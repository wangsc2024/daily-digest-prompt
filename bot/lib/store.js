/**
 * store.js — 檔案式持久化層
 *
 * 職責：records / cron jobs / keypair 的 CRUD，
 * 以及 tasks_md 檔案的建立與刪除。
 *
 * 遵循 learn-claude-code：
 * - s07: "State survives /compact" — 檔案即真相來源
 * - s10: FSM 狀態轉換 — 每筆 record 帶有 state 欄位
 * - s11: Poll-claim-work — 支援 claim / release / timeout
 *
 * 安全措施：
 * - 原子寫入（write-to-temp + rename）防止並行寫入損壞
 * - claim_generation 計數器防止逾時釋放後的過期完成
 * - 狀態轉換日誌（append-only JSONL）
 * - S4: removeRecord 檢查 state 而非 is_processed
 * - S11: task_content 長度上限防止巨型任務檔案
 */
const fs = require('fs');
const path = require('path');
const { STATES, transition, isClaimExpired, getClaimTimeout } = require('./fsm');

// M9: 測試可透過環境變數使用隔離目錄，避免與生產 data 互相干擾
const DATA_DIR = process.env.WSC_BOT_DATA_DIR || path.join(__dirname, '..', 'data');
const TASKS_DIR = process.env.WSC_BOT_TASKS_DIR || path.join(__dirname, '..', 'tasks_md');
const RECORDS_PATH = path.join(DATA_DIR, 'records.json');
const CRON_JOBS_PATH = path.join(DATA_DIR, 'cron_jobs.json');
const SCHEDULED_TASKS_PATH = path.join(DATA_DIR, 'scheduled_tasks.json');
const WORKFLOWS_PATH = path.join(DATA_DIR, 'workflows.json');
const KEYPAIR_PATH = path.join(DATA_DIR, 'keypair.json');
const STATE_LOG_PATH = path.join(DATA_DIR, 'state_transitions.log');

// S11: task_content 寫入 .md 的最大長度 (bytes)
const MAX_TASK_CONTENT_LENGTH = 50000;

