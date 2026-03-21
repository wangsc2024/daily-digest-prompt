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
const lineWebhook = require('./lib/line-webhook');
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

// CORS 中介層：限制允許的來源（白名單機制）
const CORS_ALLOWED_ORIGINS = new Set([
    'http://localhost:3001',
    'http://127.0.0.1:3001',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]);
app.use((req, res, next) => {
    const origin = req.headers.origin;
    // 允許白名單來源、無 origin（同源 / curl / 排程呼叫）
    if (origin && CORS_ALLOWED_ORIGINS.has(origin)) {
        res.setHeader('Access-Control-Allow-Origin', origin);
    } else if (!origin) {
        // 同源請求（curl / 排程呼叫）：允許但不設 wildcard，避免 CORS 洩露
        res.setHeader('Access-Control-Allow-Origin', '*');
    }
    // 非白名單 origin：不設 Access-Control-Allow-Origin（瀏覽器將拒絕）
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    if (req.method === 'OPTIONS') {
        return res.sendStatus(200);
    }
    next();
});

// S12: 安全標頭
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            connectSrc: ["'self'", "ws:", "wss:"],
            imgSrc: ["'self'", "data:"],
        }
    },
    crossOriginResourcePolicy: { policy: "same-origin" },
    crossOriginOpenerPolicy: { policy: "same-origin" }
}));

// S9: 請求體大小限制（store.MAX_TASK_CONTENT_LENGTH=50KB，1MB 已足夠）
app.use(express.json({ limit: '1mb' }));

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
if (!API_SECRET_KEY) {
    console.error('[SECURITY] API_SECRET_KEY 未設定，伺服器拒絕啟動。請在 .env 設定 API_SECRET_KEY。');
    process.exit(1);
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

    const auth = req.headers['authorization'];
    if (!auth) {
        console.warn(`[AUTH] 401 缺少 Authorization header: ${req.method} ${cleanPath} from ${req.ip}`);
        return res.status(401).json({ error: '未授權：請提供有效的 API 金鑰' });
    }
    const expected = `Bearer ${API_SECRET_KEY}`;
    if (!timingSafeTokenCompare(auth, expected)) {
        console.warn(`[AUTH] 401 無效 token: ${req.method} ${cleanPath} from ${req.ip}`);
        return res.status(401).json({ error: '未授權：請提供有效的 API 金鑰' });
    }
    next();
});

// ============================================================
// 共享狀態 (透過 app.locals 供 routes 存取)
// ============================================================
app.locals.sharedSecret = null;
app.locals.sharedSecrets = new Map(); // clientEpub → sharedSecret（多用戶）
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
// relay HTTP base（去除末尾 /gun），用於 /api/notify 直接推播
const GUN_RELAY_BASE = GUN_RELAY_URL ? GUN_RELAY_URL.replace(/\/gun$/, '') : null;
const gun = Gun({
    peers: GUN_RELAY_URL ? [GUN_RELAY_URL] : [],
    radisk: true,       // 持久化至 data/radata/（重啟後恢復 Gun graph）
    axe: false,         // 避免 put ACK 異常
    localStorage: false,
});
gun.on('hi', () => {
    if (app.locals) app.locals.gunConnected = true;
    // Relay 重新連線時補發 epub（Render.com 重啟後 radisk 資料消失）
    if (myPair && epubSig) {
        gun.get('wsc-bot/handshake').put({ epub: myPair.epub, sig: epubSig, pub: myPair.pub });
        gun.get('wsc-bot/handshake').get('bot-epub').put(myPair.epub);
        console.log('[握手] relay 重連，已補發 epub');
    }
});
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
    sendReply: sendSystemReply,
    clearTaskOnRelay,
    addToConversationHistory
});

// 訊息去重：使用 Map 記錄時間戳以支援定時清理
const processedMessages = new Map();
const MSG_CACHE_TTL = 24 * 60 * 60 * 1000; // 24 小時

// ============================================================
// 連續對話歷史（per context key，in-memory）
// ============================================================
const CONV_MAX_TURNS = 6;           // 保留最近 6 輪（每輪 = user + assistant）
const CONV_TTL_MS = 30 * 60 * 1000; // 30 分鐘無活動後清除
const conversationHistories = new Map(); // contextKey → { turns: [{role, text}], lastTs }

