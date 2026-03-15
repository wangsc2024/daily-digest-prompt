/**
 * 模擬從 LINE 指派各類型任務，並模擬 Worker 完成，驗證結果能回傳至 Gun/relay（及 LINE）。
 *
 * 流程：對 relay 的 LINE webhook 發送簽章請求 → relay 寫入 Gun (line_*) → bot 建立記錄
 *       → 本腳本對每筆 line_* pending 呼叫 claim → state=processing → /processed
 *       → bot 透過 sendReply 寫入 Gun (reply_*) → relay 解密並 postToLine(lineUserId)
 *
 * 環境變數（必填）：
 *   RELAY_LINE_WEBHOOK_URL   relay 的 LINE webhook（例：https://gun-relay-bxdc.onrender.com/api/line-webhook）
 *   LINE_CHANNEL_SECRET      relay 的 LINE 簽章用（與 relay .env 一致）
 *   LINE_TEST_USER_ID       模擬的 LINE userId（relay 會用此 ID 推回 LINE）
 *   BOT_API                  bot API 根網址（例：http://127.0.0.1:3001）
 *
 * 選填：
 *   RELAY_API_SECRET         relay 的 API_SECRET_KEY，用於 GET /api/replies 驗證
 *
 * 使用前：bot 與 relay 皆須運行；relay 需已與 bot 握手（sharedSecret 存在）。
 * 執行：node bot/test-line-task-types.mjs [inject|complete|full]
 *   inject  = 僅發送 6 則 LINE webhook 事件（各類型一則）
 *   complete = 僅對現有 pending line_* 模擬完成（不發送新任務）
 *   full    = inject + 等待記錄 + complete（預設）
 */

import crypto from 'crypto';

const BOT_API = process.env.BOT_API || 'http://127.0.0.1:3001';
const RELAY_LINE_WEBHOOK_URL = process.env.RELAY_LINE_WEBHOOK_URL;
const LINE_CHANNEL_SECRET = process.env.LINE_CHANNEL_SECRET;
const LINE_TEST_USER_ID = process.env.LINE_TEST_USER_ID || 'U00000000000000000000000000000000';
const RELAY_API_SECRET = process.env.RELAY_API_SECRET;

const TASK_SAMPLES = [
    { type: 'general', text: '今天天氣如何？' },
    { type: 'code', text: '寫一段 Python 印出 hello world' },
    { type: 'podcast', text: '幫我寫這集 podcast 的節目腳本，主題是晨間習慣' },
    { type: 'detail', text: '請詳細說明如何設定 Windows 排程器' },
    { type: 'kb_answer', text: '從知識庫中找關於屏東縣政的資料回答我' },
    { type: 'research', text: '研究一下 2025 年台灣資安法規趨勢，產出摘要' },
];

function signLineBody(rawBody, secret) {
    return crypto.createHmac('sha256', secret).update(rawBody).digest('base64');
}

async function fetchJson(url, opts = {}, timeout = 15000) {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), timeout);
    try {
        const res = await fetch(url, { ...opts, signal: ctrl.signal });
        clearTimeout(tid);
        if (opts.raw) return res;
        const text = await res.text();
        try { return JSON.parse(text); } catch { return { _raw: text }; }
    } catch (e) {
        clearTimeout(tid);
        throw e;
    }
}

async function injectLineEvents() {
    if (!RELAY_LINE_WEBHOOK_URL || !LINE_CHANNEL_SECRET) {
        console.error('缺少 RELAY_LINE_WEBHOOK_URL 或 LINE_CHANNEL_SECRET，無法發送 LINE webhook');
        process.exit(1);
    }
    console.log('[inject] 發送', TASK_SAMPLES.length, '則 LINE webhook 事件到 relay...');
    for (const { type, text } of TASK_SAMPLES) {
        const body = JSON.stringify({
            events: [{
                type: 'message',
                source: { userId: LINE_TEST_USER_ID },
                message: { type: 'text', text },
                replyToken: 'test-reply-' + type,
            }],
        });
        const raw = Buffer.from(body, 'utf8');
        const sig = signLineBody(raw, LINE_CHANNEL_SECRET);
        const res = await fetch(RELAY_LINE_WEBHOOK_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-line-signature': sig,
            },
            body: raw,
            signal: AbortSignal.timeout(15000),
        });
        const ok = res.ok;
        const data = await res.json().catch(() => ({}));
        if (!ok) {
            console.error(`  [inject] ${type} 失敗: HTTP ${res.status}`, data);
            process.exit(1);
        }
        console.log(`  [inject] ${type} ok (received: ${data.received ?? '?'})`);
    }
    console.log('[inject] 完成。請確認 bot 已連線同一 relay，稍後會出現 line_* 待處理任務。');
}

async function getPendingLineRecords() {
    const data = await fetchJson(`${BOT_API}/api/records?state=pending`);
    const list = data.records || data || [];
    if (!Array.isArray(list)) return [];
    return list.filter((r) => r.uid && String(r.uid).startsWith('line_'));
}

async function waitForPendingLineRecords(count, maxWaitMs = 60000) {
    const step = 3000;
    const start = Date.now();
    while (Date.now() - start < maxWaitMs) {
        const pending = await getPendingLineRecords();
        if (pending.length >= count) {
            return pending.slice(0, count);
        }
        console.log(`  [wait] 目前 pending line_*: ${pending.length}/${count}，${step / 1000}s 後再試...`);
        await new Promise((r) => setTimeout(r, step));
    }
    const pending = await getPendingLineRecords();
    return pending;
}

