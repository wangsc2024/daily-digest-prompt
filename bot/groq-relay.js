/**
 * groq-relay.js — Groq API 本機 HTTP Relay 服務
 *
 * 作用：持有 GROQ_API_KEY，讓 Claude Code Agent 透過 curl 呼叫，
 *       避免 API KEY 暴露在 Agent prompt 或被 pre_read_guard.py 攔截。
 *
 * 端點：
 *   POST /groq/chat   → {mode, content} → {result}
 *   GET  /groq/health → {"status":"ok", "model":"..."}
 *
 * 模式（mode）：
 *   summarize  — 一句話摘要（正體中文）
 *   translate  — 英文轉正體中文
 *   classify   — 主題分類（回傳 JSON {tags:[]}）
 *   extract    — 結構化萃取（回傳 JSON）
 *
 * 啟動：node bot/groq-relay.js
 * 或整合到 bot.js 以子進程方式啟動。
 */

// 優先讀 bot/.env，其次讀專案根目錄 .env（與 bot.js 相同的搜尋順序）
require('dotenv').config({ path: require('path').join(__dirname, '.env') });
require('dotenv').config({ path: require('path').join(__dirname, '../.env') });

const express = require('express');
const rateLimit = require('express-rate-limit');
const Groq = require('groq-sdk');

const PORT = parseInt(process.env.GROQ_RELAY_PORT || '3002', 10);
const GROQ_MODEL = process.env.GROQ_MODEL || 'llama-3.1-8b-instant';
const GROQ_RELAY_CACHE_TTL_MS = 5 * 60 * 1000; // 5 分鐘快取
const GROQ_TIMEOUT_MS = 15000;
const GROQ_MAX_TOKENS = 2048;
const HEALTH_PROBE_TTL_MS = 5 * 60 * 1000; // 健康探測結果快取 5 分鐘

const apiKey = (process.env.GROQ_API_KEY || '').trim();
if (!apiKey) {
    console.error('[groq-relay] 錯誤：請在 .env 中設定 GROQ_API_KEY');
    process.exit(1);
}

const groq = new Groq({ apiKey });
const app = express();
app.use(express.json({ limit: '1mb' }));

// 速率限制：免費方案 5 req/min，付費可調高（環境變數 GROQ_RELAY_RATE_LIMIT）
// 注意：僅套用到 /groq/chat，health 端點不計入配額
const limiter = rateLimit({
    windowMs: 60 * 1000,
    max: parseInt(process.env.GROQ_RELAY_RATE_LIMIT || '5', 10),
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: '速率限制：請稍後再試（Groq 免費方案 5 req/min）' },
});

// 健康探測狀態（5 分鐘 TTL 快取，避免每次 health 請求都消耗 API 配額）
let _healthState = {
    api_reachable: null,  // null = 尚未探測
    last_check: null,
    latency_ms: null,
    error: null,
    checked_at: 0,
};

async function probeApi() {
    const start = Date.now();
    try {
        await Promise.race([
            groq.chat.completions.create({
                model: GROQ_MODEL,
                messages: [{ role: 'user', content: 'hi' }],
                max_tokens: 1,
            }),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('health probe 逾時 (5s)')), 5000)
            ),
        ]);
        _healthState = {
            api_reachable: true,
            last_check: new Date().toISOString(),
            latency_ms: Date.now() - start,
            error: null,
            checked_at: Date.now(),
        };
    } catch (err) {
        _healthState = {
            api_reachable: false,
            last_check: new Date().toISOString(),
            latency_ms: Date.now() - start,
            error: err.message,
            checked_at: Date.now(),
        };
        console.warn('[groq-relay] health probe 失敗:', err.message);
    }
}

// 5 分鐘記憶體快取（key = mode + content 前 200 字）
const _cache = new Map();

function cacheKey(mode, content) {
    return `${mode}::${String(content).slice(0, 200)}`;
}

function getCached(mode, content) {
    const k = cacheKey(mode, content);
    const entry = _cache.get(k);
    if (!entry) return null;
    if (Date.now() - entry.ts > GROQ_RELAY_CACHE_TTL_MS) {
        _cache.delete(k);
        return null;
    }
    return entry.result;
}

function setCache(mode, content, result) {
    const k = cacheKey(mode, content);
    _cache.set(k, { result, ts: Date.now() });
    // 限制快取大小，避免記憶體洩漏
    if (_cache.size > 500) {
        const firstKey = _cache.keys().next().value;
        _cache.delete(firstKey);
    }
}

