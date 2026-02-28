/**
 * bot.js — 薄進入點
 *
 * 遵循 learn-claude-code 核心理念：
 * "The model is the agent. Our job is to give it tools and stay out of the way."
 *
 * 本檔只做三件事：init → mount → listen
 * 所有業務邏輯分散於 lib/ 模組中。
 *
 * 機制：
 * - s08: 背景佇列 — 分類作業非同步執行，不阻塞訊息接收
 * - s10: FSM — 任務狀態透過 store.transitionState() 管理
 * - s11: 逾時釋放 — 每分鐘自動釋放卡住的認領
 *
 * 安全修正：
 * - 訊息去重移至驗證成功後，防止無效訊息佔位導致資料遺失
 * - processedMessages 定時清理，防止長期運行記憶體洩漏
 * - cron 回呼加入 try-catch，防止靜默失敗
 * - graceful shutdown 處理 SIGTERM/SIGINT
 * - timing-safe token 比較，防止計時攻擊 (S1)
 * - unhandledRejection / uncaughtException 全域處理 (S2)
 * - sendSystemReply 錯誤捕獲 (S5)
 * - helmet 安全標頭 (S12)
 */
require('dotenv').config();

// 過濾 Gun.js SEA 內部的 "Could not decrypt" 雜訊
// 只在 DEBUG=true 時才輸出
if (process.env.DEBUG !== 'true') {
    const _warn = console.warn.bind(console);
    console.warn = (...args) => {
        if (typeof args[0] === 'string' && args[0].includes('Could not decrypt')) return;
        _warn(...args);
    };
}

const crypto = require('crypto');
const express = require('express');
const helmet = require('helmet');
const path = require('path');
const Gun = require('gun');
const cron = require('node-cron');
const { CronExpressionParser } = require('cron-parser');
const rateLimit = require('express-rate-limit');
require('gun/sea');

const store = require('./lib/store');
const classifier = require('./lib/classifier');
const routes = require('./lib/routes');
const { createQueue } = require('./lib/queue');
const workflow = require('./lib/workflow');

// ============================================================
// S2: 全域未捕獲例外處理
// ============================================================
process.on('unhandledRejection', (reason, promise) => {
    console.error('[unhandledRejection]', reason);
});

process.on('uncaughtException', (err) => {
    console.error('[uncaughtException]', err);
    process.exit(1);
});

// ============================================================
// Express 初始化 + 中介層
// ============================================================
const app = express();

// 完全寬鬆的 CORS 中介層 (解決本地 file:// 存取問題)
app.use((req, res, next) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    if (req.method === 'OPTIONS') {
        return res.sendStatus(200);
    }
    next();
});

// S12: 安全標頭 (在本地開發時暫時放寬)
app.use(helmet({
    contentSecurityPolicy: false,
    crossOriginResourcePolicy: { policy: "cross-origin" },
    crossOriginOpenerPolicy: { policy: "unsafe-none" }
}));

// S9: 請求體大小限制
app.use(express.json({ limit: '100kb' }));

// 速率限制 (A2)。Worker 端 poll/claim/state/processed 單筆任務約 4+ 次，多筆易觸頂，故對 /api/records 放寬 (C5)
const apiLimiter = rateLimit({
    windowMs: 60 * 1000,
    max: 60,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: '請求過於頻繁，請稍後再試' }
});
const workerLimiter = rateLimit({
    windowMs: 60 * 1000,
    max: 300,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'Worker 請求過於頻繁，請稍後再試' }
});
app.use('/api/', (req, res, next) => {
    const p = (req.path || '').replace(/^\/+/, '');
    if (p.startsWith('records')) return workerLimiter(req, res, next);
    return apiLimiter(req, res, next);
});

