#!/usr/bin/env node
/**
 * 一次性腳本：清除 Gun relay 上所有「由 LINE 指派」的任務節點（uid 以 line_ 開頭）。
 * 使用方式（在專案根目錄）：node bot/clear-line-tasks-on-relay.js
 * 或進入 bot 目錄：node clear-line-tasks-on-relay.js
 *
 * 會讀取 bot/data/records.json，篩出 line_* 的 uid，對 relay 上 chatRoom 的該節點 put(null)（tombstone）。
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
const RECORDS_PATH = path.join(DATA_DIR, 'records.json');
const CHAT_ROOM_NAME = 'render_isolated_chat_room';

let records = [];
try {
    records = JSON.parse(fs.readFileSync(RECORDS_PATH, 'utf8'));
} catch (err) {
    console.error('讀取 records.json 失敗:', err.message);
    process.exit(1);
}

const lineUids = records
    .filter(r => r.uid && String(r.uid).startsWith('line_'))
    .map(r => r.uid);

if (lineUids.length === 0) {
    console.log('沒有 LINE 指派的任務記錄（line_*），無需清除。');
    process.exit(0);
}

console.log(`找到 ${lineUids.length} 筆 LINE 任務，準備清除 relay 上對應節點：`);
lineUids.forEach(uid => console.log(`  - ${uid}`));

const Gun = require('gun');
const gun = Gun({
    peers: [GUN_RELAY_URL],
    radisk: false,
    localStorage: false,
});

const chatRoom = gun.get(CHAT_ROOM_NAME);
let done = 0;
lineUids.forEach(uid => {
    chatRoom.get(uid).put(null);
    done++;
    console.log(`[${done}/${lineUids.length}] 已送出清除: ${uid}`);
});

setTimeout(() => {
    console.log(`\n已完成：已對 relay 送出 ${lineUids.length} 個節點的 tombstone (put(null))。`);
    process.exit(0);
}, 3000);