async function simulateComplete(uid, resultText) {
    const workerId = 'test-line-' + process.pid;
    const claimRes = await fetchJson(`${BOT_API}/api/records/${uid}/claim`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ worker_id: workerId }),
    }).catch((e) => ({ error: e.message }));
    if (claimRes.error || (claimRes.statusCode && claimRes.statusCode === 409)) {
        return { ok: false, step: 'claim', message: claimRes.error || '已被認領' };
    }
    const claimGen = claimRes.claim_generation ?? 0;

    let stateRes;
    try {
        stateRes = await fetch(`${BOT_API}/api/records/${uid}/state`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: 'processing', worker_id: workerId }),
            signal: AbortSignal.timeout(10000),
        });
    } catch (e) {
        return { ok: false, step: 'state', message: e.message };
    }
    if (!stateRes.ok) {
        return { ok: false, step: 'state', message: 'HTTP ' + stateRes.status };
    }

    let processedRes;
    try {
        processedRes = await fetch(`${BOT_API}/api/records/${uid}/processed`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ claim_generation: claimGen, result: resultText }),
            signal: AbortSignal.timeout(10000),
        });
    } catch (e) {
        return { ok: false, step: 'processed', message: e.message };
    }
    if (processedRes.status === 409) return { ok: false, step: 'processed', message: '認領已過期' };
    if (processedRes.status === 400) return { ok: false, step: 'processed', message: '狀態非 processing' };
    if (!processedRes.ok) return { ok: false, step: 'processed', message: 'HTTP ' + processedRes.status };
    return { ok: true };
}

async function runComplete() {
    const pending = await getPendingLineRecords();
    if (pending.length === 0) {
        console.log('[complete] 目前沒有 pending 的 line_* 任務。請先執行 inject 或 full。');
        return;
    }
    console.log('[complete] 找到', pending.length, '筆 line_* pending，開始模擬完成...');
    const results = [];
    for (let i = 0; i < pending.length; i++) {
        const rec = pending[i];
        const type = (rec.task_type || (rec.is_research ? 'research' : 'general'));
        const resultText = `[測試] ${type} 型任務完成。UID: ${rec.uid}`;
        const out = await simulateComplete(rec.uid, resultText);
        results.push({ uid: rec.uid, type, ...out });
        if (out.ok) {
            console.log(`  [complete] ${rec.uid} (${type}) → completed`);
        } else {
            console.error(`  [complete] ${rec.uid} (${type}) 失敗: ${out.step} - ${out.message}`);
        }
    }
    const failed = results.filter((r) => !r.ok);
    if (failed.length > 0) {
        console.error('[complete] 失敗筆數:', failed.length);
        process.exit(1);
    }
    console.log('[complete] 全部完成，結果已由 bot 透過 Gun 回傳至 relay（若 relay 有 LINE 設定會推至 LINE）。');
}

async function verifyReplies(expectMin = TASK_SAMPLES.length) {
    if (!RELAY_API_SECRET) {
        console.log('[verify] 未設定 RELAY_API_SECRET，略過 GET /api/replies 驗證');
        return;
    }
    const base = RELAY_LINE_WEBHOOK_URL?.replace(/\/api\/line-webhook.*$/, '') || '';
    if (!base) {
        console.log('[verify] 無法推斷 relay 根網址，略過 /api/replies');
        return;
    }
    const res = await fetchJson(`${base}/api/replies?limit=20`, {
        headers: { Authorization: 'Bearer ' + RELAY_API_SECRET },
    }).catch(() => ({}));
    const list = res.replies || [];
    console.log('[verify] relay /api/replies 最近', list.length, '筆');
    if (list.length < expectMin) {
        console.warn('[verify] 回覆數少於預期，請確認 relay 已收到 reply_* 並解密成功');
    }
}

async function main() {
    const mode = process.argv[2] || 'full';
    console.log('=== LINE 任務類型測試 ===');
    console.log('BOT_API:', BOT_API);
    console.log('RELAY_LINE_WEBHOOK_URL:', RELAY_LINE_WEBHOOK_URL ? '已設定' : '未設定');
    console.log('LINE_TEST_USER_ID:', LINE_TEST_USER_ID);
    console.log('mode:', mode);
    console.log('');

    if (mode === 'inject') {
        await injectLineEvents();
        return;
    }
    if (mode === 'complete') {
        await runComplete();
        await verifyReplies(0);
        return;
    }
    if (mode === 'full') {
        await injectLineEvents();
        console.log('');
        console.log('[full] 等待 bot 建立 line_* 記錄（最多 60s）...');
        const pending = await waitForPendingLineRecords(TASK_SAMPLES.length);
        if (pending.length < TASK_SAMPLES.length) {
            console.warn('[full] 僅等到', pending.length, '筆 line_*，繼續完成現有筆數');
        }
        if (pending.length === 0) {
            console.error('[full] 未取得任何 line_* 任務，請確認 bot 已連線 relay 且訊息迴圈正常');
            process.exit(1);
        }
        console.log('');
        await runComplete();
        await verifyReplies(pending.length);
        console.log('');
        console.log('=== 測試完成：各類型任務已模擬完成，結果應已回傳至 Gun/relay（及 LINE）===');
        return;
    }
    console.error('用法: node test-line-task-types.mjs [inject|complete|full]');
    process.exit(1);
}

main().catch((e) => {
    console.error(e);
    process.exit(1);
});