// S1: Timing-safe Bearer Token 認證 (HMAC 消除長度洩漏)
const API_SECRET_KEY = process.env.API_SECRET_KEY ? process.env.API_SECRET_KEY.trim() : null;
const HMAC_KEY = crypto.randomBytes(32); // per-boot random key
// C2 修復：未設定時明確警告（避免靜默開放認證）
if (!API_SECRET_KEY) {
    logger.warn('[SECURITY] API_SECRET_KEY 未設定 — 所有 API 端點無需認證（僅限開發環境）');
}

function timingSafeTokenCompare(a, b) {
    // HMAC both values so buffers are always same length, eliminating length oracle
    const hmacA = crypto.createHmac('sha256', HMAC_KEY).update(String(a)).digest();
    const hmacB = crypto.createHmac('sha256', HMAC_KEY).update(String(b)).digest();
    return crypto.timingSafeEqual(hmacA, hmacB);
}

// 託管前端控制台 (根目錄) - 放在認證之前
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.use((req, res, next) => {
    const cleanPath = req.path.replace(/\/$/, '') || '/';

    // 偵錯日誌：如果您還是看到錯誤，請看終端機輸出的路徑是什麼
    // console.log(`[HTTP] ${req.method} ${cleanPath}`);

    // 放行清單
    if (cleanPath === '/' || cleanPath === '/api/health') {
        return next();
    }

    if (!API_SECRET_KEY) return next();

    const auth = req.headers['authorization'];
    if (!auth) {
        return res.status(401).json({ error: '未授權：請提供有效的 API 金鑰' });
    }
    const expected = `Bearer ${API_SECRET_KEY}`;
    if (!timingSafeTokenCompare(auth, expected)) {
        return res.status(401).json({ error: '未授權：請提供有效的 API 金鑰' });
    }
    next();
});

// ============================================================
// 共享狀態 (透過 app.locals 供 routes 存取)
// ============================================================
app.locals.sharedSecret = null;
app.locals.isListening = false;
app.locals.activeCronJobs = {};
app.locals.gunConnected = false; // M4: 由 Gun hi/bye 更新，供 /api/health 回報

// ============================================================
// Gun.js（須在 routes.mount 前初始化，因 mount 需注入 gun/SEA/chatRoomName）
// ============================================================
const GUN_RELAY_URL = process.env.GUN_RELAY_URL;
if (!GUN_RELAY_URL) {
    console.warn('[警告] GUN_RELAY_URL 未設定，Gun.js 將無法連線至 relay 伺服器');
}
const gun = Gun({
    peers: GUN_RELAY_URL ? [GUN_RELAY_URL] : [],
    radisk: true,       // 持久化至 data/radata/（重啟後恢復 Gun graph）
    axe: false,         // 避免 put ACK 異常
    localStorage: false,
});
gun.on('hi', () => { if (app.locals) app.locals.gunConnected = true; });
gun.on('bye', () => { if (app.locals) app.locals.gunConnected = false; });
const SEA = Gun.SEA;
const chatRoomName = 'render_isolated_chat_room';

// 掛載路由 dispatch map（L1: Gun 端點依賴於 init 前注入，myPair 於 init 後才有，故以 getter 傳入）
// sendReply: 讓 /processed 透過 bot 的長駐 Gun 連線回傳結果，避免 Worker 自呼 /api/send 因 relay 斷線遺失訊息
routes.mount(app, {
    gun,
    SEA,
    getMyPair: () => myPair,
    chatRoomName,
    generateId,
    startMessageLoop,
    classifier,
    sendReply: sendSystemReply
});

// 訊息去重：使用 Map 記錄時間戳以支援定時清理
const processedMessages = new Map();
const MSG_CACHE_TTL = 24 * 60 * 60 * 1000; // 24 小時

let myPair = null;

function generateId(prefix) {
    return `${prefix}_${crypto.randomUUID().slice(0, 12)}`;
}

