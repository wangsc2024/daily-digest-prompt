#!/usr/bin/env node
/**
 * 清除 Gun relay 上 chat room 內「所有」節點（含 line_*、reply_* 等），並持久化清除記錄。
 * 使用方式：node bot/clear-all-relay-nodes.js
 *
 * 流程：訂閱 relay 收集節點 id → 對每個 id put(null)（tombstone）→ 將清除清單寫入本機 JSON 留存。
 * 注意：relay 端是否持久化 tombstone 取決於 relay 伺服器設定（如 radisk）；本腳本會將清除紀錄寫入 bot/data/relay-clear-log.json。
 */
const path = require('path');
const fs = require('fs');

require('dotenv').config({ path: path.join(__dirname, '.env') });

const GUN_RELAY_URL = process.env.GUN_RELAY_URL;
if (!GUN_RELAY_URL) {
    console.error('錯誤：請在 bot/.env 設定 GUN_RELAY_URL');
    process.exit(1);
}

const DATA_DIR = process.env.WSC_BOT_DATA_DIR || path.join(__dirname, 'data');
const CLEAR_LOG_PATH = path.join(DATA_DIR, 'relay-clear-log.json');
const CHAT_ROOM_NAME = 'render_isolated_chat_room';
const COLLECT_MS = 10000;   // 收集節點時間
const PUT_DELAY_MS = 25;    // 每筆 put(null) 間隔，避免 flood
const FINAL_FLUSH_MS = 5000; // 全部送完後等待，讓 Gun 送出

const Gun = require('gun');
const gun = Gun({
    peers: [GUN_RELAY_URL],
    radisk: false,
    localStorage: false,
});

const nodes = new Map(); // id -> { updated }

gun.get(CHAT_ROOM_NAME).map().on((data, id) => {
    if (!id) return;
    nodes.set(id, { updated: Date.now() });
});

function saveClearLog(ids) {
    const log = {
        clearedAt: new Date().toISOString(),
        relayUrl: GUN_RELAY_URL,
        chatRoom: CHAT_ROOM_NAME,
        totalCleared: ids.length,
        ids: ids.slice(0, 5000),
        note: ids.length > 5000 ? `僅保留前 5000 筆，實際清除 ${ids.length} 筆` : undefined
    };
    try {
        if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
        fs.writeFileSync(CLEAR_LOG_PATH, JSON.stringify(log, null, 2), 'utf8');
        console.log(`\n已寫入清除記錄: ${CLEAR_LOG_PATH}`);
    } catch (e) {
        console.error('寫入清除記錄失敗:', e.message);
    }
}

function runClear(ids) {
    const chatRoom = gun.get(CHAT_ROOM_NAME);
    let index = 0;
    function next() {
        if (index >= ids.length) {
            console.log(`\n已送出 ${ids.length} 個 tombstone，等待 ${FINAL_FLUSH_MS / 1000} 秒讓 relay 處理...`);
            setTimeout(() => {
                saveClearLog(ids);
                console.log('完成。');
                process.exit(0);
            }, FINAL_FLUSH_MS);
            return;
        }
        const uid = ids[index];
        chatRoom.get(uid).put(null);
        index++;
        if (index % 100 === 0 || index === ids.length) {
            console.log(`[${index}/${ids.length}] 已送出清除`);
        }
        setTimeout(next, PUT_DELAY_MS);
    }
    next();
}

console.log(`正在訂閱 relay (${GUN_RELAY_URL}) chat room「${CHAT_ROOM_NAME}」，收集 ${COLLECT_MS / 1000} 秒...\n`);

setTimeout(() => {
    const ids = Array.from(nodes.keys()).sort();
    if (ids.length === 0) {
        console.log('未收到任何節點，無需清除。');
        process.exit(0);
        return;
    }
    const byPrefix = {};
    ids.forEach(id => {
        const p = id.split('_')[0] || 'other';
        byPrefix[p] = (byPrefix[p] || 0) + 1;
    });
    console.log(`共 ${ids.length} 個節點將清除：`);
    Object.entries(byPrefix).sort((a, b) => b[1] - a[1]).forEach(([p, n]) => console.log(`  ${p}_*: ${n}`));
    console.log('\n開始送出 put(null)...');
    runClear(ids);
}, COLLECT_MS);
