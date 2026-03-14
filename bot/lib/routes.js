/**
 * routes.js — Express 路由 dispatch map
 *
 * 遵循 learn-claude-code：
 * - s02: dispatch map pattern — bot.js 只做掛載
 * - s10: FSM — 狀態轉換端點
 * - s11: poll-claim-work — 認領 / 釋放端點
 *
 * 安全修正：
 * - state 參數白名單驗證
 * - path.resolve 防止路徑穿越
 * - dispatch map 增加 fallback 防止 undefined 呼叫
 * - S7: worker_id 長度驗證
 * - D3: 分頁支援 (limit / offset)
 * - S4: removeRecord 回傳 not_cancellable
 */
const fs = require('fs');
const path = require('path');
const http = require('http');
const store = require('./store');
const skills = require('./skills');
const { STATES } = require('./fsm');
const workflow = require('./workflow');

// 需自動存入知識庫的任務類型關鍵字
const KB_KEYWORDS = ['研究', '規劃', '計畫', '方案', '架構', '設計', '優化', '改善', '提升', '重構', '改進', '分析', '評估', '策略', '報告'];
const KB_URL = 'http://127.0.0.1:3000';

// 機器人記憶（最近 N 筆完成任務，持久化，供 Worker 注入上下文）
const DATA_DIR = process.env.WSC_BOT_DATA_DIR || path.join(__dirname, '..', 'data');
const BOT_MEMORY_PATH = path.join(DATA_DIR, 'bot-memory.json');
const MEMORY_MAX_ENTRIES = 20;

/**
 * 非同步將任務+成果存入知識庫（fire-and-forget，不影響回應速度）
 */
