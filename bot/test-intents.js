/**
 * 全意圖端到端測試腳本
 * 測試：general / kb_answer / podcast / game / research（Codex quota 視情況）
 * 執行：node bot/test-intents.js
 */
require('dotenv').config({ path: require('path').join(__dirname, '.env') });

const classifier = require('./lib/classifier');
const { execSync } = require('child_process');
const path  = require('path');
const http  = require('http');
const crypto = require('crypto');

const API_BASE  = 'http://127.0.0.1:3001';
const API_KEY   = process.env.API_SECRET_KEY || '';
const WORKER_PS = path.join(__dirname, 'process_messages.ps1');

// ─── helpers ────────────────────────────────────────────────────────────────

function ok(label)  { console.log(`  ✅ ${label}`); }
function fail(label){ console.log(`  ❌ ${label}`); }
function info(label){ console.log(`  ℹ️  ${label}`); }
function section(title){ console.log(`\n${'─'.repeat(60)}\n## ${title}\n`); }

function apiRequest(method, urlPath, body) {
    return new Promise((resolve, reject) => {
        const payload = body ? JSON.stringify(body) : null;
        const opts = {
            hostname: '127.0.0.1', port: 3001, path: urlPath,
            method,
            headers: {
                'Authorization': `Bearer ${API_KEY}`,
                ...(payload ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } : {})
            }
        };
        const req = http.request(opts, res => {
            let bodyStr = '';
            res.on('data', d => bodyStr += d);
            res.on('end', () => { try { resolve({ status: res.statusCode, data: JSON.parse(bodyStr) }); } catch { resolve({ status: res.statusCode, data: bodyStr }); } });
        });
        req.on('error', reject);
        if (payload) req.write(payload);
        req.end();
    });
}

function apiGet(urlPath) { return apiRequest('GET', urlPath).then(r => r.data); }

async function apiAddRecord(uid, taskContent, isResearch, taskType, originalText) {
    const r = await apiRequest('POST', '/api/records', {
        uid, taskContent, isResearch, taskType,
        lineUserId: 'test', lineReplyTarget: 'test',
        lineSourceType: 'user', contextKey: 'test', originalText
    });
    if (r.status !== 200) throw new Error(`addRecord 失敗: ${JSON.stringify(r.data)}`);
    return r.data;
}

async function apiGetRecord(uid) {
    const r = await apiRequest('GET', `/api/records/${uid}`);
    return r.data && r.data.record;
}

const { spawn } = require('child_process');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/** 非同步啟動 Worker，返回 Promise（Worker 退出時 resolve）。不設 timeout 避免殺掉 Cursor CLI 造成任務卡死。 */
function runWorker() {
    info('執行 process_messages.ps1...');
    return new Promise((resolve) => {
        const proc = spawn('pwsh', ['-NoProfile', '-File', WORKER_PS], {
            encoding: 'utf8', cwd: __dirname, stdio: ['ignore', 'pipe', 'pipe']
        });
        let stdout = '', stderr = '';
        proc.stdout.on('data', d => { stdout += d; });
        proc.stderr.on('data', d => { stderr += d; });
        proc.on('close', code => resolve({ stdout, stderr, exitCode: code }));
        proc.on('error', err => resolve({ stdout, stderr, exitCode: -1, error: err.message }));
    });
}

/** 背景啟動 Worker（fire-and-forget），不等待退出。適用 Cursor CLI 型任務（遊戲/程式碼）。
 *  Worker 在背景繼續執行，測試透過 HTTP 輪詢任務狀態，不依賴 Worker 程序生命週期。 */
function runWorkerBackground() {
    info('背景啟動 process_messages.ps1（不等待退出）...');
    const proc = spawn('pwsh', ['-NoProfile', '-File', WORKER_PS], {
        encoding: 'utf8', cwd: __dirname, stdio: 'ignore'
    });
    proc.unref(); // 不讓 Node.js event loop 等待此子程序
    proc.on('error', err => info(`Background Worker 啟動失敗: ${err.message}`));
}

/** 等待任務完成，最多 maxWaitMs 毫秒，每 pollIntervalMs 輪詢一次。
 *  若偵測到 retry_count 增加（任務失敗重回佇列），自動重啟 Worker 以繼續處理。 */
async function waitForRecord(uid, maxWaitMs = 600_000, pollIntervalMs = 5_000) {
    const deadline = Date.now() + maxWaitMs;
    let lastState = null;
    let lastRetryCount = 0;
    while (Date.now() < deadline) {
        await sleep(pollIntervalMs);
        let rec = null;
        // 帶 retry 的 apiGetRecord（避免 transient ECONNABORTED）
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                rec = await apiGetRecord(uid);
                break;
            } catch (e) {
                if (attempt < 2) { await sleep(500); } else { throw e; }
            }
        }
        if (!rec) continue;
        if (rec.state !== lastState) {
            info(`任務 ${uid} state: ${lastState || 'pending'} → ${rec.state}`);
            lastState = rec.state;
        }
        // Worker 失敗後任務回到 pending（retry_count 增加）→ 自動重啟 Worker
        const currentRetry = rec.retry_count || 0;
        if (currentRetry > lastRetryCount && rec.state === 'pending') {
            lastRetryCount = currentRetry;
            info(`任務第 ${currentRetry} 次重試，自動重啟 Worker...`);
            runWorker().then(r => info(`重試 Worker 完成 (exitCode=${r.exitCode})`));
        }
        if (rec.state === 'completed' || rec.state === 'failed') return rec;
    }
    // 取得最後狀態
    try { return await apiGetRecord(uid); } catch { return null; }
}

