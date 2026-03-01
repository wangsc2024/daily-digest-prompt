/**
 * 最終完整測試：發送任務 → 等待 Worker 執行 → 結果通知 wangsc2025
 * 此腳本需在 Claude Code session 外部執行（避免 CLAUDECODE 衝突）
 */

import SEA from 'gun/sea.js';
import Gun from 'gun';
import { randomBytes } from 'crypto';
import { writeFileSync, readFileSync, existsSync } from 'fs';
import { execSync } from 'child_process';

const RELAY_URL = process.env.GUN_RELAY_URL || 'https://gun-relay-bxdc.onrender.com/gun';
const BOT_API = 'http://localhost:3001';
const CHATROOM = 'render_isolated_chat_room';
const HANDSHAKE_PATH = 'wsc-bot/handshake';
const NTFY_TOPIC = 'wangsc2025';
const NTFY_URL = `https://ntfy.sh/${NTFY_TOPIC}`;
const RESULT_FILE = 'D:/Source/daily-digest-prompt/bot/final_test_result.json';

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
    } catch (e) { clearTimeout(tid); throw e; }
}

async function sendNtfy(title, message, priority = 3) {
    const ntfyPayload = { topic: NTFY_TOPIC, title, message, priority };
    const payloadFile = 'D:/Source/daily-digest-prompt/bot/ntfy_final_payload.json';
    writeFileSync(payloadFile, JSON.stringify(ntfyPayload, null, 2), 'utf8');
    try {
        execSync(`curl -s -X POST https://ntfy.sh -H "Content-Type: application/json; charset=utf-8" -d @${payloadFile}`, { timeout: 15000 });
        console.log(`    ✅ ntfy 通知已發送至 ${NTFY_TOPIC}`);
    } catch (e) {
        console.log(`    ⚠ ntfy 發送失敗: ${e.message}`);
    }
}

async function main() {
    console.log('=== 最終完整工作流程測試 ===');
    console.log(`時間: ${now()}\nRelay: ${RELAY_URL}\n`);

    // 1. Bot 健康
    const h = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
    if (!h?.gunConnected) { console.error('❌ Bot 未連線'); process.exit(1); }
    console.log(`[1] Bot OK: uptime=${Math.round(h.uptime)}s`);

    // 2. 金鑰對
    const myPair = await SEA.pair();
    console.log(`[2] 金鑰對: Epub=${myPair.epub.substring(0, 20)}...`);

    // 3. Bot epub
    const gun = Gun({ peers: [RELAY_URL], radisk: false, localStorage: false });
    const botEpub = await new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(null), 15000);
        let ok = false;
        const done = (epub, src) => {
            if (ok) return; ok = true;
            clearTimeout(timeout);
            console.log(`[3] Bot epub [${src}]: ${epub?.substring(0, 20)}...`);
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
        setTimeout(() => { if (!ok) gun.get(HANDSHAKE_PATH).get('bot-epub').once(e => { if (e) done(e, 'bot-epub'); }); }, 3000);
        setTimeout(() => { if (!ok) gun.get(HANDSHAKE_PATH).once(hw => { if (hw?.epub) done(hw.epub, '重試'); }); }, 7000);
    });
    if (!botEpub) { console.error('❌ 無法取得 Bot epub'); process.exit(1); }

    // 4. Shared Secret
    const sharedSecret = await SEA.secret(botEpub, myPair);
    console.log(`[4] Shared Secret: ${sharedSecret.substring(0, 20)}...`);

    // 5. 握手
    console.log('\n[5] 握手中（等 8s）...');
    gun.get(HANDSHAKE_PATH).get('client-epub').put(myPair.epub);
    gun.get(HANDSHAKE_PATH).get('clients').get(myPair.pub).put(myPair.epub);
    await sleep(8000);

    // 6. 發送任務（具體有意義的任務）
    const taskText = `請用繁體中文分析「Gun.js 去中心化資料庫在 AI Agent 任務管理系統中的應用優勢」，涵蓋：(1) 無需伺服器的 P2P 架構優勢 (2) SEA 端對端加密保障任務隱私 (3) 與傳統 REST API 相比的即時性優勢。每項 2-3 句話。`;
    console.log('\n[6] 發送任務...');
    console.log(`    ${taskText.substring(0, 60)}...`);

    const payload = JSON.stringify({ text: taskText, ts: Date.now() });
    const encryptedData = await SEA.encrypt(payload, sharedSecret);
    const msgId = genMsgId();
    gun.get(CHATROOM).get(msgId).put(encryptedData);
    console.log(`    ✅ msgId: ${msgId}`);

    // 7. 等待 Bot 確認 + Worker 結果（最多 8 分鐘）
    console.log('\n[7] 等待 Bot 確認 + Worker 執行結果（最多 8 分鐘）...');
    let botConfirm = '';
    let workerResult = '';

    await new Promise((resolve) => {
        const timeout = setTimeout(() => { console.log('\n⚠ 8 分鐘超時'); resolve(); }, 8 * 60 * 1000);
        const startWait = Date.now();

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

        // 每 60s 回報
        let i = 0;
        const iv = setInterval(async () => {
            i++;
            const elapsed = Math.round((Date.now() - startWait) / 1000);
            const health = await fetchJson(`${BOT_API}/api/health`).catch(() => null);
            console.log(`    [${elapsed}s] 等待 Worker... pendingTasks=${health?.pendingTasks ?? '?'}`);
            if (i > 9) clearInterval(iv);
        }, 60000);
    });

    // 8. 整理結果
    const testResult = {
        timestamp: new Date().toISOString(),
        task: taskText,
        msgId,
        botConfirm,
        workerResult: workerResult || '（未收到）',
        success: !!workerResult
    };

    writeFileSync(RESULT_FILE, JSON.stringify(testResult, null, 2), 'utf8');
    console.log(`\n結果已存至: ${RESULT_FILE}`);

    // 9. 發送 ntfy 通知
    console.log('\n[8] 發送 ntfy 通知至 wangsc2025...');

    if (workerResult) {
        // 提取 Worker 執行的實際內容（去掉 [系統回覆] 前綴和任務 ID 行）
        const resultContent = workerResult
            .replace(/\[系統回覆\] 任務 \S+ 執行完畢：\n/, '')
            .trim();

        const ntfyTitle = `✅ 聊天室任務執行完成 ${now()}`;
        const ntfyMessage = `📋 任務：${taskText.substring(0, 80)}...\n\n` +
            `🤖 執行結果：\n${resultContent.substring(0, 800)}${resultContent.length > 800 ? '\n...[截斷]' : ''}`;

        await sendNtfy(ntfyTitle, ntfyMessage, 4);
    } else {
        await sendNtfy(
            `⚠ 聊天室任務超時未收到結果 ${now()}`,
            `任務 ${msgId} 已發送，Bot 確認：${botConfirm ? '✅' : '❌'}，Worker 結果：未收到（8 分鐘內）`,
            3
        );
    }

    // 10. 最終摘要
    console.log('\n=== 最終測試結果 ===');
    console.log(`msgId:      ${msgId}`);
    console.log(`Bot 確認:   ${botConfirm ? '✅' : '⚠ 未收到'}`);
    console.log(`Worker 結果: ${workerResult ? '✅ 收到' : '⚠ 未收到'}`);
    if (workerResult) {
        console.log('\nWorker 執行內容（前 300 字）:');
        console.log(workerResult.substring(0, 300));
    }

    setTimeout(() => process.exit(0), 1000);
}

main().catch(e => { console.error('失敗:', e); process.exit(1); });
