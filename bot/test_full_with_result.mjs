/**
 * 完整工作流程測試（含 Worker 結果）
 * - 發送任務，等待 Bot 確認，然後等待最多 8 分鐘接收 Worker 執行結果
 */

import SEA from 'gun/sea.js';
import Gun from 'gun';
import { randomBytes } from 'crypto';

const RELAY_URL = process.env.GUN_RELAY_URL || 'https://gun-relay-bxdc.onrender.com/gun';
const BOT_API = 'http://localhost:3001';
const CHATROOM = 'render_isolated_chat_room';
const HANDSHAKE_PATH = 'wsc-bot/handshake';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const genMsgId = () => 'msg_' + randomBytes(8).toString('hex').slice(0, 12);
const now = () => new Date().toLocaleTimeString('zh-TW');

async function fetchJson(url, opts = {}, timeout = 10000) {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), timeout);
    try {
        const res = await fetch(url, { ...opts, signal: ctrl.signal });
        clearTimeout(tid);
        return res.json();
    } catch (e) {
        clearTimeout(tid);
        throw e;
    }
}

async function main() {
    console.log('=== 完整工作流程測試（含 Worker 結果等待）===');
    console.log(`時間: ${now()}`);

    // 1. Bot 健康
    const h = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
    if (!h?.gunConnected) { console.error('❌ Bot 未連線'); process.exit(1); }
    console.log(`[1] Bot OK: uptime=${Math.round(h.uptime)}s\n`);

    // 2. 生成金鑰對
    const myPair = await SEA.pair();
    console.log(`[2] 用戶 Epub: ${myPair.epub.substring(0, 20)}...`);

    // 3. Gun 連線 + Bot epub
    const gun = Gun({ peers: [RELAY_URL], radisk: false, localStorage: false });
    const botEpub = await new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(null), 15000);
        let ok = false;
        const done = (epub, src) => {
            if (ok) return; ok = true;
            clearTimeout(timeout);
            console.log(`[3] Bot epub [${src}]: ${epub ? epub.substring(0, 20) : 'null'}...`);
            resolve(epub);
        };
        gun.get(HANDSHAKE_PATH).once(async (hw) => {
            if (!hw?.epub) return;
            if (hw.sig && hw.pub) {
                const v = await SEA.verify(hw.sig, hw.pub);
                if (v !== hw.epub) { done(null, 'verify-fail'); return; }
                done(hw.epub, 'handshake+ECDSA');
            } else done(hw.epub, 'handshake');
        });
        setTimeout(() => { if (!ok) gun.get(HANDSHAKE_PATH).get('bot-epub').once(e => { if (e) done(e, 'fallback'); }); }, 3000);
        setTimeout(() => { if (!ok) gun.get(HANDSHAKE_PATH).once(hw => { if (hw?.epub) done(hw.epub, '重試'); }); }, 7000);
    });
    if (!botEpub) { console.error('❌ 無法取得 Bot epub'); process.exit(1); }

    // 4. Shared Secret
    const sharedSecret = await SEA.secret(botEpub, myPair);
    console.log(`[4] Shared Secret: ${sharedSecret.substring(0, 20)}...`);

    // 5. 發布 epub，握手
    console.log('\n[5] 握手中（等 8s）...');
    gun.get(HANDSHAKE_PATH).get('client-epub').put(myPair.epub);
    gun.get(HANDSHAKE_PATH).get('clients').get(myPair.pub).put(myPair.epub);
    await sleep(8000);

    // 6. 發送任務
    const taskText = `請用繁體中文分析台灣 AI 產業三大發展機會（每項 2-3 句話），測試時間 ${now()}`;
    const payload = JSON.stringify({ text: taskText, ts: Date.now() });
    const encryptedData = await SEA.encrypt(payload, sharedSecret);
    const msgId = genMsgId();
    gun.get(CHATROOM).get(msgId).put(encryptedData);
    console.log(`\n[6] 任務已送出: ${msgId}`);
    console.log(`    內容: ${taskText.substring(0, 60)}...`);

    // 7+8. 同時監聽兩種回覆：Bot 確認 + Worker 結果
    console.log('\n[7] 等待 Bot 確認 + Worker 執行結果（最多 8 分鐘）...');
    console.log('    Task Scheduler 每 5 分鐘執行一次 Worker');

    let botConfirm = '';
    let workerResult = '';

    const WAIT_MS = 8 * 60 * 1000; // 8 分鐘
    const startWait = Date.now();

    await new Promise((resolve) => {
        const timeout = setTimeout(resolve, WAIT_MS);

        gun.get(CHATROOM).map().on(async (data, key) => {
            if (!data || key === msgId) return;
            try {
                const raw = await SEA.decrypt(data, sharedSecret);
                if (!raw) return;
                const text = typeof raw === 'string' ? raw : raw?.text || '';
                if (!text.startsWith('[系統回覆]')) return;

                if (!botConfirm) {
                    botConfirm = text;
                    console.log(`\n    ✅ [${now()}] Bot 確認: ${text.substring(0, 80)}`);
                } else if (text !== botConfirm && !workerResult) {
                    workerResult = text;
                    console.log(`\n    ✅ [${now()}] Worker 結果收到！`);
                    clearTimeout(timeout);
                    resolve();
                }
            } catch {}
        });

        // 每 60s 顯示等待狀態
        const interval = setInterval(async () => {
            const elapsed = Math.round((Date.now() - startWait) / 1000);
            const health = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
            console.log(`    [${elapsed}s] 等待 Worker... pendingTasks=${health?.pendingTasks ?? '?'}`);
            if (Date.now() - startWait > WAIT_MS) clearInterval(interval);
        }, 60000);
    });

    // 9. 結果
    console.log('\n=== 測試結果 ===');
    console.log(`Bot 確認: ${botConfirm ? '✅ ' + botConfirm.substring(0, 80) : '⚠ 未收到'}`);

    if (workerResult) {
        console.log('\n✅ Worker 執行結果：');
        console.log(workerResult.substring(0, 1000));
        if (workerResult.length > 1000) console.log('...[截斷]');
        console.log('\n✅ 完整工作流程驗證成功！');
    } else {
        console.log('\n⚠ 未收到 Worker 結果（超時）');
        console.log('可能原因：Worker 執行中 / claude -p 耗時較長');
    }

    setTimeout(() => process.exit(0), 1000);
}

main().catch(e => { console.error('失敗:', e); process.exit(1); });
