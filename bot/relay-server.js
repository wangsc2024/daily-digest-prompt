#!/usr/bin/env node
/**
 * 最小 Gun relay 伺服器（含 Radisk 持久化）。
 * 資料寫入 bot/data/radata/，relay 重啟後 tombstone 與 graph 會保留。
 *
 * 使用方式：node bot/relay-server.js
 * 預設 port 8765，可設環境變數 PORT。
 * 連線：http://localhost:8765/gun
 *
 * 若要用此 relay 取代 Render，請將 bot/.env 的 GUN_RELAY_URL 改為 http://localhost:8765/gun（本機）或你的對外網址。
 */
const http = require('http');
const path = require('path');
const Gun = require('gun');

const PORT = process.env.PORT || 8765;
const DATA_DIR = process.env.WSC_BOT_DATA_DIR || path.join(__dirname, 'data');
const RADATA_DIR = path.join(DATA_DIR, 'radata');

const server = http.createServer(Gun.serve(__dirname));
const gun = Gun({
    web: server,
    peers: [],
    radisk: true,
    file: RADATA_DIR,
    localStorage: false,
    axe: false,
});
server.listen(PORT, () => {
    console.log(`[relay] 已啟動，port ${PORT}，持久化目錄: ${RADATA_DIR}`);
    console.log(`[relay] 連線: http://localhost:${PORT}/gun`);
});