function getConversationHistory(contextKey) {
    if (!contextKey) return [];
    const entry = conversationHistories.get(contextKey);
    if (!entry) return [];
    if (Date.now() - entry.lastTs > CONV_TTL_MS) {
        conversationHistories.delete(contextKey);
        return [];
    }
    return entry.turns;
}

function addToConversationHistory(contextKey, userText, assistantText) {
    if (!contextKey) return;
    const turns = getConversationHistory(contextKey);
    turns.push({ role: 'user', text: userText });
    turns.push({ role: 'assistant', text: assistantText });
    const trimmed = turns.slice(-(CONV_MAX_TURNS * 2));
    conversationHistories.set(contextKey, { turns: trimmed, lastTs: Date.now() });
}

/** 將對話歷史格式化為任務檔前置區段，讓 Worker 理解上下文 */
function formatHistoryForTask(history) {
    if (!Array.isArray(history) || history.length === 0) return '';
    const lines = history.map(t => `${t.role === 'user' ? '用戶' : '助理'}：${t.text}`).join('\n');
    return `## 對話上下文\n${lines}\n\n---\n\n`;
}

let myPair = null;
let epubSig = null; // 模組層級，供 gun.on('hi') 重連補發使用

function generateId(prefix) {
    return `${prefix}_${crypto.randomUUID().slice(0, 12)}`;
}

