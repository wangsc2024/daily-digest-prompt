/**
 * classifier.js — Groq 意圖分類器（跑 bot.js 的環境使用 Groq API）
 *
 * 意圖分類、簡答、工作流分解皆透過 Groq API；Worker 端執行由 Codex exec（登入方案）處理。
 * AI prompt 從 skills/*.md 按需載入（lib/skills）。
 *
 * 安全措施：
 * - 使用者輸入以 JSON.stringify 逃脫後插入 prompt，防止 prompt injection
 * - AI 回應做結構驗證，缺欄位時安全降級
 * - 30 秒逾時，429 時延遲重試
 */
const path = require('path');
const { DateTime } = require('luxon');
const Groq = require('groq-sdk');
const skills = require('./skills');

const GROQ_MODEL = process.env.GROQ_MODEL || 'llama-3.1-8b-instant';
const GROQ_TIMEOUT_MS = 30000;
const GROQ_429_RETRY_DELAY_MS = 22000;
const GROQ_429_MAX_RETRIES = 1;
const TIMEZONE = (process.env.TIMEZONE || 'Asia/Taipei').trim();
const SCHEDULED_MAX_DAYS = Math.max(1, Math.min(365, parseInt(process.env.SCHEDULED_MAX_DAYS || '7', 10) || 7));

let groq = null;

function init(apiKey) {
    groq = new Groq({ apiKey });
}

/** 載入 skill 並替換變數（委派給 lib/skills） */
function loadSkill(skillName, vars = {}) {
    return skills.loadSkill(skillName, vars);
}

function isValidScheduledAt(scheduledAt) {
    if (typeof scheduledAt !== 'string' || !scheduledAt.trim()) return false;
    const dt = DateTime.fromISO(scheduledAt.trim(), { zone: TIMEZONE });
    if (!dt.isValid) return false;
    const now = DateTime.now().setZone(TIMEZONE);
    if (dt <= now) return false;
    const maxEnd = now.plus({ days: SCHEDULED_MAX_DAYS });
    return dt <= maxEnd;
}

const VALID_INTENTS = new Set(['general', 'podcast', 'kb_answer', 'game', 'research']);

function validateDecision(parsed) {
    if (typeof parsed !== 'object' || parsed === null) return false;
    if (typeof parsed.task_content !== 'string' || parsed.task_content.length === 0) return false;
    if (typeof parsed.is_periodic !== 'boolean') return false;
    if (parsed.is_periodic && (typeof parsed.cron_expression !== 'string' || !parsed.cron_expression)) return false;
    if (parsed.is_scheduled !== undefined && typeof parsed.is_scheduled !== 'boolean') return false;
    if (parsed.is_periodic && parsed.is_scheduled) return false;
    if (parsed.is_scheduled && !isValidScheduledAt(parsed.scheduled_at)) return false;
    if (parsed.intent !== undefined && !VALID_INTENTS.has(parsed.intent)) return false;
    return true;
}

function extractJSON(text) {
    const trimmed = (text || '').trim();
    const start = trimmed.indexOf('{');
    if (start === -1) return null;
    let depth = 0;
    for (let i = start; i < trimmed.length; i++) {
        const ch = trimmed[i];
        if (ch === '{') depth++;
        else if (ch === '}') {
            depth--;
            if (depth === 0) {
                try {
                    return JSON.parse(trimmed.slice(start, i + 1));
                } catch {
                    return null;
                }
            }
        }
    }
    return null;
}

function is429QuotaError(err) {
    const msg = err && err.message ? String(err.message) : '';
    return msg.includes('429') || msg.includes('rate_limit') || msg.includes('quota');
}

async function callGroq(promptOrMessages, options = {}) {
    const { jsonMode = false, timeoutMs = GROQ_TIMEOUT_MS, maxTokens = 2048, systemPrompt = null } = options;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`Groq API 逾時 (${timeoutMs}ms)`)), timeoutMs)
    );
    let messages;
    if (Array.isArray(promptOrMessages)) {
        messages = promptOrMessages;
    } else {
        messages = [];
        if (systemPrompt) messages.push({ role: 'system', content: systemPrompt });
        messages.push({ role: 'user', content: promptOrMessages });
    }
    const params = {
        model: GROQ_MODEL,
        messages,
        max_tokens: maxTokens,
        ...(jsonMode ? { response_format: { type: 'json_object' } } : {}),
    };
    try {
        const completion = await Promise.race([
            groq.chat.completions.create(params, { signal: controller.signal }),
            timeoutPromise
        ]);
        clearTimeout(timeout);
        const content = completion?.choices?.[0]?.message?.content;
        return typeof content === 'string' ? content : '';
    } catch (err) {
        clearTimeout(timeout);
        if (err.name === 'AbortError' || (err.message && err.message.includes('逾時'))) {
            throw new Error(`Groq API 逾時 (${timeoutMs}ms)`);
        }
        throw err;
    }
}