// 確保目錄存在
[DATA_DIR, TASKS_DIR].forEach(dir => {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// ---- 低階 I/O ----

function loadJSON(filePath, fallback) {
    try {
        if (fs.existsSync(filePath)) {
            return JSON.parse(fs.readFileSync(filePath, 'utf8'));
        }
    } catch (err) {
        console.error(`讀取 ${filePath} 失敗:`, err.message);
    }
    return fallback;
}

/** 原子寫入：先寫暫存檔再 rename，避免並行寫入損壞。失敗時拋錯以保持記憶體與磁碟一致 (C2)。 */
function saveJSON(filePath, data) {
    const tmp = filePath + '.tmp';
    try {
        fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
        fs.renameSync(tmp, filePath);
    } catch (err) {
        try { fs.unlinkSync(tmp); } catch {}
        const e = new Error(`寫入 ${filePath} 失敗: ${err.message}`);
        e.cause = err;
        throw e;
    }
}

/** 原子寫入文字檔（用於 .md 任務檔）。失敗時拋錯 (C2)。 */
function saveTextFile(filePath, content) {
    const tmp = filePath + '.tmp';
    try {
        fs.writeFileSync(tmp, content, 'utf8');
        fs.renameSync(tmp, filePath);
    } catch (err) {
        try { fs.unlinkSync(tmp); } catch {}
        const e = new Error(`寫入 ${filePath} 失敗: ${err.message}`);
        e.cause = err;
        throw e;
    }
}

// A9: 狀態轉換日誌最大大小 (10MB)，超過時輪替
const STATE_LOG_MAX_BYTES = 10 * 1024 * 1024;

/** 狀態轉換日誌（append-only JSONL），含輪替 */
function logTransition(uid, from, to, actor) {
    const entry = JSON.stringify({
        t: new Date().toISOString(), uid, from, to, actor
    });
    try {
        fs.appendFileSync(STATE_LOG_PATH, entry + '\n', 'utf8');
        // A9: 檢查日誌大小，超過上限時輪替
        const stats = fs.statSync(STATE_LOG_PATH);
        if (stats.size > STATE_LOG_MAX_BYTES) {
            const rotatedPath = STATE_LOG_PATH + '.1';
            try { fs.unlinkSync(rotatedPath); } catch {}
            fs.renameSync(STATE_LOG_PATH, rotatedPath);
        }
    } catch {}
}

// ---- 狀態載入 ----

const records = loadJSON(RECORDS_PATH, []);
const cronJobs = loadJSON(CRON_JOBS_PATH, []);
const scheduledTasks = loadJSON(SCHEDULED_TASKS_PATH, []);
const workflows = loadJSON(WORKFLOWS_PATH, []);

// 啟動時遷移：舊記錄若無 state 欄位則補上
records.forEach(r => {
    if (!r.state) {
        r.state = r.is_processed ? STATES.COMPLETED : STATES.PENDING;
    }
    if (r.claim_generation === undefined) {
        r.claim_generation = 0;
    }
});

// 啟動時去重：同一 UID 僅保留狀態最優先的記錄
(function deduplicateRecords() {
    const STATE_PRIORITY = {
        [STATES.COMPLETED]:  5,
        [STATES.PROCESSING]: 4,
        [STATES.CLAIMED]:    3,
        [STATES.FAILED]:     2,
        [STATES.PENDING]:    1
    };
    const bestByUid = new Map();
    for (let i = 0; i < records.length; i++) {
        const rec = records[i];
        const existing = bestByUid.get(rec.uid);
        if (!existing || (STATE_PRIORITY[rec.state] || 0) > (STATE_PRIORITY[existing.state] || 0)) {
            bestByUid.set(rec.uid, { idx: i, state: rec.state });
        }
    }
    if (bestByUid.size < records.length) {
        const keepIndices = new Set([...bestByUid.values()].map(v => v.idx));
        const removed = records.length - keepIndices.size;
        const deduped = records.filter((_, i) => keepIndices.has(i));
        records.length = 0;
        records.push(...deduped);
        saveJSON(RECORDS_PATH, records);
        console.log(`[啟動遷移] 移除了 ${removed} 筆重複記錄（UID 去重）`);
    }
})();

// ---- Records CRUD ----

function addRecord(uid, taskContent, isResearch) {
    if (records.some(r => r.uid === uid)) {
        console.log(`[addRecord] UID 已存在，跳過: ${uid}`);
        return;
    }

    const filename = `${uid}.md`;
    const filePath = path.join(TASKS_DIR, filename);
    // S11: 截斷過長的 task_content
    const safeContent = typeof taskContent === 'string'
        ? taskContent.slice(0, MAX_TASK_CONTENT_LENGTH)
        : String(taskContent).slice(0, MAX_TASK_CONTENT_LENGTH);
    saveTextFile(filePath, safeContent);

    records.push({
        uid,
        filename,
        time: new Date().toISOString(),
        state: STATES.PENDING,
        is_processed: false,
        is_research: !!isResearch,
        claimed_by: null,
        claimed_at: null,
        claim_generation: 0,
        result: null
    });
    try {
        saveJSON(RECORDS_PATH, records);
    } catch (err) {
        records.pop();
        if (fs.existsSync(filePath)) try { fs.unlinkSync(filePath); } catch {}
        throw err;
    }
    console.log(`[新增任務記錄]: ${filename}, 研究型: ${!!isResearch}`);
}

function markProcessed(uid, claimGeneration) {
    const idx = records.findIndex(m => m.uid === uid);
    if (idx === -1) return 'not_found';
    const rec = records[idx];

    // H2: 僅允許從 processing 轉為 completed，避免繞過 claim/worker 驗證
    if (rec.state !== STATES.PROCESSING) {
        return 'invalid_state';
    }

    // 驗證 claim_generation（防止逾時釋放後的過期完成；null/undefined 不強制比對，避免 PowerShell 傳 null 誤判）
    if (claimGeneration !== undefined && claimGeneration !== null && claimGeneration !== rec.claim_generation) {
        return 'stale_claim';
    }

    if (arguments.length >= 3 && arguments[2] != null) {
        rec.result = String(arguments[2]).slice(0, MAX_TASK_CONTENT_LENGTH);
    }
    const from = rec.state;
    rec.state = transition(rec.state, STATES.COMPLETED);
    rec.is_processed = true;
    rec.claimed_by = null;
    rec.claimed_at = null;
    saveJSON(RECORDS_PATH, records);
    logTransition(uid, from, STATES.COMPLETED, 'system');
    return 'completed';
}

/**
 * FSM 狀態轉換通用方法
 * @param {string} uid
 * @param {string} targetState
 * @param {object} [extra] - 額外欄位 (如 worker_id)
 * @returns {object|null} 更新後的 record，或 null
 */
function transitionState(uid, targetState, extra = {}) {
    const idx = records.findIndex(m => m.uid === uid);
    if (idx === -1) return null;
    const rec = records[idx];
    const from = rec.state;

    // 授權檢查：processing 轉換需由認領者執行
    if (from === STATES.CLAIMED && targetState === STATES.PROCESSING) {
        if (extra.worker_id && rec.claimed_by && extra.worker_id !== rec.claimed_by) {
            throw new Error(`Worker 不匹配：預期 ${rec.claimed_by}，收到 ${extra.worker_id}`);
        }
    }
    // 授權檢查：completed/failed 僅允許認領該任務的 worker 操作 (H1)；extra.force 時跳過（用於工作流取消 C3）
    if (from === STATES.PROCESSING && (targetState === STATES.COMPLETED || targetState === STATES.FAILED)) {
        if (!extra.force && extra.worker_id && rec.claimed_by && extra.worker_id !== rec.claimed_by) {
            throw new Error(`Worker 不匹配：僅認領者 ${rec.claimed_by} 可標記完成/失敗`);
        }
    }
    if (from === STATES.CLAIMED && targetState === STATES.FAILED && !extra.force) {
        if (extra.worker_id && rec.claimed_by && extra.worker_id !== rec.claimed_by) {
            throw new Error(`Worker 不匹配：僅認領者 ${rec.claimed_by} 可標記失敗`);
        }
    }

    // 完成時驗證 claim_generation（防止逾時釋放後的過期完成；null 不強制比對）
    if (targetState === STATES.COMPLETED && extra.claim_generation !== undefined && extra.claim_generation !== null) {
        if (extra.claim_generation !== rec.claim_generation) {
            throw new Error('認領已過期，此任務已被重新認領');
        }
    }

    rec.state = transition(rec.state, targetState);
    if (targetState === STATES.COMPLETED) {
        rec.is_processed = true;
        if (extra.result != null) rec.result = String(extra.result).slice(0, MAX_TASK_CONTENT_LENGTH);
    }
    if (targetState === STATES.FAILED || targetState === STATES.COMPLETED) {
        rec.claimed_by = null;
        rec.claimed_at = null;
    }
    saveJSON(RECORDS_PATH, records);
    logTransition(uid, from, targetState, extra.worker_id || 'api');
    return rec;
}

/**
 * 認領任務 (s11: poll-claim-work)
 * @param {string} uid
 * @param {string} workerId
 * @returns {{ status: string, claim_generation?: number }}
 */
function claimRecord(uid, workerId) {
    const idx = records.findIndex(m => m.uid === uid);
    if (idx === -1) return { status: 'not_found' };
    const rec = records[idx];

    // 如果已被認領且尚未逾時，拒絕
    const claimTtl = getClaimTimeout(rec.is_research ? 'research' : (rec.task_type || 'general'));
    if (rec.state === STATES.CLAIMED && !isClaimExpired(rec.claimed_at, claimTtl)) {
        return { status: 'already_claimed' };
    }

    // 如果逾時，先釋放回 pending 並遞增 generation
    if (rec.state === STATES.CLAIMED && isClaimExpired(rec.claimed_at, claimTtl)) {
        logTransition(uid, STATES.CLAIMED, STATES.PENDING, 'timeout');
        rec.state = STATES.PENDING;
        rec.claim_generation = (rec.claim_generation || 0) + 1;
    }

    const actualFrom = rec.state;
    try {
        rec.state = transition(rec.state, STATES.CLAIMED);
    } catch {
        return { status: 'invalid_state' };
    }

    rec.claimed_by = workerId;
    rec.claimed_at = new Date().toISOString();
    saveJSON(RECORDS_PATH, records);
    logTransition(uid, actualFrom, STATES.CLAIMED, workerId);
    return { status: 'claimed', claim_generation: rec.claim_generation };
}

/**
 * 釋放逾時的認領
 * @returns {number} 釋放的任務數
 */
function releaseExpiredClaims() {
    let released = 0;
    records.forEach(rec => {
        const ttl = getClaimTimeout(rec.is_research ? 'research' : (rec.task_type || 'general'));
        if (rec.state === STATES.CLAIMED && isClaimExpired(rec.claimed_at, ttl)) {
            logTransition(rec.uid, STATES.CLAIMED, STATES.PENDING, 'timeout');
            rec.state = STATES.PENDING;
            rec.claimed_by = null;
            rec.claimed_at = null;
            rec.claim_generation = (rec.claim_generation || 0) + 1;
            released++;
        }
    });
    if (released > 0) {
        saveJSON(RECORDS_PATH, records);
        console.log(`[逾時釋放] 已釋放 ${released} 個逾時認領`);
    }
    return released;
}

/**
 * 強制將任務標為失敗（僅供工作流取消使用，C3）。不驗證 worker_id，允許 pending/claimed/processing → failed。
 * @returns {boolean} 是否已處理（含 not_found）
 */
function forceTaskFailed(uid) {
    const idx = records.findIndex(m => m.uid === uid);
    if (idx === -1) return false;
    const rec = records[idx];
    if (rec.state === STATES.COMPLETED || rec.state === STATES.FAILED) return true;
    const from = rec.state;
    rec.state = STATES.FAILED;
    rec.claimed_by = null;
    rec.claimed_at = null;
    saveJSON(RECORDS_PATH, records);
    logTransition(uid, from, STATES.FAILED, 'workflow_cancel');
    return true;
}

/**
 * 強制將任務標記為失敗（用於工作流取消 C3），不驗證 worker_id
 * @param {string} uid
 * @returns {'removed'|object|null} removed=已刪除, object=更新後 record, null=not_found
 */
function forceFailRecord(uid) {
    const idx = records.findIndex(m => m.uid === uid);
    if (idx === -1) return null;
    const rec = records[idx];
    if (rec.state === STATES.PENDING) {
        const out = removeRecord(uid);
        return out === 'removed' ? 'removed' : null;
    }
    if (rec.state === STATES.CLAIMED || rec.state === STATES.PROCESSING) {
        return transitionState(uid, STATES.FAILED, { force: true });
    }
    return null;
}

// S4: removeRecord 檢查 state 而非 is_processed，只允許刪除 pending 任務。M2: 拒絕刪除工作流所屬任務。
function removeRecord(uid) {
    const idx = records.findIndex(m => m.uid === uid);
    if (idx === -1) return null;
    const rec = records[idx];

    if (rec.state !== STATES.PENDING) {
        return 'not_cancellable';
    }

    for (const wf of workflows) {
        if (wf.status === 'running' || wf.status === 'pending') {
            for (const step of wf.steps || []) {
                if (step.task_uid === uid) return 'workflow_task';
            }
        }
    }

    const filename = rec.filename;
    const filePath = path.join(TASKS_DIR, filename);
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);

    records.splice(idx, 1);
    saveJSON(RECORDS_PATH, records);
    return 'removed';
}

/**
 * 查詢任務記錄（支援篩選 + 分頁）
 * @returns {{ total: number, records: object[] }} total = 篩選後總數（分頁前）
 */
function queryRecords(filters = {}) {
    let results = records;
    if (filters.is_processed !== undefined) {
        results = results.filter(m => m.is_processed === filters.is_processed);
    }
    if (filters.is_research !== undefined) {
        results = results.filter(m => m.is_research === filters.is_research);
    }
    if (filters.state !== undefined) {
        results = results.filter(m => m.state === filters.state);
    }
    const total = results.length;
    // D3: 分頁支援
    if (filters.limit !== undefined) {
        const limit = Math.max(1, Math.min(filters.limit, 500));
        const offset = filters.offset || 0;
        results = results.slice(offset, offset + limit);
    }
    return { total, records: results };
}

/** 依 uid 取得單筆記錄 */
function getRecord(uid) {
    return records.find(r => r.uid === uid) || null;
}

function getTaskContent(uid) {
    const rec = records.find(r => r.uid === uid);
    if (!rec) return null;
    try {
        return fs.readFileSync(path.join(TASKS_DIR, rec.filename), 'utf8');
    } catch {
        return null;
    }
}

// ---- Cron Jobs CRUD ----

function addCronJob(job) {
    cronJobs.push(job);
    saveJSON(CRON_JOBS_PATH, cronJobs);
}

function removeCronJob(cronId) {
    const idx = cronJobs.findIndex(j => j.id === cronId);
    if (idx === -1) return false;
    cronJobs.splice(idx, 1);
    saveJSON(CRON_JOBS_PATH, cronJobs);
    return true;
}

// ---- Scheduled Tasks CRUD ----

const SCHEDULED_STATUS = { WAITING: 'waiting', TRIGGERED: 'triggered', CANCELLED: 'cancelled' };

function addScheduledTask(task) {
    scheduledTasks.push(task);
    saveJSON(SCHEDULED_TASKS_PATH, scheduledTasks);
}

function getScheduledTask(id) {
    return scheduledTasks.find(t => t.id === id) || null;
}

function removeScheduledTask(id) {
    const idx = scheduledTasks.findIndex(t => t.id === id);
    if (idx === -1) return false;
    scheduledTasks.splice(idx, 1);
    saveJSON(SCHEDULED_TASKS_PATH, scheduledTasks);
    return true;
}

function queryScheduledTasks(filters = {}) {
    let results = scheduledTasks;
    if (filters.status !== undefined) {
        results = results.filter(t => t.status === filters.status);
    }
    const total = results.length;
    if (filters.limit !== undefined) {
        const limit = Math.max(1, Math.min(filters.limit, 100));
        const offset = filters.offset || 0;
        results = results.slice(offset, offset + limit);
    }
    return { total, scheduledTasks: results };
}

function getDueScheduledTasks(nowIso) {
    const cutoff = nowIso || new Date().toISOString();
    return scheduledTasks.filter(
        t => t.status === SCHEDULED_STATUS.WAITING && t.scheduled_at <= cutoff
    );
}

function markScheduledTaskTriggered(id) {
    const idx = scheduledTasks.findIndex(t => t.id === id);
    if (idx === -1) return false;
    scheduledTasks[idx].status = SCHEDULED_STATUS.TRIGGERED;
    saveJSON(SCHEDULED_TASKS_PATH, scheduledTasks);
    return true;
}

function cancelScheduledTask(id) {
    const idx = scheduledTasks.findIndex(t => t.id === id);
    if (idx === -1) return false;
    if (scheduledTasks[idx].status !== SCHEDULED_STATUS.WAITING) return false;
    scheduledTasks[idx].status = SCHEDULED_STATUS.CANCELLED;
    saveJSON(SCHEDULED_TASKS_PATH, scheduledTasks);
    return true;
}

// ---- Workflows CRUD ----

function addWorkflow(workflow) {
    workflows.push(workflow);
    saveJSON(WORKFLOWS_PATH, workflows);
}

function getWorkflow(workflowId) {
    return workflows.find(w => w.id === workflowId) || null;
}

function saveWorkflows() {
    saveJSON(WORKFLOWS_PATH, workflows);
}

function removeWorkflow(workflowId) {
    const idx = workflows.findIndex(w => w.id === workflowId);
    if (idx === -1) return false;
    workflows.splice(idx, 1);
    saveJSON(WORKFLOWS_PATH, workflows);
    return true;
}

// ---- Keypair ----

function loadKeypair() { return loadJSON(KEYPAIR_PATH, null); }
function saveKeypair(pair) { saveJSON(KEYPAIR_PATH, pair); }

// ---- Exports ----

module.exports = {
    DATA_DIR,
    TASKS_DIR,
    records,
    cronJobs,
    scheduledTasks,
    workflows,
    addRecord,
    markProcessed,
    transitionState,
    claimRecord,
    releaseExpiredClaims,
    forceTaskFailed,
    removeRecord,
    forceFailRecord,
    queryRecords,
    getRecord,
    getTaskContent,
    addCronJob,
    removeCronJob,
    addScheduledTask,
    getScheduledTask,
    removeScheduledTask,
    queryScheduledTasks,
    getDueScheduledTasks,
    markScheduledTaskTriggered,
    cancelScheduledTask,
    SCHEDULED_STATUS,
    addWorkflow,
    getWorkflow,
    saveWorkflows,
    removeWorkflow,
    loadKeypair,
    saveKeypair
};