function saveToKnowledgeBase(taskContent, resultStr) {
    const title = taskContent.trim().slice(0, 60) + (taskContent.length > 60 ? '…' : '');
    const noteContent = `## 任務\n${taskContent}\n\n## 執行結果\n${resultStr}`;
    const body = JSON.stringify({ title, content: noteContent, source: 'manual' });
    const req = http.request(`${KB_URL}/api/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body) }
    }, res => {
        console.log(`[KB] 已儲存任務至知識庫: ${title} (HTTP ${res.statusCode})`);
    });
    req.on('error', e => console.error('[KB] 儲存失敗:', e.message));
    req.write(body);
    req.end();
}

/**
 * 是否將任務結果存入知識庫。
 * 規則：研究型一律存 KB；code 型一律存規劃結果至 KB；其餘依關鍵字。
 */
function shouldSaveToKB(taskContent, isResearch, taskType) {
    if (isResearch) return true;
    if (taskType === 'code') return true;
    const lower = taskContent || '';
    return KB_KEYWORDS.some(kw => lower.includes(kw));
}

function loadBotMemory() {
    try {
        if (fs.existsSync(BOT_MEMORY_PATH)) {
            return JSON.parse(fs.readFileSync(BOT_MEMORY_PATH, 'utf8'));
        }
    } catch {}
    return { version: 1, recent_tasks: [] };
}

function saveBotMemory(taskContent, resultStr, isResearch) {
    try {
        const mem = loadBotMemory();
        mem.recent_tasks.unshift({
            ts: new Date().toISOString(),
            task_preview: (taskContent || '').trim().slice(0, 120),
            result_preview: (resultStr || '').trim().slice(0, 300),
            is_research: !!isResearch
        });
        if (mem.recent_tasks.length > MEMORY_MAX_ENTRIES) {
            mem.recent_tasks = mem.recent_tasks.slice(0, MEMORY_MAX_ENTRIES);
        }
        fs.writeFileSync(BOT_MEMORY_PATH, JSON.stringify(mem, null, 2), 'utf8');
    } catch (e) {
        console.error('[Memory] 儲存失敗:', e.message);
    }
}

const VALID_STATES = new Set(Object.values(STATES));
const VALID_WF_STATES = new Set(Object.values(workflow.WF_STATES)); // M10: 工作流 status 白名單
const MAX_WORKER_ID_LENGTH = 128;

/**
 * 工作流全部完成後，聚合所有步驟成果並組合成一則完整回覆。
 * 只取「最後一個有實質 result 的步驟」作為主體（通常是潤飾/整合步驟），
 * 前置步驟的 result 折疊於「過程摘要」區塊供參考。
 */
function buildWorkflowFinalReply(wf, storeRef) {
    if (!wf) return '[工作流已完成]';

    const completedSteps = (wf.steps || []).filter(s => s.status === 'completed' && s.task_uid);
    if (completedSteps.length === 0) return `[工作流「${wf.name}」已完成，無步驟結果]`;

    // 收集各步驟結果
    const stepResults = completedSteps.map(s => {
        const r = storeRef.getRecord(s.task_uid);
        return { name: s.name, result: (r && r.result) ? r.result.trim() : '' };
    }).filter(s => s.result);

    if (stepResults.length === 0) return `[工作流「${wf.name}」已完成，步驟無輸出]`;

    // 最後一步視為「最終成果」，前面的步驟作為「過程記錄」
    const finalStep = stepResults[stepResults.length - 1];
    const intermediateSteps = stepResults.slice(0, -1);

    let msg = `✅ **工作流完成：${wf.name}**\n\n`;
    msg += `---\n\n`;
    msg += finalStep.result;

    if (intermediateSteps.length > 0) {
        msg += `\n\n---\n\n<details>\n<summary>📋 過程記錄（${intermediateSteps.length} 個步驟）</summary>\n\n`;
        for (const s of intermediateSteps) {
            const preview = s.result.slice(0, 600) + (s.result.length > 600 ? '\n…[略]' : '');
            msg += `**${s.name}**\n${preview}\n\n`;
        }
        msg += `</details>`;
    }

    return msg;
}

/**
 * L1: 可選注入 Gun 相關依賴，將 /api/connect、/api/send 註冊至 dispatch map
 * @param {object} app - Express app
 * @param {object} [opts] - 若提供 gun/SEA/getMyPair/chatRoomName/generateId/startMessageLoop 則註冊 connect 與 send
 *                          可額外提供 sendReply(text) async fn，供 /processed 在任務完成時透過 bot 穩定連線回傳結果
 */
function mount(app, opts = {}) {
    // 健康檢查
    app.get('/api/health', (req, res) => {
        const queueStats = req.app.locals.classifyQueue
            ? req.app.locals.classifyQueue.stats()
            : { pending: 0, running: 0 };

        res.json({
            status: 'ok',
            connected: !!req.app.locals.sharedSecret,
            listening: req.app.locals.isListening || false,
            gunConnected: !!req.app.locals.gunConnected, // M4: Gun.js relay 連線狀態
            pendingTasks: store.queryRecords({ state: STATES.PENDING }).total,
            claimedTasks: store.queryRecords({ state: STATES.CLAIMED }).total,
            activeCronJobs: Object.keys(req.app.locals.activeCronJobs || {}).length,
            classifyQueue: queueStats,
            uptime: process.uptime()
        });
    });

    // 列出可用 Skill（除錯／維運用）
    app.get('/api/skills', (req, res) => {
        const list = skills.listSkills();
        res.json({ total: list.length, skills: list });
    });

    // 近期任務記憶查詢（Worker 執行前注入上下文，避免重複執行相同任務）
    app.get('/api/memory/recent', (req, res) => {
        const limit = Math.max(1, Math.min(parseInt(req.query.limit, 10) || 5, 20));
        const mem = loadBotMemory();
        const tasks = (mem.recent_tasks || []).slice(0, limit);
        res.json({ total: mem.recent_tasks ? mem.recent_tasks.length : 0, recent_tasks: tasks });
    });

    // 查詢任務記錄（支援 state 篩選 + D3 分頁）
    app.get('/api/records', (req, res) => {
        const filters = {};
        if (req.query.is_processed !== undefined) {
            filters.is_processed = req.query.is_processed === 'true';
        }
        if (req.query.is_research !== undefined) {
            filters.is_research = req.query.is_research === 'true';
        }
        if (req.query.state !== undefined) {
            if (!VALID_STATES.has(req.query.state)) {
                return res.status(400).json({ error: `不合法的 state 值，可選：${[...VALID_STATES].join(', ')}` });
            }
            filters.state = req.query.state;
        }
        // D3: 分頁。M7: 預設 limit=50，避免未帶 limit 時回傳全部
        filters.limit = req.query.limit !== undefined ? Math.max(1, Math.min(parseInt(req.query.limit, 10) || 50, 500)) : 50;
        filters.offset = req.query.offset !== undefined ? Math.max(0, parseInt(req.query.offset, 10) || 0) : 0;
        const { total, records } = store.queryRecords(filters);
        res.json({ total, count: records.length, records });
    });

    // 查詢單筆任務 (Audit 6.5: 新增端點)
    app.get('/api/records/:uid', (req, res) => {
        const record = store.getRecord(req.params.uid);
        if (!record) return res.status(404).json({ error: '找不到指定的任務' });
        res.json({ record });
    });

    // 下載任務檔案 (含路徑穿越防護)
    app.get('/api/files/:filename', (req, res) => {
        const filename = req.params.filename;
        if (filename.includes('/') || filename.includes('\\') || filename.includes('..')) {
            return res.status(400).json({ error: '不合法的檔案名稱' });
        }
        const filePath = path.resolve(path.join(store.TASKS_DIR, filename));
        const tasksDirResolved = path.resolve(store.TASKS_DIR);
        if (!filePath.startsWith(tasksDirResolved + path.sep) && filePath !== tasksDirResolved) {
            return res.status(400).json({ error: '不合法的檔案路徑' });
        }
        if (fs.existsSync(filePath)) {
            res.sendFile(filePath);
        } else {
            res.status(404).json({ error: '找不到該任務檔案' });
        }
    });

    // ---- s11: poll-claim-work 端點 ----

    // 認領任務
    app.patch('/api/records/:uid/claim', (req, res) => {
        const { worker_id } = req.body || {};
        if (!worker_id) {
            return res.status(400).json({ error: '缺少 worker_id 參數' });
        }
        // S7: worker_id 長度驗證
        if (typeof worker_id !== 'string' || worker_id.length > MAX_WORKER_ID_LENGTH) {
            return res.status(400).json({ error: `worker_id 長度不可超過 ${MAX_WORKER_ID_LENGTH} 字元` });
        }
        const result = store.claimRecord(req.params.uid, worker_id);
        const statusMap = {
            claimed: () => res.json({
                success: true,
                message: `任務已由 ${worker_id} 認領`,
                claim_generation: result.claim_generation
            }),
            already_claimed: () => res.status(409).json({ error: '任務已被其他 worker 認領' }),
            not_found: () => res.status(404).json({ error: '找不到指定的任務' }),
            invalid_state: () => res.status(400).json({ error: '任務狀態不允許認領' })
        };
        const handler = statusMap[result.status];
        if (handler) {
            handler();
        } else {
            res.status(500).json({ error: '未知的認領結果' });
        }
    });

    // FSM 狀態轉換（通用）+ 工作流推進
    app.patch('/api/records/:uid/state', (req, res) => {
        const { state, worker_id, claim_generation, result } = req.body || {};
        if (!state) {
            return res.status(400).json({ error: '缺少 state 參數' });
        }
        if (!VALID_STATES.has(state)) {
            return res.status(400).json({ error: `不合法的 state 值，可選：${[...VALID_STATES].join(', ')}` });
        }
        // S7: worker_id 長度驗證
        if (worker_id && (typeof worker_id !== 'string' || worker_id.length > MAX_WORKER_ID_LENGTH)) {
            return res.status(400).json({ error: `worker_id 長度不可超過 ${MAX_WORKER_ID_LENGTH} 字元` });
        }
        try {
            const extra = {};
            if (worker_id) extra.worker_id = worker_id;
            if (claim_generation !== undefined) extra.claim_generation = claim_generation;
            if (result !== undefined) extra.result = result;
            const rec = store.transitionState(req.params.uid, state, extra);
            if (!rec) return res.status(404).json({ error: '找不到指定的任務' });

            // 工作流推進：任務完成或失敗時通知工作流引擎
            if (state === STATES.COMPLETED) {
                try { workflow.onTaskCompleted(req.params.uid); } catch (e) {
                    console.error('[workflow] 推進失敗:', e.message);
                }
            } else if (state === STATES.FAILED) {
                try { workflow.onTaskFailed(req.params.uid); } catch (e) {
                    console.error('[workflow] 失敗處理異常:', e.message);
                }
            }

            res.json({ success: true, record: rec });
        } catch (err) {
            res.status(400).json({ error: err.message });
        }
    });

    // 標記已處理（向後相容，支援 claim_generation、result 驗證）+ 工作流推進
    app.patch('/api/records/:uid/processed', (req, res) => {
        try {
            const { claim_generation, result } = req.body || {};
            const uid = req.params.uid;
            const resultStatus = store.markProcessed(uid, claim_generation, result);
            const { sendReply } = opts;
            const statusMap = {
                completed: () => {
                    // 工作流推進：回傳 { workflowId, completed, stepsStarted } 或 null（非工作流任務）
                    let wfResult = null;
                    try { wfResult = workflow.onTaskCompleted(uid); } catch (e) {
                        console.error('[workflow] 推進失敗:', e.message);
                    }

                    const rec = store.getRecord(uid);
                    const taskContent = store.getTaskContent(uid) || uid;
                    const resultStr = Array.isArray(result)
                        ? result.join('\n')
                        : (typeof result === 'string' ? result : String(result));

                    // ---- 工作流任務：依步驟位置決定是否回傳聊天室 ----
                    if (wfResult !== null) {
                        if (wfResult.completed) {
                            // 整個工作流完成：聚合所有步驟結果，發一次完整成果
                            if (typeof sendReply === 'function') {
                                const wf = workflow.queryWorkflows({}).workflows.find(w => w.id === wfResult.workflowId);
                                const finalMsg = buildWorkflowFinalReply(wf, store);
                                sendReply(finalMsg)
                                    .catch(e => console.error('[routes/processed] workflow sendReply 失敗:', e.message));
                            }
                            // 知識庫：研究型工作流一律存 KB（以工作流名稱為主題）
                            const wf = workflow.queryWorkflows({}).workflows.find(w => w.id === wfResult.workflowId);
                            if (wf && shouldSaveToKB(wf.name, true, null)) {
                                const allResults = (wf.steps || [])
                                    .filter(s => s.status === 'completed' && s.task_uid)
                                    .map(s => {
                                        const r = store.getRecord(s.task_uid);
                                        return r && r.result ? `## ${s.name}\n${r.result}` : '';
                                    })
                                    .filter(Boolean)
                                    .join('\n\n');
                                if (allResults) saveToKnowledgeBase(wf.name, allResults);
                            }
                        }
                        // 中間步驟：不發聊天室回覆，靜默完成（暫存於 records.json）
                        saveBotMemory(taskContent, resultStr, rec && rec.is_research);
                        res.json({ success: true });
                        return;
                    }

                    // ---- 非工作流任務：原有邏輯不變 ----
                    if (result != null && typeof sendReply === 'function') {
                        const MAX_LEN = 6000;
                        const truncated = resultStr.length > MAX_LEN
                            ? resultStr.slice(0, MAX_LEN) + '\n...[內容過長，已截斷]'
                            : resultStr;

                        const taskLabel = taskContent.trim().slice(0, 80) + (taskContent.length > 80 ? '…' : '');

                        sendReply(`[系統回覆] 任務完畢\n**任務**：${taskLabel}\n\n**結果**：\n${truncated}`)
                            .catch(e => console.error('[routes/processed] sendReply 失敗:', e.message));

                        // 研究型一律存 KB；code 型一律存規劃結果至 KB；其餘依關鍵字
                        if (shouldSaveToKB(taskContent, rec && rec.is_research, rec && rec.task_type)) {
                            saveToKnowledgeBase(taskContent, resultStr);
                        }

                        // 儲存至機器人記憶（供 Worker 下次執行前注入上下文，避免重複）
                        saveBotMemory(taskContent, resultStr, rec && rec.is_research);
                    }
                    res.json({ success: true });
                },
                not_found: () => res.status(404).json({ error: '找不到指定的任務' }),
                stale_claim: () => res.status(409).json({ error: '認領已過期，此任務已被重新認領' }),
                invalid_state: () => res.status(400).json({ error: '只能標記 processing 狀態的任務為已完成' })
            };
            const handler = statusMap[resultStatus];
            if (handler) {
                handler();
            } else {
                res.status(500).json({ error: '未知的處理結果' });
            }
        } catch (err) {
            res.status(400).json({ error: err.message });
        }
    });

    // DLQ: 任務失敗端點（含自動重試 / Dead Letter Queue 邏輯）
    app.post('/api/records/:uid/fail', (req, res) => {
        const { worker_id, error } = req.body || {};
        const result = store.requeueOrDeadLetter(req.params.uid, worker_id, error);
        const rec = store.getRecord(req.params.uid);
        const retry_count = rec ? rec.retry_count : undefined;
        if (result === 'not_found') return res.status(404).json({ error: '找不到指定的任務' });
        if (result === 'invalid_state') return res.status(400).json({ error: '任務狀態不允許執行失敗處理' });
        res.json({ status: result, retry_count });
    });

    // S4: 取消任務（只允許 pending 狀態）
    app.delete('/api/records/:uid', (req, res) => {
        const result = store.removeRecord(req.params.uid);
        if (result === null) return res.status(404).json({ error: '找不到指定的任務' });
        if (result === 'not_cancellable') return res.status(400).json({ error: '只能取消 pending 狀態的任務' });
        if (result === 'workflow_task') return res.status(400).json({ error: '此任務屬於工作流，請取消工作流而非單獨刪除任務' });
        res.json({ success: true, message: `任務 ${req.params.uid} 已取消` });
    });

    // ---- 工作流管理 ----

    // 建立工作流
    app.post('/api/workflows', (req, res) => {
        const { name, steps } = req.body || {};
        if (!steps || !Array.isArray(steps)) {
            return res.status(400).json({ error: '缺少 steps 陣列' });
        }
        try {
            const wf = workflow.createWorkflow(name, steps);
            res.status(201).json({ success: true, workflow: wf });
        } catch (err) {
            res.status(400).json({ error: err.message });
        }
    });

    // 查詢工作流列表 (M10: status 白名單驗證)
    app.get('/api/workflows', (req, res) => {
        const filters = {};
        if (req.query.status) {
            if (!VALID_WF_STATES.has(req.query.status)) {
                return res.status(400).json({ error: `不合法的 status，可選：${[...VALID_WF_STATES].join(', ')}` });
            }
            filters.status = req.query.status;
        }
        if (req.query.limit) filters.limit = parseInt(req.query.limit, 10) || 20;
        if (req.query.offset) filters.offset = parseInt(req.query.offset, 10) || 0;
        const { total, workflows } = workflow.queryWorkflows(filters);
        res.json({ total, count: workflows.length, workflows });
    });

    // 查詢單一工作流
    app.get('/api/workflows/:id', (req, res) => {
        const wf = store.getWorkflow(req.params.id);
        if (!wf) return res.status(404).json({ error: '找不到指定的工作流' });
        res.json({ workflow: wf });
    });

    // 取消工作流
    app.delete('/api/workflows/:id', (req, res) => {
        const result = workflow.cancelWorkflow(req.params.id);
        if (result === 'not_found') return res.status(404).json({ error: '找不到指定的工作流' });
        if (result === 'not_cancellable') return res.status(400).json({ error: '只能取消 running 或 pending 的工作流' });
        res.json({ success: true, message: `工作流 ${req.params.id} 已取消` });
    });

    // Cron 排程管理
    app.get('/api/cron-jobs', (req, res) => {
        res.json({ total: store.cronJobs.length, jobs: store.cronJobs });
    });

    app.delete('/api/cron-jobs/:id', (req, res) => {
        const cronId = req.params.id;
        const activeCronJobs = req.app.locals.activeCronJobs || {};

        if (activeCronJobs[cronId]) {
            activeCronJobs[cronId].stop();
            delete activeCronJobs[cronId];
        }

        if (store.removeCronJob(cronId)) {
            res.json({ success: true, message: `排程 ${cronId} 已取消` });
        } else {
            res.status(404).json({ error: '找不到指定的排程' });
        }
    });

    // 單次定時任務管理
    app.get('/api/scheduled-tasks', (req, res) => {
        const filters = {};
        if (req.query.status) filters.status = req.query.status;
        if (req.query.limit !== undefined) filters.limit = Math.max(1, Math.min(parseInt(req.query.limit, 10) || 20, 100));
        if (req.query.offset !== undefined) filters.offset = Math.max(0, parseInt(req.query.offset, 10) || 0);
        const { total, scheduledTasks } = store.queryScheduledTasks(filters);
        res.json({ total, count: scheduledTasks.length, scheduledTasks });
    });

    app.get('/api/scheduled-tasks/:id', (req, res) => {
        const task = store.getScheduledTask(req.params.id);
        if (!task) return res.status(404).json({ error: '找不到指定的定時任務' });
        res.json({ scheduledTask: task });
    });

    app.delete('/api/scheduled-tasks/:id', (req, res) => {
        const ok = store.cancelScheduledTask(req.params.id);
        if (!ok) return res.status(404).json({ error: '找不到指定的定時任務或該任務已觸發/已取消，無法取消' });
        res.json({ success: true, message: `定時任務 ${req.params.id} 已取消` });
    });

    // 任務強化端點：保留原始意圖，補充技術細節與結構，絕不簡化或刪減需求
    const { classifier: classifierDep } = opts;
    if (classifierDep && typeof classifierDep.optimizeTask === 'function') {
        app.post('/api/tasks/optimize', async (req, res) => {
            const { task_content } = req.body || {};
            if (!task_content || typeof task_content !== 'string' || task_content.trim().length === 0) {
                return res.status(400).json({ error: '缺少 task_content 參數或內容為空' });
            }
            if (task_content.length > 50000) {
                return res.status(400).json({ error: 'task_content 不可超過 50000 字元' });
            }
            try {
                const result = await classifierDep.optimizeTask(task_content);
                res.json({
                    success: true,
                    original: task_content,
                    optimized: (result && result.optimized) || result,
                    research_keywords: (result && result.research_keywords) || [],
                    is_research: (result && result.is_research) || false
                });
            } catch (err) {
                console.error('[/api/tasks/optimize] 強化失敗:', err.message);
                res.status(500).json({ error: '任務強化失敗', original: task_content });
            }
        });
    }

    // L1: /api/connect 與 /api/send 由 bot 注入 Gun 依賴後註冊
    const { gun, SEA, getMyPair, chatRoomName, generateId, startMessageLoop } = opts;
    if (gun && SEA && typeof getMyPair === 'function' && chatRoomName && typeof generateId === 'function' && typeof startMessageLoop === 'function') {
        app.post('/api/connect', async (req, res) => {
            const { targetEpub } = req.body;
            if (!targetEpub || typeof targetEpub !== 'string') {
                return res.status(400).json({ error: '缺少 targetEpub 或格式不正確' });
            }
            if (targetEpub.length > 2048) {
                return res.status(400).json({ error: 'targetEpub 過長' });
            }
            if (app.locals.isListening) {
                return res.json({ success: true, message: '安全連線已存在，無需重複建立' });
            }
            const myPair = getMyPair();
            if (!myPair) return res.status(500).json({ error: '伺服器金鑰尚未就緒' });
            app.locals.sharedSecret = await SEA.secret(targetEpub, myPair);
            startMessageLoop();
            res.json({ success: true, message: '安全連線已建立' });
        });

        app.post('/api/send', async (req, res) => {
            const { text } = req.body;
            if (!text || typeof text !== 'string') {
                return res.status(400).json({ error: '缺少 text 參數或格式不正確' });
            }
            if (!app.locals.sharedSecret) return res.status(403).json({ error: '尚未建立安全連線' });
            try {
                const encrypted = await SEA.encrypt(text, app.locals.sharedSecret);
                gun.get(chatRoomName).get(generateId('msg')).put(encrypted);
                res.json({ success: true });
            } catch (err) {
                console.error('[/api/send] 加密失敗:', err.message);
                res.status(500).json({ error: '訊息加密失敗' });
            }
        });
    }
}

module.exports = { mount };