// 各模式的 system prompt
const SYSTEM_PROMPTS = {
    summarize: '你是精簡摘要助手。將輸入內容用一句正體中文（30字以內）精確摘要。只回覆摘要本身，不加說明。',
    translate: '你是技術翻譯助手。將英文翻譯為正體中文，保留技術術語（如 LLM、RAG、API 等）原文括弧附上。只回覆譯文，不加說明。',
    classify: '你是主題分類助手。將輸入內容分類並回傳 JSON 格式：{"tags":["標籤1","標籤2"]}。標籤使用正體中文，最多5個。只回覆 JSON，不加說明。',
    extract: '你是結構化萃取助手。從輸入內容中萃取關鍵資訊並回傳 JSON 格式：{"key_points":["要點1","要點2"],"summary":"摘要","confidence":"high|medium|low"}。只回覆 JSON，不加說明。',
    kb_score: '你是知識品質評分助手（v2）。評估知識庫筆記的品質與保留價值，以 JSON 回傳：' +
        '{"concept_count":N,"depth_level":"foundation|mechanism|application|optimization|synthesis",' +
        '"info_density":"high|medium|low","is_knowledge":true,' +
        '"is_derived":false,"retention_value":"high|medium|low","issues":["問題1"]}。' +
        '判斷標準：concept_count = 可辨識的獨立概念數；' +
        'depth_level = 知識深度（foundation/mechanism/application/optimization/synthesis）；' +
        'info_density = 資訊密度（high/medium/low）；' +
        'is_knowledge = 是否為知識性內容（false = 任務日誌/模板/樣板/純連結）；' +
        'is_derived = 是否為衍生內容（true = Podcast腳本/翻譯稿/對話改寫/自動生成等由既有知識改寫而成，無新增知識價值）；' +
        'retention_value = 保留價值（low = 衍生品/已有MP3等最終產物/口語對話格式不適合檢索; medium = 有一定價值但不完整; high = 原創可複用知識）；' +
        'issues = 具體問題列表。只回覆 JSON，不加說明。',
};

const VALID_MODES = new Set(Object.keys(SYSTEM_PROMPTS));

async function callGroq(mode, content) {
    const systemPrompt = SYSTEM_PROMPTS[mode];
    const isJson = (mode === 'classify' || mode === 'extract' || mode === 'kb_score');

    const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`Groq 逾時 (${GROQ_TIMEOUT_MS}ms)`)), GROQ_TIMEOUT_MS)
    );

    const params = {
        model: GROQ_MODEL,
        messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: String(content).slice(0, 8000) },
        ],
        max_tokens: GROQ_MAX_TOKENS,
        ...(isJson ? { response_format: { type: 'json_object' } } : {}),
    };

    const completion = await Promise.race([
        groq.chat.completions.create(params),
        timeoutPromise,
    ]);

    return (completion?.choices?.[0]?.message?.content || '').trim();
}

// POST /groq/chat（套用速率限制）
app.post('/groq/chat', limiter, async (req, res) => {
    const { mode, content } = req.body || {};

    if (!mode || !VALID_MODES.has(mode)) {
        return res.status(400).json({
            error: `無效 mode：${mode}，可用值：${[...VALID_MODES].join(', ')}`
        });
    }
    if (!content || typeof content !== 'string' || !content.trim()) {
        return res.status(400).json({ error: 'content 不可為空' });
    }

    // 快取命中
    const cached = getCached(mode, content);
    if (cached !== null) {
        return res.json({ result: cached, cached: true, model: GROQ_MODEL });
    }

    try {
        const result = await callGroq(mode, content);
        setCache(mode, content, result);
        res.json({ result, cached: false, model: GROQ_MODEL });
    } catch (err) {
        const is429 = err?.message?.includes('429') || err?.message?.includes('rate_limit');
        const status = is429 ? 429 : 500;
        console.error(`[groq-relay] callGroq 失敗 (mode=${mode}):`, err.message);
        res.status(status).json({
            error: err.message,
            mode,
            hint: is429 ? '已達 Groq 配額上限，請稍後再試' : '請檢查 GROQ_API_KEY 是否有效'
        });
    }
});

// GET /groq/health（不套用速率限制，TTL 5 分鐘探測一次真實 API）
app.get('/groq/health', async (_req, res) => {
    const stale = Date.now() - _healthState.checked_at > HEALTH_PROBE_TTL_MS;

    if (_healthState.api_reachable === null) {
        // 首次：等待探測完成後再回應
        await probeApi();
    } else if (stale) {
        // 非首次：背景更新，本次用舊結果即時回應
        probeApi();
    }

    const ok = _healthState.api_reachable !== false;
    res.status(ok ? 200 : 503).json({
        status: ok ? 'ok' : 'error',
        model: GROQ_MODEL,
        port: PORT,
        cache_size: _cache.size,
        rate_limit_per_min: parseInt(process.env.GROQ_RELAY_RATE_LIMIT || '5', 10),
        api_reachable: _healthState.api_reachable,
        api_latency_ms: _healthState.latency_ms,
        last_api_check: _healthState.last_check,
        ...(_healthState.error ? { api_error: _healthState.error } : {}),
    });
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`[groq-relay] 已啟動 → http://localhost:${PORT}/groq`);
    console.log(`[groq-relay] 模型：${GROQ_MODEL}，速率限制：${process.env.GROQ_RELAY_RATE_LIMIT || 5} req/min`);
    // 啟動後背景執行初始健康探測（不阻塞 listen）
    probeApi().then(() => {
        const state = _healthState;
        if (state.api_reachable) {
            console.log(`[groq-relay] API 連線正常（${state.latency_ms}ms）`);
        } else {
            console.warn(`[groq-relay] API 連線失敗：${state.error}`);
        }
    });
});

module.exports = app; // 供測試使用