// S5: sendSystemReply 加入錯誤捕獲
async function sendSystemReply(text) {
    if (!app.locals.sharedSecret) return;
    try {
        // G25: 加密含時間戳的 JSON payload，供前端排序使用
        const payload = JSON.stringify({ text, ts: Date.now() });
        const encrypted = await SEA.encrypt(payload, app.locals.sharedSecret);
        gun.get(chatRoomName).get(generateId('reply')).put(encrypted);
    } catch (err) {
        console.error('[sendSystemReply] 失敗:', err.message);
    }
}

/** 清理過期的去重記錄，防止記憶體洩漏；保留仍有 store 記錄的 ID 以免 Gun 重播重複處理 */
function purgeStaleMessages() {
    const cutoff = Date.now() - MSG_CACHE_TTL;
    for (const [id, ts] of processedMessages) {
        if (ts < cutoff && !store.getRecord(id)) {
            processedMessages.delete(id);
        }
    }
}

// ============================================================
// 單次定時任務：時區與最遠排程天數
// ============================================================
const TIMEZONE = (process.env.TIMEZONE || 'Asia/Taipei').trim();
const SCHEDULED_MAX_DAYS = Math.max(1, Math.min(365, parseInt(process.env.SCHEDULED_MAX_DAYS || '7', 10) || 7));

// ============================================================
// S8: Cron 表達式最小間隔檢查
// ============================================================
const CRON_MIN_INTERVAL_MINUTES = 5;

/** 每小時允許的最大觸發次數（C4：正面列表，防止複合格式繞過） */
const MAX_CRON_TRIGGERS_PER_HOUR = Math.floor(60 / CRON_MIN_INTERVAL_MINUTES);

/**
 * 檢查 cron 表達式是否滿足最小間隔（防止 * * * * * 或 0-59/2 等每小時觸發過密）
 * 以「未來 1 小時觸發次數」為準，超過上限則拒絕 (C4)
 * @param {string} expression - cron 5 碼表達式
 * @returns {boolean} true = 安全
 */
function isCronIntervalSafe(expression) {
    if (!expression || !cron.validate(expression)) return false;
    let count = 0;
    try {
        const now = new Date();
        const endAt = new Date(now.getTime() + 60 * 60 * 1000);
        const interval = CronExpressionParser.parse(expression.trim(), {
            currentDate: now,
            endDate: endAt
        });
        while (count <= MAX_CRON_TRIGGERS_PER_HOUR) {
            const next = interval.next();
            const t = next.toDate ? next.toDate().getTime() : next.getTime();
            if (t >= endAt.getTime()) break;
            count++;
        }
        return count <= MAX_CRON_TRIGGERS_PER_HOUR;
    } catch (err) {
        if (err.message && err.message.includes('time span')) return count <= MAX_CRON_TRIGGERS_PER_HOUR;
        return false;
    }
}

/** 檢查並觸發到期的單次定時任務 */
async function checkDueScheduledTasks() {
    const now = new Date().toISOString();
    const due = store.getDueScheduledTasks(now);
    for (const t of due) {
        try {
            if (t.workflow_data && t.workflow_data.name && Array.isArray(t.workflow_data.steps)) {
                workflow.createWorkflow(t.workflow_data.name, t.workflow_data.steps, t.source_id);
                await sendSystemReply(
                    `[系統回覆] 定時任務已觸發：「${t.task_content}」（工作流），等待 Worker 依序處理中...`
                );
            } else {
                store.addRecord(generateId('sched'), t.task_content, t.is_research);
                await sendSystemReply(
                    `[系統回覆] 定時任務已觸發：「${t.task_content}」，等待 Worker 認領處理中...`
                );
            }
            store.markScheduledTaskTriggered(t.id);
        } catch (err) {
            console.error(`[scheduled] 觸發任務 ${t.id} 失敗:`, err.message);
        }
    }
}

