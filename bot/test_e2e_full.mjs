/**
 * 端對端完整測試：聊天室指派任務 → Bot 儲存 → Worker(Task Scheduler) 執行 → 結果回傳
 *
 * 此腳本在 Claude Code session 外部執行（或背景），等待 Task Scheduler 的 Worker
 * 自動認領並執行任務（每 5 分鐘一次），最多等待 10 分鐘。
 *
 * 修正的測試訊息格式（與 index.html 完全一致）：
 * - 加密格式: SEA.encrypt(JSON.stringify({text, ts}), sharedSecret)
 * - Gun put: chatroom.get('msg_xxx').put(encryptedData) 直接放
 */

import SEA from 'gun/sea.js';
import Gun from 'gun';
import { randomBytes } from 'crypto';

const RELAY_URL = process.env.GUN_RELAY_URL || 'https://gun-relay-bxdc.onrender.com/gun';
const BOT_API = 'http://localhost:3001';
const CHATROOM = 'render_isolated_chat_room';
const HANDSHAKE_PATH = 'wsc-bot/handshake';
const TOTAL_WAIT_SECS = 600; // 最多等 10 分鐘（含 Worker 執行時間）

const sleep = ms => new Promise(r => setTimeout(r, ms));
const genMsgId = () => 'msg_' + randomBytes(8).toString('hex').slice(0, 12);

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
    const startTime = Date.now();
    console.log('=== 端對端完整工作流程測試 ===');
    console.log(`啟動時間: ${new Date().toLocaleTimeString('zh-TW')}`);
    console.log(`Relay: ${RELAY_URL}\n`);

    // 1. Bot 健康確認
    console.log('[1] Bot 健康確認...');
    const h = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
    if (!h?.gunConnected) { console.error('    ❌ Bot 未連線'); process.exit(1); }
    console.log(`    ✅ uptime=${Math.round(h.uptime)}s, gunConnected=true`);

    // 2. 生成金鑰對
    console.log('\n[2] 生成聊天室金鑰對...');
    const myPair = await SEA.pair();
    console.log(`    ✅ Epub: ${myPair.epub.substring(0, 20)}...`);

    // 3. 連線 Gun & 取得 Bot epub
    console.log('\n[3] 取得 Bot epub...');
    const gun = Gun({ peers: [RELAY_URL], radisk: false, localStorage: false });

    const botEpub = await new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(null), 15000);
        let settled = false;
        const ok = (epub, src) => {
            if (settled) return;
            settled = true;
            clearTimeout(timeout);
            console.log(`    ✅ Bot epub 取自 [${src}]`);
            resolve(epub);
        };

        gun.get(HANDSHAKE_PATH).once(async (hw) => {
            if (!hw?.epub) return;
            if (hw.sig && hw.pub) {
                const v = await SEA.verify(hw.sig, hw.pub);
                if (v !== hw.epub) { ok(null, 'verify-fail'); return; }
                ok(hw.epub, 'handshake+ECDSA');
            } else ok(hw.epub, 'handshake');
        });

        setTimeout(() => {
            if (!settled) gun.get(HANDSHAKE_PATH).get('bot-epub').once(epub => {
                if (epub && typeof epub === 'string') ok(epub, 'bot-epub fallback');
            });
        }, 3000);

        setTimeout(() => {
            if (!settled) gun.get(HANDSHAKE_PATH).once(hw => {
                if (hw?.epub) ok(hw.epub, 'handshake 重試');
            });
        }, 7000);
    });

    if (!botEpub) { console.error('    ❌ 無法取得 Bot epub'); process.exit(1); }

    // 4. Shared Secret
    const sharedSecret = await SEA.secret(botEpub, myPair);
    if (!sharedSecret) { console.error('    ❌ 無法計算 Shared Secret'); process.exit(1); }
    console.log(`    ✅ Shared Secret: ${sharedSecret.substring(0, 20)}...`);

    // 5. 握手（發布用戶 epub）
    console.log('\n[4] 發布用戶 Epub，等待 Bot 握手（8s）...');
    gun.get(HANDSHAKE_PATH).get('client-epub').put(myPair.epub);
    gun.get(HANDSHAKE_PATH).get('clients').get(myPair.pub).put(myPair.epub);
    await sleep(8000);
    console.log('    ✅ 握手等待完成');

    // 6. 發送任務
    const taskText = `請用繁體中文分析台灣 AI 產業的三大發展趨勢，各用一段話說明。（測試 ${new Date().toLocaleTimeString('zh-TW')}）`;
    console.log('\n[5] 發送加密任務...');
    console.log(`    任務: ${taskText.substring(0, 50)}...`);

    const payload = JSON.stringify({ text: taskText, ts: Date.now() });
    const encryptedData = await SEA.encrypt(payload, sharedSecret);
    const msgId = genMsgId();
    gun.get(CHATROOM).get(msgId).put(encryptedData);
    console.log(`    ✅ 已發送 (msgId: ${msgId})`);

    // 7. 等待 Bot 確認儲存
    console.log('\n[6] 等待 Bot 確認任務儲存（最多 30s）...');
    let botConfirmed = false;
    let botConfirmMsg = '';

    const confirmPromise = new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(false), 30000);
        const sentTs = Date.now();

        gun.get(CHATROOM).map().on(async (data, key) => {
            if (!data || key === msgId) return;
            try {
                const raw = await SEA.decrypt(data, sharedSecret);
                if (!raw) return;
                const text = typeof raw === 'string' ? raw : raw?.text || '';
                if (text.startsWith('[系統回覆]')) {
                    clearTimeout(timeout);
                    botConfirmMsg = text;
                    resolve(true);
                }
            } catch {}
        });
    });

    botConfirmed = await confirmPromise;
    if (botConfirmed) {
        console.log(`    ✅ Bot 確認: ${botConfirmMsg}`);
    } else {
        console.log('    ⚠ Bot 未在 30s 內確認（繼續等待 Worker）');
    }

    // 8. 等待 Worker 執行結果（Task Scheduler 每 5 分鐘）
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    const remaining = TOTAL_WAIT_SECS - elapsed;
    console.log(`\n[7] 等待 Worker 執行結果（最多 ${Math.round(remaining/60)} 分鐘）...`);
    console.log('    Task Scheduler 每 5 分鐘執行一次 process_messages.ps1');
    console.log('    Worker 會認領任務，用 claude -p 執行，再廣播結果回聊天室\n');

    let workerResult = null;

    workerResult = await new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(null), remaining * 1000);
        let confirmed = false;

        gun.get(CHATROOM).map().on(async (data, key) => {
            if (!data || key === msgId || confirmed) return;
            try {
                const raw = await SEA.decrypt(data, sharedSecret);
                if (!raw) return;
                const text = typeof raw === 'string' ? raw : raw?.text || '';
                // Worker 結果是第二條系統回覆（包含任務執行結果）
                if (text.startsWith('[系統回覆]') && text !== botConfirmMsg) {
                    confirmed = true;
                    clearTimeout(timeout);
                    resolve(text);
                }
            } catch {}
        });

        // 每 30 秒回報狀態
        let i = 0;
        const statusInterval = setInterval(async () => {
            i++;
            const t = Math.round((Date.now() - startTime) / 1000);
            const health = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
            const pending = health?.pendingTasks ?? '?';
            console.log(`    [${t}s] 等待中... pendingTasks=${pending}`);
            if (i > Math.ceil(remaining / 30)) clearInterval(statusInterval);
        }, 30000);
    });

    // 9. 最終結果
    console.log('\n=== 測試結果 ===');
    const totalTime = Math.round((Date.now() - startTime) / 1000);
    console.log(`總耗時: ${totalTime}s`);
    console.log(`Bot 確認任務儲存: ${botConfirmed ? '✅' : '⚠'}`);

    if (workerResult) {
        console.log(`\nWorker 執行結果:\n${workerResult.substring(0, 500)}${workerResult.length > 500 ? '...' : ''}`);
        console.log('\n✅ 完整工作流程測試成功！');
    } else {
        console.log('\n⚠ Worker 結果未在時間內回傳');
        console.log('可能原因: Worker 尚未執行 / claude -p 處理中 / 超時');
        console.log('請確認 process_messages.ps1 是否在 Task Scheduler 中正常執行');
    }

    process.exit(0);
}

main().catch(e => { console.error('測試失敗:', e); process.exit(1); });