// S5: sendSystemReply — 廣播給所有已連線節點（各自加密）
// 註：my-gun-relay 會把自己註冊為「客戶端」（wsc-bot/handshake/clients/<relay.pub>），
// 故只要 relay 已啟動且與 bot 完成 ECDH 握手，sharedSecrets 即含 relay，無需瀏覽器開聊天室。
async function sendSystemReply(text, lineReplyTarget) {
    const ts = Date.now();
    const replyId = generateId('reply');

    // ── 主路徑：HTTP POST 到 relay /api/notify（HTTPS 可靠，供 LINE 推播）────
    if (GUN_RELAY_BASE && lineReplyTarget) {
        try {
            const resp = await fetch(`${GUN_RELAY_BASE}/api/notify`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${process.env.API_SECRET_KEY || ''}`,
                },
                body: JSON.stringify({ text, lineReplyTarget, msgId: replyId }),
                signal: AbortSignal.timeout(8000),
            });
            if (resp.ok) {
                console.log(`[sendSystemReply] HTTP notify 成功 → ${lineReplyTarget.slice(0, 8)}… msgId=${replyId}`);
            } else {
                console.warn(`[sendSystemReply] HTTP notify 回傳 ${resp.status}，改依 Gun P2P`);
            }
        } catch (e) {
            console.warn(`[sendSystemReply] HTTP notify 失敗 (${e.message})，改依 Gun P2P`);
        }
    }

    // ── 次要路徑：Gun P2P 廣播（供瀏覽器聊天室，fire-and-forget）────────────
    if (app.locals.sharedSecrets.size === 0) {
        if (!GUN_RELAY_BASE || !lineReplyTarget) {
            console.warn('[sendSystemReply] 無已連線節點（sharedSecrets 為空），Gun 廣播跳過。');
        }
        return;
    }
    try {
        let i = 0;
        for (const ss of app.locals.sharedSecrets.values()) {
            const nodeId = `${replyId}_${i}`;
            const payloadObj = { id: nodeId, msgId: replyId, text, ts, updatedAt: ts };
            if (lineReplyTarget) payloadObj.lineReplyTarget = lineReplyTarget;
            const encrypted = await SEA.encrypt(JSON.stringify(payloadObj), ss);
            gun.get(chatRoomName).get(nodeId).put(encrypted);
            i++;
        }
    } catch (err) {
        console.error('[sendSystemReply] Gun 廣播失敗:', err.message);
    }
}

/** 任務完成後清除 relay 上對應的訊息節點（tombstone），避免 relay 累積已結案任務內容 */
function clearTaskOnRelay(uid) {
    if (!uid || typeof uid !== 'string') return;
    try {
        gun.get(chatRoomName).get(uid).put(null);
        console.log(`[clearTaskOnRelay] 已清除 relay 節點: ${uid}`);
    } catch (err) {
        console.error('[clearTaskOnRelay] 失敗:', err.message);
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

/** 檢查並觸發到期的單次定時任務 — 以任務內容重新走分類流程 */
async function checkDueScheduledTasks() {
    const now = new Date().toISOString();
    const due = store.getDueScheduledTasks(now);
    for (const t of due) {
        try {
            classifyQueue.push({ id: generateId('sched'), text: t.task_content });
            await sendSystemReply(
                `[系統回覆] 定時任務已觸發：「${t.task_content}」，進入分類佇列處理中...`
            );
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

/** intent → 任務加註前綴（Worker 依此選擇對應 Skill/Workflow） */
const INTENT_ANNOTATIONS = {
    podcast:  '[採用製作podcast workflow] ',
    kb_answer: '[採用查詢知識庫skill] ',
    game:     '[採用設計遊戲workflow] ',
    research: '[採用深度研究skill] '
};

/** intent → 顯示標籤 */
const INTENT_LABELS = {
    podcast:  'Podcast型',
    kb_answer: '知識庫查詢型',
    game:     '遊戲設計型',
    research: '深度研究型',
    general:  '一般型'
};

/** 從 intent 推導 is_research（供 store 欄位向後相容） */
function intentToIsResearch(intent) { return intent === 'research'; }

/** 從 intent 推導 task_type（供 store 欄位向後相容） */
function intentToTaskType(intent) { return intent || 'general'; }

const classifyQueue = createQueue({
    concurrency: CONCURRENCY,
    maxRetries: 3,
    processor: async (item) => classifier.classify(item.text),
    onComplete: async (item, decision) => {
        const intent = decision.intent || 'general';
        const annotation = INTENT_ANNOTATIONS[intent] || '';
        const annotatedContent = annotation + decision.task_content;
        const isResearch = intentToIsResearch(intent);
        const taskType = intentToTaskType(intent);
        const typeLabel = INTENT_LABELS[intent] || '一般型';

        // ---- 1. 週期性任務 → cron 排程 ----
        if (decision.is_periodic && cron.validate(decision.cron_expression)) {
            if (!isCronIntervalSafe(decision.cron_expression)) {
                console.error(`[classify] cron 間隔過短，拒絕：${decision.cron_expression}`);
                await sendSystemReply(
                    `[系統回覆] 排程間隔過短（最少 ${CRON_MIN_INTERVAL_MINUTES} 分鐘），已降級為立即執行。`,
                    item.lineReplyTarget
                );
                // 以原始任務內容重新進入分類流程（立即執行）
                classifyQueue.push({ id: generateId('instant'), text: decision.task_content, lineUserId: item.lineUserId, lineReplyTarget: item.lineReplyTarget, lineSourceType: item.lineSourceType });
                return;
            }

            // 去重：同 expression + 同內容已存在則跳過（防 Gun.js 重播重複建立）
            const existingJob = store.cronJobs.find(j => {
                if (j.cron_expression !== decision.cron_expression) return false;
                const norm = s => (s || '').replace(/每天\s*[\d]+\s*[:\uff1a]\s*[\d]+\s*/g, '').replace(/\s+/g, ' ').trim();
                return norm(j.task_content) === norm(decision.task_content);
            });
            if (existingJob) {
                console.log(`[cron] 已存在相同排程（${existingJob.id}），略過重複建立`);
                return;
            }

            const cronId = generateId('cron');
            // 觸發時以任務內容重新走分類流程，而非直接建檔
            const task = cron.schedule(decision.cron_expression, () => {
                try {
                    classifyQueue.push({ id: generateId('cron'), text: decision.task_content });
                } catch (err) {
                    console.error(`[cron ${cronId}] 推入分類佇列失敗:`, err.message);
                }
            });
            app.locals.activeCronJobs[cronId] = task;

            // 儲存原始任務內容（無加註），觸發時重新分類
            store.addCronJob({
                id: cronId,
                cron_expression: decision.cron_expression,
                task_content: decision.task_content,
                created_at: new Date().toISOString()
            });

            await sendSystemReply(
                `[系統回覆] 已設定週期任務：「${decision.task_content}」(${typeLabel})，排程：${decision.cron_expression}`,
                item.lineReplyTarget
            );
            return;
        }

        // ---- 2. 單次定時任務 → 存入 scheduled_tasks，觸發時重新分類 ----
        if (decision.is_scheduled && decision.scheduled_at) {
            const schedId = generateId('sched');
            // 儲存原始任務內容（無加註），觸發時重新分類
            store.addScheduledTask({
                id: schedId,
                task_content: decision.task_content,
                scheduled_at: decision.scheduled_at.trim(),
                created_at: new Date().toISOString(),
                source_id: item.id,
                status: 'waiting'
            });
            await sendSystemReply(
                `[系統回覆] 已排定任務：「${decision.task_content}」(${typeLabel})，將於 ${decision.scheduled_at} 執行。`,
                item.lineReplyTarget
            );
            return;
        }

        // ---- 3. 無效 cron 警告（is_periodic 但表達式無效） ----
        if (decision.is_periodic) {
            console.error(`[classify] 無效的 cron 表達式: ${decision.cron_expression}`);
        }

        // ---- 4. 即時任務 ----
        // general：Groq 直接回覆（via Gun Relay → LINE），不建檔；降級時加前綴提示
        if (intent === 'general') {
            const degradedPrefix = decision._degraded ? '[降級回答] ' : '';
            try {
                const quickAnswer = await classifier.answerQuestion(item.text, item.conversationHistory);
                const reply = quickAnswer || '已收到您的訊息。';
                await sendSystemReply(`[系統回覆] ${degradedPrefix}${reply}`, item.lineReplyTarget);
                // 更新連續對話歷史
                if (item.contextKey) addToConversationHistory(item.contextKey, item.text, reply);
                // 持久化「已處理」記錄，重啟後 Gun 重播不會重複回覆（僅寫 records.json，不建 .md）
                store.addProcessedOnlyRecord(item.id);
            } catch (err) {
                console.error('[classify] 簡答發送失敗:', err.message);
                await sendSystemReply(`[系統回覆] ${degradedPrefix}已收到您的訊息。`, item.lineReplyTarget);
                store.addProcessedOnlyRecord(item.id);
            }
            return;
        }

        // podcast / kb_answer / game / research：加註後建檔，交由 Worker 執行
        // 將對話歷史前置於任務檔，讓 Worker 理解上下文
        const historyPrefix = formatHistoryForTask(item.conversationHistory);
        const taskWithContext = historyPrefix + annotatedContent;
        store.addRecord(item.id, taskWithContext, isResearch, taskType, item.lineUserId, item.lineReplyTarget, item.lineSourceType, item.contextKey, item.text);
        await sendSystemReply(
            `[系統回覆] 已將任務存為檔案 ${item.id}.md (${typeLabel})，等待 Worker 認領處理中...`,
            item.lineReplyTarget
        );
    },
    onError: (item, err) => {
        console.error('[classify] AI 分類失敗:', err.message);
        sendSystemReply(
            '[系統回覆] [降級回答] AI 分類服務暫時無法使用，請稍後再試。',
            item.lineReplyTarget
        ).catch(e => console.error('[classify] 降級回覆失敗:', e.message));
        store.addProcessedOnlyRecord(item.id);
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

        // 三層去重防護：bot 自產節點前綴過濾（reply_/broadcast_/msg_）
        // reply_ 由 sendSystemReply 產生，broadcast_ 由 /api/broadcast 產生
        // 這些 ID 從未加入 store，重啟後 Gun 重播會被誤判為新用戶訊息
        if (id.startsWith('reply_') || id.startsWith('broadcast_')) {
            processedMessages.set(id, Date.now());
            return;
        }

        // 二層去重：Map 被 TTL 清除後，仍可靠 store 避免重複處理
        if (store.getRecord(id)) {
            processedMessages.set(id, Date.now());
            return;
        }

        if (!data || app.locals.sharedSecrets.size === 0) return;

        // 多用戶：逐一嘗試所有已知 sharedSecret 解密
        let raw = null;
        for (const ss of app.locals.sharedSecrets.values()) {
            try {
                const decrypted = await SEA.decrypt(data, ss);
                if (decrypted !== undefined && decrypted !== null) { raw = decrypted; break; }
            } catch {}
        }

        // 不要把暫時無法解密的訊息標記為已處理。
        // 這類情況可能只是握手尚未完成或 relay 稍後重送新密文，
        // 若先寫入 processedMessages，後續同 id 重送會被永久吞掉。
        if (raw === null) {
            return;
        }

        try {
            // SEA.decrypt 可能回傳字串（用戶訊息）或已解析物件（relay 送來的 {id,text,ts,lineUserId,lineReplyTarget,lineSourceType}）
            let text;
            let lineUserId;
            let lineReplyTarget;
            let lineSourceType;
            if (typeof raw === 'string') {
                text = raw;
            } else if (raw && typeof raw === 'object' && raw.text) {
                text = raw.text;
                lineUserId = raw.lineUserId || undefined;
                lineReplyTarget = raw.lineReplyTarget || raw.lineUserId || undefined;
                lineSourceType = raw.lineSourceType || undefined;
            } else {
                text = raw != null ? String(raw) : '';
            }
            if (!text || text.startsWith('[系統回覆]')) return;

            processedMessages.set(id, Date.now());
            const contextKey = lineReplyTarget || lineUserId || 'chatroom';
            const conversationHistory = getConversationHistory(contextKey);
            if (!classifyQueue.push({ id, text, lineUserId, lineReplyTarget, lineSourceType, contextKey, conversationHistory })) {
                store.addRecord(id, text, false, undefined, lineUserId, lineReplyTarget, lineSourceType);
                console.warn(`[message] 佇列已滿，直接存為未分類任務: ${id}`);
            }
        } catch (err) {
            processedMessages.set(id, Date.now());
            console.error(`[message] 處理失敗 ${id}:`, err.message);
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

    // 初始化 LINE Client（推播模式，允許直接回報至 LINE，不依賴 relay 的揮發 lineUserId 變數）
    lineWebhook.initClient();

    // 從既有 records + scheduledTasks + workflows 填充去重快取，防止重啟後 Gun.js 重播訊息導致重複處理
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
    for (const wf of store.workflows) {
        if (wf.source_id && !processedMessages.has(wf.source_id)) {
            const ts = new Date(wf.created_at).getTime();
            processedMessages.set(wf.source_id, Number.isNaN(ts) ? Date.now() : ts);
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
    // G20: 廣播 epub + pub + 附加自身簽章（防 MITM：收方可用 pub 驗證 sig）
    epubSig = await SEA.sign(myPair.epub, myPair);
    gun.get('wsc-bot/handshake').put({ epub: myPair.epub, sig: epubSig, pub: myPair.pub });
    // 相容舊版客端讀取路徑 `bot-epub`
    gun.get('wsc-bot/handshake').get('bot-epub').put(myPair.epub);
    console.log('[握手] 已將 bot epub + 簽章公告至 Gun relay');

    /** 註冊客端 epub，計算 sharedSecret 並啟動訊息迴圈（如尚未啟動） */
    async function registerClient(clientEpub) {
        const ss = await SEA.secret(clientEpub, myPair);
        app.locals.sharedSecrets.set(clientEpub, ss);
        app.locals.sharedSecret = ss; // 向下相容
        if (!app.locals.isListening) {
            startMessageLoop();
            console.log('[握手] 已與前端完成 ECDH 金鑰交換，開始監聽加密訊息');
        } else {
            console.log(`[握手] 客端連線/重連，已連線用戶數: ${app.locals.sharedSecrets.size}`);
        }
    }

    // 向下相容：單一 client-epub 路徑
    gun.get('wsc-bot/handshake').get('client-epub').on(async (clientEpub) => {
        if (!clientEpub || typeof clientEpub !== 'string') return;
        if (clientEpub.length > 2048) return;
        await registerClient(clientEpub);
    });

    // 多用戶：監聽 clients map，每個用戶以自身 pub 為 key 發布 epub
    gun.get('wsc-bot/handshake').get('clients').map().on(async (clientEpub, userPub) => {
        if (!clientEpub || typeof clientEpub !== 'string') return;
        if (clientEpub.length > 2048) return;
        await registerClient(clientEpub);
    });

    // 重新載入 cron 排程 (P2)。L4: 重載時也檢查最小間隔，避免惡意表達式一旦寫入即永久生效
    // 觸發時以任務內容重新走分類流程，確保 annotation 與 intent 邏輯保持最新
    for (const job of store.cronJobs) {
        if (cron.validate(job.cron_expression) && isCronIntervalSafe(job.cron_expression)) {
            const task = cron.schedule(job.cron_expression, () => {
                try {
                    classifyQueue.push({ id: generateId('cron'), text: job.task_content });
                } catch (err) {
                    console.error(`[cron ${job.id}] 推入分類佇列失敗:`, err.message);
                }
            });
            app.locals.activeCronJobs[job.id] = task;
        }
    }
    const cronCount = Object.keys(app.locals.activeCronJobs).length;
    if (cronCount > 0) console.log(`已重新載入 ${cronCount} 個 cron 排程`);

    // s11: 每分鐘自動釋放逾時的認領 + 回收卡住的 processing + 檢查到期定時任務
    cron.schedule('* * * * *', () => {
        store.releaseExpiredClaims();
        store.recoverStaleProcessing();
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
