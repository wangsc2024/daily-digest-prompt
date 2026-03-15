/**
 * fsm.js — 任務狀態機
 *
 * 遵循 learn-claude-code s10: "Same request_id, two protocols"
 * 一個通用 FSM 原語處理任務生命週期的狀態轉換。
 *
 * 狀態流：pending → claimed → processing → completed | failed
 *         pending → completed (直接完成，向後相容 markProcessed)
 *         claimed → pending   (逾時釋放)
 */

const STATES = {
    PENDING:      'pending',
    CLAIMED:      'claimed',
    PROCESSING:   'processing',
    COMPLETED:    'completed',
    FAILED:       'failed',
    DEAD_LETTER:  'dead_letter'
};

// 合法的狀態轉換表（COMPLETED / DEAD_LETTER 為終態，明確標記空陣列）
const TRANSITIONS = {
    [STATES.PENDING]:      [STATES.CLAIMED, STATES.COMPLETED],
    [STATES.CLAIMED]:      [STATES.PROCESSING, STATES.PENDING, STATES.COMPLETED],
    [STATES.PROCESSING]:   [STATES.COMPLETED, STATES.FAILED, STATES.PENDING],
    [STATES.FAILED]:       [STATES.PENDING, STATES.DEAD_LETTER],
    [STATES.COMPLETED]:    [],
    [STATES.DEAD_LETTER]:  []
};

// 原則：每個任務預估執行時間約 5–30 分鐘；認領後應在數分鐘內轉為 processing。
// 任務認領預設逾時（毫秒）：認領後若未轉為 processing 超過此時長即釋放
const CLAIM_TIMEOUT_MS = 5 * 60 * 1000;  // 5 分鐘

// G26: 依任務類型動態設定 claim timeout（認領→processing 的允許時間，通常 < 1 min）
const CLAIM_TIMEOUTS = {
    research:  5 * 60 * 1000,  // 5 分鐘
    code:      5 * 60 * 1000,  // 5 分鐘
    game:      5 * 60 * 1000,  // 5 分鐘（遊戲型比照編碼型）
    podcast:   5 * 60 * 1000,  // 5 分鐘
    detail:    5 * 60 * 1000,  // 5 分鐘
    kb_answer: 5 * 60 * 1000,  // 5 分鐘
    general:   5 * 60 * 1000,  // 5 分鐘
};

// Processing 狀態超時（毫秒）：單任務預估 5–30 min，設 45 min 含緩衝；worker 崩潰時自動回收
const PROCESSING_TIMEOUTS = {
    research:  45 * 60 * 1000, // 45 分鐘
    code:      45 * 60 * 1000, // 45 分鐘
    game:      45 * 60 * 1000, // 45 分鐘（遊戲型比照編碼型）
    podcast:   45 * 60 * 1000, // 45 分鐘
    detail:    45 * 60 * 1000, // 45 分鐘
    kb_answer: 45 * 60 * 1000, // 45 分鐘
    general:   45 * 60 * 1000, // 45 分鐘
};

function getProcessingTimeout(taskType) {
    return PROCESSING_TIMEOUTS[taskType] || PROCESSING_TIMEOUTS.general;
}

/**
 * 依任務類型取得對應的 claim timeout（毫秒）
 * @param {string} [taskType] - 任務類型（'research' | 'code' | 'podcast' | 'detail' | 'kb_answer' | 'general'）
 * @returns {number}
 */
function getClaimTimeout(taskType) {
    return CLAIM_TIMEOUTS[taskType] || CLAIM_TIMEOUTS.general;
}

/**
 * 檢查狀態轉換是否合法
 * @param {string} from - 目前狀態
 * @param {string} to   - 目標狀態
 * @returns {boolean}
 */
function canTransition(from, to) {
    const allowed = TRANSITIONS[from];
    return !!allowed && allowed.includes(to);
}

/**
 * 執行狀態轉換，回傳新狀態或拋出錯誤
 * @param {string} current - 目前狀態
 * @param {string} target  - 目標狀態
 * @returns {string} target
 */
function transition(current, target) {
    if (!canTransition(current, target)) {
        throw new Error(`不合法的狀態轉換: ${current} → ${target}`);
    }
    return target;
}

/**
 * 檢查認領是否已逾時
 * @param {string} claimedAt - ISO 時間字串
 * @param {number} [timeoutMs] - 逾時毫秒數
 * @returns {boolean}
 */
function isClaimExpired(claimedAt, timeoutMs = CLAIM_TIMEOUT_MS) {
    if (!claimedAt) return true;
    const claimTime = new Date(claimedAt).getTime();
    // NaN 安全：無效日期字串 → 視為已逾時（安全預設值）
    if (Number.isNaN(claimTime)) return true;
    return Date.now() - claimTime > timeoutMs;
}

/**
 * 檢查值是否為合法的狀態
 * @param {string} value
 * @returns {boolean}
 */
function isValidState(value) {
    return Object.values(STATES).includes(value);
}

module.exports = {
    STATES,
    TRANSITIONS,
    CLAIM_TIMEOUT_MS,
    CLAIM_TIMEOUTS,
    PROCESSING_TIMEOUTS,
    canTransition,
    transition,
    isClaimExpired,
    isValidState,
    getClaimTimeout,
    getProcessingTimeout
};