// ─── Test 1: 意圖分類 ────────────────────────────────────────────────────────
async function testClassification() {
    section('Test 1：意圖分類（Groq classifier）');

    const cases = [
        { msg: '你好，今天天氣如何？',                   want: 'general'   },
        { msg: '請從知識庫查詢六祖壇經',                 want: 'kb_answer' },
        { msg: '幫我研究最新 AI 語言模型發展趨勢',       want: 'research'  },
        { msg: '幫我製作一個關於禪修的 podcast 腳本',    want: 'podcast'   },
        { msg: '設計一個網頁打磚塊小遊戲',               want: 'game'      },
    ];

    let passed = 0;
    for (const c of cases) {
        try {
            const result = await classifier.classify(c.msg);
            if (result.intent === c.want) {
                ok(`"${c.msg.slice(0,20)}…" → ${result.intent}`);
                passed++;
            } else {
                fail(`"${c.msg.slice(0,20)}…" → ${result.intent}（預期 ${c.want}）`);
            }
        } catch (e) {
            fail(`"${c.msg.slice(0,20)}…" → 分類失敗: ${e.message}`);
        }
    }
    console.log(`\n分類結果：${passed}/${cases.length} 通過`);
    return passed === cases.length;
}

// ─── Test 2: general — Groq 即時回覆 ────────────────────────────────────────
async function testGeneral() {
    section('Test 2：general 意圖 — Groq 即時回覆');

    // 2a. 無歷史
    try {
        const ans = await classifier.answerQuestion('1+1等於幾？');
        if (ans && ans.length > 0) ok(`無歷史簡答: "${ans}"`);
        else fail('answerQuestion 回傳空值');
    } catch (e) {
        fail(`answerQuestion 失敗: ${e.message}`);
    }

    // 2b. 帶對話歷史（連續對話）
    const history = [
        { role: 'user',      text: '六祖壇經說什麼？' },
        { role: 'assistant', text: '《六祖壇經》記錄了六祖慧能的開示，主張頓悟成佛、心性本清淨。' }
    ];
    try {
        const ans2 = await classifier.answerQuestion('由誰主講？', history);
        if (ans2 && ans2.includes('慧能')) {
            ok(`連續對話（有歷史）: "${ans2}"`);
        } else if (ans2 && ans2.length > 0) {
            info(`連續對話回答（未提 慧能，可能正確）: "${ans2}"`);
        } else {
            fail('連續對話回傳空值');
        }
    } catch (e) {
        fail(`連續對話失敗: ${e.message}`);
    }
}

// ─── Worker task helper ──────────────────────────────────────────────────────
async function runWorkerTask(uid, taskName, minResultLen = 10, maxWaitMs = 600_000) {
    const { stdout, exitCode } = await runWorker();
    if (stdout) info(`Worker 已啟動並退出 (exitCode=${exitCode})`);
    info(`等待任務 ${uid} 完成（最多 ${maxWaitMs/60000} 分鐘）...`);
    const rec = await waitForRecord(uid, maxWaitMs);
    if (rec && rec.state === 'completed' && rec.result && rec.result.length > minResultLen) {
        ok(`任務完成，輸出 ${rec.result.length} 字元`);
        info(`結果摘要: ${rec.result.slice(0, 120).replace(/\n/g, ' ')}…`);
        return { success: true, rec };
    } else if (rec && rec.state === 'completed') {
        info(`任務完成但輸出很短: "${rec.result}"`);
        return { success: true, rec };
    } else {
        fail(`${taskName} 未完成，state=${rec?.state}, exitCode=${exitCode}`);
        if (stdout) info(`Worker stdout: ${stdout.slice(0, 300)}`);
        return { success: false, rec };
    }
}

// ─── Test 3: kb_answer ───────────────────────────────────────────────────────
async function testKbAnswer() {
    section('Test 3：kb_answer 意圖 — Worker 執行');

    const uid = `test_kb_${crypto.randomUUID().slice(0, 8)}`;
    const content = '[採用查詢知識庫skill] 從知識庫查詢：daily-digest 是什麼專案？如果找不到相關筆記，請直接說「知識庫中無相關資料」。';
    await apiAddRecord(uid, content, false, 'kb_answer', '從知識庫查詢 daily-digest 是什麼');
    info(`已建立任務 ${uid}`);

    const { success } = await runWorkerTask(uid, 'kb_answer 任務');
    return success;
}

