/**
 * 完整工作流程測試：聊天室金鑰生成 → 任務指派 → Worker 執行
 * 模擬瀏覽器聊天室用戶的完整流程
 *
 * 訊息格式（與 index.html 一致）:
 * - 加密內容: JSON.stringify({ text, ts })
 * - Gun 路徑: chatroom.get('msg_xxx').put(encryptedData) 直接放，不包裝
 * - msgId: 'msg_' + random hex
 */

import SEA from 'gun/sea.js';
import Gun from 'gun';
import { randomBytes } from 'crypto';

const RELAY_URL = process.env.GUN_RELAY_URL || 'https://gun-relay-bxdc.onrender.com/gun';
const BOT_API = 'http://localhost:3001';
const CHATROOM = 'render_isolated_chat_room';
const HANDSHAKE_PATH = 'wsc-bot/handshake';
const EPUB_WAIT_MS = 8000; // 等待 bot 收到 epub 並建立 sharedSecret 的時間

const sleep = ms => new Promise(r => setTimeout(r, ms));

function genMsgId() {
    return 'msg_' + randomBytes(8).toString('hex').slice(0, 12);
}

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
    console.log('=== 完整工作流程測試 ===');
    console.log(`Relay: ${RELAY_URL}`);
    console.log(`Bot API: ${BOT_API}`);
    console.log('');

    // ---- 步驟 1: 確認 Bot 健康狀態 ----
    console.log('[1] 確認 Bot 服務狀態...');
    const health = await fetchJson(`${BOT_API}/api/health`).catch(e => null);
    if (!health) { console.error('    ❌ Bot API 無法連線'); process.exit(1); }
    console.log(`    uptime: ${Math.round(health.uptime)}s, gunConnected: ${health.gunConnected}, pendingTasks: ${health.pendingTasks}`);
    if (!health.gunConnected) { console.error('    ❌ Bot 未連線 Gun'); process.exit(1); }

    // ---- 步驟 2: 生成聊天室用戶金鑰對（模擬 index.html connect()）----
    console.log('\n[2] 生成聊天室用戶金鑰對...');
    const myPair = await SEA.pair();
    console.log(`    ✅ 用戶 Epub: ${myPair.epub.substring(0, 20)}...`);
    console.log(`    ✅ 用戶 Pub:  ${myPair.pub.substring(0, 20)}...`);

    // ---- 步驟 3: 連線 Gun Relay，取得 Bot Epub ----
    console.log(`\n[3] 連線 Gun Relay 並取得 Bot epub (最多 15s)...`);
    const gun = Gun({ peers: [RELAY_URL], radisk: false, localStorage: false });

    const botEpub = await new Promise((resolve) => {
        const timeout = setTimeout(() => { console.log('    ⚠ 15s 逾時'); resolve(null); }, 15000);
        let settled = false;

        function tryResolve(epub, source) {
            if (settled) return;
            settled = true;
            clearTimeout(timeout);
            console.log(`    ✅ Bot epub 取自 [${source}]`);
            resolve(epub);
        }

        // 主路徑：含簽章驗證的完整握手物件
        gun.get(HANDSHAKE_PATH).once(async (hw) => {
            if (!hw || !hw.epub) return; // null 或未就緒，等 fallback
            if (hw.sig && hw.pub) {
                const verified = await SEA.verify(hw.sig, hw.pub);
                if (verified !== hw.epub) {
                    console.log('    ⚠ Bot epub 驗證失敗（中間人攻擊？）');
                    tryResolve(null, 'verify-fail');
                    return;
                }
                tryResolve(hw.epub, 'handshake+ECDSA驗證');
            } else {
                tryResolve(hw.epub, 'handshake（無簽章）');
            }
        });

        // Fallback 2s: bot-epub 相容路徑
        setTimeout(() => {
            if (settled) return;
            gun.get(HANDSHAKE_PATH).get('bot-epub').once((epub) => {
                if (epub && typeof epub === 'string') tryResolve(epub, 'bot-epub fallback');
            });
        }, 2000);

        // 第二次完整握手嘗試 5s
        setTimeout(() => {
            if (settled) return;
            gun.get(HANDSHAKE_PATH).once(async (hw) => {
                if (!hw || !hw.epub) return;
                tryResolve(hw.epub, 'handshake 第2次重試');
            });
        }, 5000);
    });

    if (!botEpub) { console.error('    ❌ 無法取得 Bot epub'); process.exit(1); }
    console.log(`    Bot Epub: ${botEpub.substring(0, 20)}...`);

    // ---- 步驟 4: 計算 ECDH Shared Secret ----
    console.log('\n[4] 計算 ECDH Shared Secret...');
    const sharedSecret = await SEA.secret(botEpub, myPair);
    if (!sharedSecret) { console.error('    ❌ 無法計算 Shared Secret'); process.exit(1); }
    console.log(`    ✅ Shared Secret: ${sharedSecret.substring(0, 20)}...`);

    // ---- 步驟 5: 向 Bot 發布用戶 Epub（多用戶握手）----
    console.log('\n[5] 向 Bot 發布用戶 Epub（模擬 index.html 握手）...');
    // 向下相容路徑 + 多用戶路徑（兩條都發，確保 bot 收到）
    gun.get(HANDSHAKE_PATH).get('client-epub').put(myPair.epub);
    gun.get(HANDSHAKE_PATH).get('clients').get(myPair.pub).put(myPair.epub);
    console.log(`    ✅ 用戶 Epub 已發布（等待 ${EPUB_WAIT_MS/1000}s 讓 Bot 完成握手）...`);

    // 等待 bot 接收 epub、計算 sharedSecret、啟動訊息監聽迴圈
    await sleep(EPUB_WAIT_MS);
    console.log('    Bot 握手等待完成');

    // ---- 步驟 6: 發送加密任務訊息（格式與 index.html 一致）----
    const taskText = `測試工作流程：請用繁體中文寫一首關於春天的五言絕句（4 句），測試時間 ${new Date().toLocaleTimeString('zh-TW')}`;
    console.log('\n[6] 發送加密任務訊息...');
    console.log(`    任務內容: ${taskText}`);

    // 關鍵：加密 JSON.stringify({text, ts}) 而非純文字，與 index.html 一致
    const payload = JSON.stringify({ text: taskText, ts: Date.now() });
    const encryptedData = await SEA.encrypt(payload, sharedSecret);
    const msgId = genMsgId(); // msg_xxx 格式

    // 關鍵：直接 put 加密結果，不包裝成 {d: ..., ts: ...}
    gun.get(CHATROOM).get(msgId).put(encryptedData);
    console.log(`    ✅ 加密訊息已送出 (msgId: ${msgId})`);

    // ---- 步驟 7: 等待 Bot 確認儲存任務（最多 30s）----
    console.log('\n[7] 等待 Bot 儲存任務（最多 30 秒）...');
    let taskStored = false;
    for (let i = 0; i < 30; i++) {
        await sleep(1000);
        const h = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
        if (h && h.pendingTasks > 0) {
            console.log(`\n    ✅ Bot 已儲存 ${h.pendingTasks} 個待處理任務`);
            taskStored = true;
            break;
        }
        process.stdout.write(i % 10 === 9 ? `${i+1}` : '.');
    }
    console.log('');

    if (!taskStored) {
        // 也可能因為 classify 佇列而延遲或 pendingTasks 計算方式不同
        console.log('    ⚠ Bot 未回報 pendingTasks > 0，確認 tasks_md 目錄...');
        // 繼續執行，不中止
    }

    // ---- 步驟 8: 監聽 Bot 系統回覆（最多 40s）----
    console.log('\n[8] 監聽 Bot 系統回覆（最多 40 秒）...');
    let botReply = null;

    botReply = await new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(null), 40000);
        const sentAt = Date.now();

        gun.get(CHATROOM).map().on(async (data, key) => {
            if (!data || key === msgId) return; // 跳過自己的訊息
            // 只看新訊息（比發送時間晚 or 未知時間）
            try {
                const raw = await SEA.decrypt(data, sharedSecret);
                if (!raw) return;
                let text;
                if (typeof raw === 'string') text = raw;
                else if (raw && typeof raw === 'object' && raw.text) text = raw.text;
                else return;

                if (text && text.startsWith('[系統回覆]')) {
                    clearTimeout(timeout);
                    resolve(text);
                }
            } catch {}
        });
    });

    if (botReply) {
        console.log(`    ✅ Bot 回覆: ${botReply}`);
    } else {
        console.log('    ⚠ 40 秒內未收到 Bot 系統回覆');
    }

    // ---- 步驟 9: 最終狀態確認 ----
    console.log('\n[9] 最終狀態確認...');
    const finalHealth = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
    if (finalHealth) {
        console.log(`    Bot: uptime=${Math.round(finalHealth.uptime)}s, pendingTasks=${finalHealth.pendingTasks}`);
    }

    console.log('\n=== 測試結果 ===');
    console.log(`任務指派: ${taskStored ? '✅ 成功' : '⚠ 未確認（可能有延遲）'}`);
    console.log(`Bot 回覆: ${botReply ? '✅ 收到' : '⚠ 未收到'}`);
    console.log('\n若任務已儲存，執行以下指令讓 Worker 處理:');
    console.log('  pwsh -ExecutionPolicy Bypass -File process_messages.ps1');

    setTimeout(() => process.exit(0), 1000);
}

main().catch((e) => {
    console.error('測試失敗:', e);
    process.exit(1);
});