// ============================================================
// s08: 背景分類佇列 — "Fire and forget"
// ============================================================
// G27: 並行度從環境變數讀取（預設 1 避免免費額度 5 次/分鐘 觸發 429；付費方案設 CLASSIFY_CONCURRENCY=3）
const CONCURRENCY = parseInt(process.env.CLASSIFY_CONCURRENCY || '1', 10);
const classifyQueue = createQueue({
    concurrency: CONCURRENCY,
    maxRetries: 3,
    processor: async (item) => classifier.classify(item.text),
    onComplete: async (item, decision) => {
        // ---- 1. 週期性任務 → cron 排程 ----
        if (decision.is_periodic && cron.validate(decision.cron_expression)) {
            if (!isCronIntervalSafe(decision.cron_expression)) {
                console.error(`[classify] cron 間隔過短，拒絕：${decision.cron_expression}`);
                await sendSystemReply(
                    `[系統回覆] 排程間隔過短（最少 ${CRON_MIN_INTERVAL_MINUTES} 分鐘），已降級為單次任務。`
                );
                store.addRecord(item.id, decision.task_content, decision.is_research);
                return;
            }

            const cronId = generateId('cron');
            const task = cron.schedule(decision.cron_expression, () => {
                try {
                    store.addRecord(generateId('cron'), decision.task_content, decision.is_research);
                } catch (err) {
                    console.error(`[cron ${cronId}] 建立任務失敗:`, err.message);
                }
            });
            app.locals.activeCronJobs[cronId] = task;

            store.addCronJob({
                id: cronId,
                cron_expression: decision.cron_expression,
                task_content: decision.task_content,
                is_research: decision.is_research,
                created_at: new Date().toISOString()
            });

            await sendSystemReply(
                `[系統回覆] 已設定週期任務：「${decision.task_content}」` +
                `(研究型: ${decision.is_research})，排程：${decision.cron_expression}`
            );
            return;
        }

        // ---- 2. 單次定時任務 → 存入 scheduled_tasks ----
        if (decision.is_scheduled && decision.scheduled_at) {
            const schedId = generateId('sched');
            let workflowData = null;
            if (decision.is_workflow) {
                try {
                    const decomposition = await classifier.decomposeWorkflow(decision.task_content);
                    if (decomposition) workflowData = decomposition;
                } catch (err) {
                    console.error('[classify] 定時任務工作流分解失敗，存為單一任務:', err.message);
                }
            }
            store.addScheduledTask({
                id: schedId,
                task_content: decision.task_content,
                is_research: !!decision.is_research,
                is_workflow: !!decision.is_workflow && !!workflowData,
                workflow_data: workflowData,
                scheduled_at: decision.scheduled_at.trim(),
                created_at: new Date().toISOString(),
                source_id: item.id,
                status: 'waiting'
            });
            await sendSystemReply(
                `[系統回覆] 已排定任務：「${decision.task_content}」，將於 ${decision.scheduled_at} 執行。`
            );
            return;
        }

        // ---- 3. 多步驟工作流 → 分解 + 建立工作流 ----
        if (decision.is_workflow) {
            try {
                const decomposition = await classifier.decomposeWorkflow(decision.task_content);
                if (decomposition) {
                    const wf = workflow.createWorkflow(
                        decomposition.name,
                        decomposition.steps,
                        item.id
                    );
                    const stepNames = wf.steps.map(s => s.name).join(' → ');
                    await sendSystemReply(
                        `[系統回覆] 已建立工作流「${wf.name}」（${wf.steps.length} 步驟）：${stepNames}` +
                        `\n工作流 ID: ${wf.id}，等待 Worker 依序處理中...`
                    );
                    return;
                }
            } catch (err) {
                console.error('[classify] 工作流分解失敗，降級為單一任務:', err.message);
            }
            // 分解失敗時降級為單一任務
        }

        // ---- 4. 即時單次任務 ----
        if (decision.is_periodic) {
            console.error(`[classify] 無效的 cron 表達式: ${decision.cron_expression}`);
        }
        store.addRecord(item.id, decision.task_content, decision.is_research);
        await sendSystemReply(
            `[系統回覆] 已將任務存為檔案 ${item.id}.md` +
            ` (研究型: ${decision.is_research})，等待 Worker 認領處理中...`
        );
        // 簡答：僅對「一般單次、非工作流」任務立即回覆；研究型／定時由 Worker 處理，不發簡答
        if (!decision.is_workflow && !decision.is_research) {
            try {
                const quickAnswer = await classifier.answerQuestion(item.text);
                if (quickAnswer) {
                    await sendSystemReply(`[系統回覆] (簡答) ${quickAnswer}`);
                }
            } catch (err) {
                console.error('[classify] 簡答發送失敗:', err.message);
            }
        }
    },
    onError: (item, err) => {
        console.error('[classify] AI 分類失敗:', err.message);
        store.addRecord(item.id, item.text, false);
    }
});