async function classify(userMessage, _429RetriesLeft = GROQ_429_MAX_RETRIES) {
    if (!groq) throw new Error('Classifier 未初始化，請先呼叫 init()');
    const now = DateTime.now().setZone(TIMEZONE);
    const currentDatetime = now.toISO();
    const prompt = loadSkill('intent-classifier', {
        userMessage,
        currentDatetime: currentDatetime || now.toFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZZ"),
        timezone: TIMEZONE
    });

    let text;
    try {
        text = await callGroq(prompt, { jsonMode: true });
    } catch (err) {
        if (is429QuotaError(err) && _429RetriesLeft > 0) {
            console.warn(`[classify] 配額限制 (429)，${GROQ_429_RETRY_DELAY_MS / 1000} 秒後重試 (剩 ${_429RetriesLeft} 次)...`);
            await new Promise(r => setTimeout(r, GROQ_429_RETRY_DELAY_MS));
            return classify(userMessage, _429RetriesLeft - 1);
        }
        throw err;
    }

    const parsed = extractJSON(text);
    const fallback = {
        is_periodic: false,
        cron_expression: '',
        is_scheduled: false,
        scheduled_at: '',
        intent: 'general',
        task_content: userMessage,
        _degraded: true
    };
    if (!parsed) {
        console.error('[classify] JSON 解析失敗，降級為一般任務');
        return fallback;
    }
    if (!validateDecision(parsed)) {
        console.error('[classify] 回應缺少必要欄位，降級為一般任務');
        return fallback;
    }
    if (parsed.is_scheduled === undefined) parsed.is_scheduled = false;
    if (parsed.scheduled_at === undefined) parsed.scheduled_at = '';
    if (parsed.cron_expression === undefined) parsed.cron_expression = '';
    if (!VALID_INTENTS.has(parsed.intent)) parsed.intent = 'general';
    return parsed;
}

const QUICK_ANSWER_TIMEOUT_MS = 15000;
const QUICK_ANSWER_SYSTEM_PROMPT =
    '你是一個簡潔的助理。請「直接回答」以下問題，用一至三句話給出實質內容。' +
    '不要只重述、改寫或總結問題，也不要回覆「您想了解的是…」這類句子。' +
    '若為天氣、常識、建議類問題，請依你的知識簡要回答。' +
    '若問題涉及之前的對話內容，請根據上下文回答。';

async function answerQuestion(userMessage, conversationHistory) {
    if (!groq || !userMessage || typeof userMessage !== 'string') return null;
    const trimmed = userMessage.trim();
    if (trimmed.length === 0) return null;

    if (Array.isArray(conversationHistory) && conversationHistory.length > 0) {
        // 有對話歷史：構建多輪訊息，讓 LLM 理解上下文
        const messages = [{ role: 'system', content: QUICK_ANSWER_SYSTEM_PROMPT }];
        for (const turn of conversationHistory) {
            messages.push({ role: turn.role === 'user' ? 'user' : 'assistant', content: turn.text });
        }
        messages.push({ role: 'user', content: trimmed });
        try {
            const text = await callGroq(messages, { timeoutMs: QUICK_ANSWER_TIMEOUT_MS });
            const out = text ? String(text).trim() : '';
            return out.length > 0 ? out : null;
        } catch (err) {
            console.error('[classifier] quick-answer (with history) 失敗:', err.message);
            return null;
        }
    } else {
        // 無歷史：保留原始行為
        const prompt = loadSkill('quick-answer', { userMessage: trimmed });
        try {
            const text = await callGroq(prompt, { timeoutMs: QUICK_ANSWER_TIMEOUT_MS });
            const out = text ? String(text).trim() : '';
            return out.length > 0 ? out : null;
        } catch (err) {
            console.error('[classifier] quick-answer 失敗:', err.message);
            return null;
        }
    }
}


