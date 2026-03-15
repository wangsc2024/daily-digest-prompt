#!/usr/bin/env node
/**
 * 列出 Gun relay 上 chat room 目前可見的節點（任務/訊息 id 與狀態）。
 * 使用方式：node bot/list-relay-nodes.js
 * 會連線至 relay，訂閱 chat room 的 .map()，收集約 8 秒內收到的節點後輸出。
 */
const path = require('path');

require('dotenv').config({ path: path.join(__dirname, '.env') });

const GUN_RELAY_URL = process.env.GUN_RELAY_URL;
if (!GUN_RELAY_URL) {
    console.error('錯誤：請在 bot/.env 設定 GUN_RELAY_URL');
    process.exit(1);
}

const CHAT_ROOM_NAME = 'render_isolated_chat_room';
const COLLECT_MS = 8000;

const Gun = require('gun');
const gun = Gun({
    peers: [GUN_RELAY_URL],
    radisk: false,
    localStorage: false,
});

const nodes = new Map(); // id -> { hasData: boolean, updated: number }

gun.get(CHAT_ROOM_NAME).map().on((data, id) => {
    if (!id) return;
    const hasData = data !== undefined && data !== null && (typeof data !== 'string' || data.length > 0);
    nodes.set(id, { hasData, updated: Date.now() });
});

console.log(`正在訂閱 relay (${GUN_RELAY_URL}) chat room「${CHAT_ROOM_NAME}」，收集 ${COLLECT_MS / 1000} 秒...\n`);

setTimeout(() => {
    const list = Array.from(nodes.entries())
        .sort((a, b) => (a[1].updated - b[1].updated));
    const total = list.length;
    const withData = list.filter(([, v]) => v.hasData).length;
    const tombstone = list.filter(([, v]) => !v.hasData).length;

    console.log(`共 ${total} 個節點（有內容: ${withData}，已清除/tombstone: ${tombstone}）\n`);
    console.log('ID 前綴說明: line_=LINE 訊息, reply_=Bot 回覆, broadcast_=廣播, msg_=其他訊息\n');

    if (list.length === 0) {
        console.log('（未收到任何節點，可能 relay 尚無資料或連線較慢）');
        process.exit(0);
        return;
    }

    const byPrefix = {};
    list.forEach(([id, v]) => {
        const p = id.split('_')[0] || 'other';
        if (!byPrefix[p]) byPrefix[p] = { withData: 0, tombstone: 0, ids: [] };
        if (v.hasData) byPrefix[p].withData++;
        else byPrefix[p].tombstone++;
        byPrefix[p].ids.push(id);
    });

    Object.entries(byPrefix).sort((a, b) => b[1].ids.length - a[1].ids.length).forEach(([prefix, info]) => {
        console.log(`[${prefix}_*] 共 ${info.ids.length} 個（有內容: ${info.withData}，tombstone: ${info.tombstone}）`);
        info.ids.slice(0, 15).forEach(id => {
            const v = nodes.get(id);
            console.log(`  - ${id} ${v && !v.hasData ? '(已清除)' : ''}`);
        });
        if (info.ids.length > 15) {
            console.log(`  ... 其餘 ${info.ids.length - 15} 個`);
        }
        console.log('');
    });

    process.exit(0);
}, COLLECT_MS);