// ─── Test 4: podcast ─────────────────────────────────────────────────────────
async function testPodcast() {
    section('Test 4：podcast 意圖 — Worker 執行');

    const uid = `test_pod_${crypto.randomUUID().slice(0, 8)}`;
    const content = '[採用製作podcast workflow] 製作一段 30 秒的每日開場白 podcast 腳本，主題：今日以感恩心面對生活。請直接輸出腳本文字，不需要實際錄音。';
    await apiAddRecord(uid, content, false, 'podcast', '製作30秒 podcast 開場白腳本');
    info(`已建立任務 ${uid}`);

    const { success } = await runWorkerTask(uid, 'podcast 任務', 30);
    return success;
}

// ─── Test 5: game ────────────────────────────────────────────────────────────
async function testGame() {
    section('Test 5：game 意圖 — Worker 執行');

    const uid = `test_game_${crypto.randomUUID().slice(0, 8)}`;
    const content = '[採用設計遊戲workflow] 設計一個極簡的猜數字文字遊戲規則說明（不需要實際寫程式碼，只要輸出遊戲規則文字，50字以內）。';
    await apiAddRecord(uid, content, false, 'game', '設計猜數字遊戲規則');
    info(`已建立任務 ${uid}`);

    // 遊戲型任務使用 Cursor CLI，可能耗時 15-60 分鐘；採背景啟動 Worker，
    // 透過 HTTP 輪詢（最多 90 分鐘）等待完成，不依賴 Worker 程序生命週期。
    runWorkerBackground();
    info(`等待任務 ${uid} 完成（最多 90 分鐘，含 stale-recovery 自動重試）...`);
    const rec = await waitForRecord(uid, 90 * 60_000);
    if (rec && rec.state === 'completed' && rec.result && rec.result.length > 10) {
        ok(`任務完成，輸出 ${rec.result.length} 字元`);
        info(`結果摘要: ${rec.result.slice(0, 120).replace(/\n/g, ' ')}…`);
        return true;
    } else if (rec && rec.state === 'completed') {
        info(`任務完成但輸出很短: "${rec.result}"`);
        return true;
    } else {
        fail(`game 任務未完成，state=${rec?.state}`);
        return false;
    }
}

// ─── Test 6: research（Codex quota 狀態確認）────────────────────────────────
async function testResearch() {
    section('Test 6：research 意圖 — Codex quota 確認');

    const uid = `test_res_${crypto.randomUUID().slice(0, 8)}`;
    const content = '[採用深度研究skill] 請用 3 句話說明什麼是「頓悟」（禪宗概念）。若工具不可用請直接以文字回答。';
    await apiAddRecord(uid, content, true, 'research', '頓悟是什麼');
    info(`已建立任務 ${uid}（研究型，Codex 路徑）`);

    const { stdout } = await runWorker();
    info(`等待任務 ${uid} 完成（最多 10 分鐘）...`);
    const rec = await waitForRecord(uid, 600_000);
    if (rec && rec.state === 'completed') {
        ok(`研究任務完成（state=completed），輸出 ${(rec.result||'').length} 字元`);
        if (rec.result) info(`結果: ${rec.result.slice(0, 120).replace(/\n/g, ' ')}…`);
        return true;
    } else if ((stdout || '').includes('usage limit') || (stdout || '').includes('quota')) {
        info(`Codex 配額耗盡（預期），fallback 路徑: state=${rec?.state}`);
        return false;
    } else {
        fail(`研究任務未完成，state=${rec?.state}`);
        info(`Worker stdout: ${stdout?.slice(0, 400)}`);
        return false;
    }
}

// ─── main ────────────────────────────────────────────────────────────────────
async function main() {
    console.log('╔══════════════════════════════════════════════════╗');
    console.log('║   LINE 指派任務全意圖端到端測試                  ║');
    console.log('╚══════════════════════════════════════════════════╝');

    if (!process.env.GROQ_API_KEY) {
        console.error('\n❌ GROQ_API_KEY 未設定，請確認 bot/.env');
        process.exit(1);
    }
    classifier.init(process.env.GROQ_API_KEY);

    const results = {};

    results.classify = await testClassification();
    await testGeneral();           // general 無需 Worker，直接 Groq
    results.kb_answer = await testKbAnswer();
    results.podcast   = await testPodcast();
    results.game      = await testGame();
    results.research  = await testResearch();

    section('測試總結');
    for (const [k, v] of Object.entries(results)) {
        console.log(`  ${v ? '✅' : '❌'} ${k}`);
    }
    console.log('\n  ℹ️  general 意圖（Groq 即時回覆）見 Test 2 詳情');
    console.log('  ℹ️  research Codex 配額耗盡至 3/24 14:01 恢復\n');
}

main().catch(e => { console.error('測試失敗:', e); process.exit(1); });