const OPTIMIZE_TASK_TIMEOUT_MS = 45000;
const OPTIMIZE_TASK_MAX_TOKENS = 8192;
const RESEARCH_SEP = '---RESEARCH_KEYWORDS---';
const OPTIMIZE_TASK_SYSTEM_PROMPT =
    '你是任務描述強化專家。你的唯一工作是讓任務更清晰易執行。' +
    '你必須完整保留原始任務的所有需求、目標與意圖，絕對不可刪除、合併、簡化或替換任何需求。' +
    '若你無法在完全不改變原意的前提下強化，請原文回傳原始任務，不要做任何修改。' +
    '若任務含有研究意圖（任務描述包含：研究、查詢、了解、分析、調查、學習、探索、比較、評估任何技術/工具/概念），' +
    '額外輸出 JSON 尾碼，格式固定如下（主體強化文字在前，JSON 在後，以 ' + RESEARCH_SEP + ' 分隔）：\n' +
    RESEARCH_SEP + '\n' +
    '{"keywords": ["關鍵詞1", "關鍵詞2", "關鍵詞3"], "is_research": true}\n' +
    '若無研究意圖，不輸出分隔符與 JSON，直接回傳強化後的純文字。';
const TASK_CONTENT_MAX_CHARS = 50000;

/**
 * 強化任務描述：保留原始意圖，補充技術細節與結構，絕不簡化或刪減需求。
 * 若任務含研究意圖，額外解析 research_keywords 供 Worker 執行 KB 深化。
 * @param {string} taskContent - 原始任務內容
 * @returns {Promise<{optimized: string, research_keywords: string[], is_research: boolean}>}
 *   失敗時 optimized 為原始內容，research_keywords 為空陣列，is_research 為 false
 */
async function optimizeTask(taskContent) {
    if (!groq) throw new Error('Classifier 未初始化，請先呼叫 init()');
    if (!taskContent || typeof taskContent !== 'string') {
        return { optimized: taskContent, research_keywords: [], is_research: false };
    }
    const trimmed = taskContent.trim();
    if (trimmed.length === 0) {
        return { optimized: taskContent, research_keywords: [], is_research: false };
    }
    // 過短的任務不需要優化（< 20 字元通常是簡單指令）
    if (trimmed.length < 20) {
        return { optimized: taskContent, research_keywords: [], is_research: false };
    }

    const truncated = trimmed.length > TASK_CONTENT_MAX_CHARS
        ? trimmed.slice(0, TASK_CONTENT_MAX_CHARS) + '\n[...內容過長已截斷]'
        : trimmed;

    const prompt = loadSkill('task-optimizer', { taskContent: truncated });
    try {
        const text = await callGroq(prompt, {
            timeoutMs: OPTIMIZE_TASK_TIMEOUT_MS,
            maxTokens: OPTIMIZE_TASK_MAX_TOKENS,
            systemPrompt: OPTIMIZE_TASK_SYSTEM_PROMPT,
        });
        const result = text ? String(text).trim() : '';
        if (result.length === 0) {
            console.warn('[optimizeTask] AI 回傳空內容，使用原始任務');
            return { optimized: taskContent, research_keywords: [], is_research: false };
        }
        if (result.includes(RESEARCH_SEP)) {
            const [optimizedText, jsonPart] = result.split(RESEARCH_SEP);
            try {
                const parsed = JSON.parse(jsonPart.trim());
                return {
                    optimized: optimizedText.trim(),
                    research_keywords: Array.isArray(parsed.keywords) ? parsed.keywords : [],
                    is_research: parsed.is_research === true
                };
            } catch {
                return { optimized: result, research_keywords: [], is_research: false };
            }
        }
        return { optimized: result, research_keywords: [], is_research: false };
    } catch (err) {
        console.error('[optimizeTask] 強化失敗，使用原始任務:', err.message);
        return { optimized: taskContent, research_keywords: [], is_research: false };
    }
}

module.exports = {
    init,
    loadSkill,
    listSkills: skills.listSkills,
    clearSkillCache: skills.clearCache,
    classify,
    answerQuestion,
    optimizeTask,
    extractJSON,
    validateDecision
};