// 暴露佇列狀態供 health API 使用
app.locals.classifyQueue = classifyQueue;

// ============================================================
// 訊息處理迴圈 — "One loop, many mechanisms"
// ============================================================
function startMessageLoop() {
    gun.get(chatRoomName).map().on(async (data, id) => {
        if (processedMessages.has(id)) return;

        // 二層去重：Map 被 TTL 清除後，仍可靠 store 避免重複處理
        if (store.getRecord(id)) {
            processedMessages.set(id, Date.now());
            return;
        }

        if (!data || !app.locals.sharedSecret) return;

        try {
            const raw = await SEA.decrypt(data, app.locals.sharedSecret);
            const text = typeof raw === 'string' ? raw : (raw != null ? String(raw) : '');
            if (!text || text.startsWith('[系統回覆]')) return;

            processedMessages.set(id, Date.now());
            if (!classifyQueue.push({ id, text })) {
                store.addRecord(id, text, false);
                console.warn(`[message] 佇列已滿，直接存為未分類任務: ${id}`);
            }
        } catch (err) {
            processedMessages.set(id, Date.now());
            console.error(`[message] 解密失敗 ${id}:`, err.message);
        }
    });

    app.locals.isListening = true;
}

// ============================================================
// VZ4: /api/broadcast — 推播執行摘要到聊天室（純文字廣播）
// ============================================================
app.post('/api/broadcast', async (req, res) => {
    try {
        const { message } = req.body;
        if (!message || typeof message !== 'string') {
            return res.status(400).json({ error: '缺少 message 欄位' });
        }
        if (message.length > 5000) {
            return res.status(400).json({ error: '訊息超過 5000 字元限制' });
        }

        if (!myPair) {
            return res.status(503).json({ error: 'Bot 金鑰尚未初始化' });
        }

        // 廣播純文字摘要到聊天室（以 bot 身分，不加密，直接寫入 Gun graph）
        const msgId = 'broadcast_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
        gun.get(chatRoomName).get(msgId).put({
            bot: true,
            text: message,
            ts: Date.now()
        });

        console.log(`[broadcast] 推播訊息 ${msgId}（${message.length} 字元）`);
        res.json({ ok: true, msgId });
    } catch (err) {
        console.error(`[broadcast] 失敗: ${err.message}`);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// 初始化 + 啟動
// ============================================================
let server;

async function init() {
    // Groq API（意圖分類、簡答、工作流分解）
    if (!process.env.GROQ_API_KEY) {
        console.error('錯誤：請在 .env 檔案中設定 GROQ_API_KEY（跑 bot.js 的環境使用 Groq 做意圖分類）');
        process.exit(1);
    }
    classifier.init(process.env.GROQ_API_KEY.trim());

    // 從既有 records + scheduledTasks 填充去重快取，防止重啟後 Gun.js 重播訊息導致重複處理
    for (const rec of store.records) {
        const ts = new Date(rec.time).getTime();
        processedMessages.set(rec.uid, Number.isNaN(ts) ? Date.now() : ts);
    }
    for (const st of store.scheduledTasks) {
        if (st.source_id && !processedMessages.has(st.source_id)) {
            const ts = new Date(st.created_at).getTime();
            processedMessages.set(st.source_id, Number.isNaN(ts) ? Date.now() : ts);
        }
    }
    if (processedMessages.size > 0) {
        console.log(`已從既有記錄填充 ${processedMessages.size} 筆去重快取`);
    }

    // SEA 金鑰對 (P4: 持久化)
    const savedPair = store.loadKeypair();
    if (savedPair) {
        myPair = savedPair;
        console.log('已從檔案載入 SEA 金鑰對');
    } else {
        myPair = await SEA.pair();
        store.saveKeypair(myPair);
        console.log('已產生並儲存新的 SEA 金鑰對');
    }
    console.log('伺服器的公開加密金鑰 (epub):', myPair.epub);

    // Gun 握手：公告 bot epub，並監聽 client epub（取代 /api/connect HTTP 呼叫）
    // epub 是 ECDH 公鑰，公開傳遞安全，私鑰 epriv 永不離開本機
    // G20: 廣播 epub + 附加自身簽章（防 MITM：收方可用簽章驗證 epub 真實性）
    const epubSig = await SEA.sign(myPair.epub, myPair);
    gun.get('wsc-bot/handshake').put({ epub: myPair.epub, sig: epubSig });
    console.log('[握手] 已將 bot epub + 簽章公告至 Gun relay');

    gun.get('wsc-bot/handshake').get('client-epub').on(async (clientEpub) => {
        if (!clientEpub || typeof clientEpub !== 'string') return;
        if (clientEpub.length > 2048) return;
        if (app.locals.isListening) return; // 已建立連線，忽略重複握手
        app.locals.sharedSecret = await SEA.secret(clientEpub, myPair);
        startMessageLoop();
        console.log('[握手] 已與前端完成 ECDH 金鑰交換，開始監聽加密訊息');
    });

    // 重新載入 cron 排程 (P2)。L4: 重載時也檢查最小間隔，避免惡意表達式一旦寫入即永久生效
    for (const job of store.cronJobs) {
        if (cron.validate(job.cron_expression) && isCronIntervalSafe(job.cron_expression)) {
            const task = cron.schedule(job.cron_expression, () => {
                try {
                    store.addRecord(generateId('cron'), job.task_content, job.is_research);
                } catch (err) {
                    console.error(`[cron ${job.id}] 建立任務失敗:`, err.message);
                }
            });
            app.locals.activeCronJobs[job.id] = task;
        }
    }
    const cronCount = Object.keys(app.locals.activeCronJobs).length;
    if (cronCount > 0) console.log(`已重新載入 ${cronCount} 個 cron 排程`);

    // s11: 每分鐘自動釋放逾時的認領，並檢查到期的單次定時任務
    cron.schedule('* * * * *', () => {
        store.releaseExpiredClaims();
        purgeStaleMessages();
        checkDueScheduledTasks().catch(err => console.error('[checkDueScheduledTasks]', err.message));
    });

    // 啟動時掃描已到期但未觸發的定時任務（處理重啟後的遺漏）
    checkDueScheduledTasks().catch(err => console.error('[checkDueScheduledTasks]', err.message));

    // 啟動伺服器
    const PORT = process.env.PORT || 3001;
    server = app.listen(PORT, () => console.log(`=== API 伺服器正在監聽 port ${PORT} ===`));
}

// ============================================================
// Graceful Shutdown
// ============================================================
function shutdown() {
    console.log('收到關閉信號，正在優雅關閉...');
    // 停止所有 cron 排程
    Object.values(app.locals.activeCronJobs).forEach(task => task.stop());
    if (server) {
        server.close(() => {
            console.log('伺服器已關閉');
            process.exit(0);
        });
        // 最多等待 10 秒
        setTimeout(() => {
            console.error('強制關閉（逾時 10 秒）');
            process.exit(1);
        }, 10000);
    } else {
        process.exit(0);
    }
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

init();
