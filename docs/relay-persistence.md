# Gun Relay 持久化設定

**目前生產環境 relay**：my-gun-relay 部署於 **https://gun-relay-bxdc.onrender.com/gun**（Render）。`bot/.env` 的 `GUN_RELAY_URL` 應指向此 URL，bot 與 relay 完成 ECDH 握手後，任務完成回覆會經由 relay 寫入 Gun 並可轉送至 LINE。

任務完成後對 relay 送出的 `put(null)`（tombstone）以及日常訊息，要能在 relay **重啟後仍保留**，必須在 **relay 伺服器** 啟用 Gun 的 Radisk 持久化並使用可持久化的儲存路徑。

## 1. Relay 端必須啟用的設定

在 **relay 的 Gun 建構**（例如 `my-gun-relay/index.js` 或 Render 上的 relay 專案）中，請確保：

```javascript
const gun = Gun({
    web: server,           // 或你的 HTTP server
    peers: [],             // 依需求
    radisk: true,          // ★ 必須：啟用 Radisk 持久化
    localStorage: false,
    axe: false,
    file: 'radata',        // ★ 儲存目錄名稱（相對 process.cwd() 或可改為絕對路徑）
    // 可選：效能與穩定性
    chunk: 2 * 1024 * 1024,
    until: 2 * 1000,
});
```

- **`radisk: true`**：將 graph 寫入磁碟（含 tombstone），重啟後會從 `file` 目錄恢復。
- **`file: 'radata'`**：資料寫入 `radata/` 目錄；若部署環境有「持久化磁碟」，請把該目錄放在持久化磁碟上（見下方部署說明）。

## 2. 部署環境與持久化

| 環境 | 持久化要點 |
|------|------------|
| **本機（如 my-gun-relay）** | 使用預設 `file: 'radata'` 即可，目錄在專案下會持久存在。 |
| **Render.com** | 免費方案重啟後 **磁碟會清空**，radata 不會保留。要持久化須：使用 **Persistent Disk**（付費），並在專案中將 `file` 指到掛載的磁碟路徑（例如 `process.env.RADATA_PATH || '/data/radata'`）。 |
| **VPS / 自架** | 確保 relay  process 有權限寫入 `radata` 目錄，且該目錄不在重啟會清空的 tmp 下。 |

## 3. 驗證是否生效

1. 啟動 relay 後，在 chat room 寫入一筆資料，再對該節點 `put(null)`。
2. **重啟 relay**。
3. 用 `node bot/list-relay-nodes.js` 訂閱同一 chat room：若該節點仍為 tombstone（無內容），表示 relay 已正確持久化 tombstone。

若 relay 未啟用 radisk 或磁碟非持久，重啟後會看不到先前的 tombstone，節點可能又顯示舊內容。

## 4. 本專案內建「具持久化」的 Relay（可選）

若希望 relay 一定寫入本機磁碟、重啟後保留 tombstone，可使用專案內的迷你 relay：

```bash
node bot/relay-server.js
```

- 監聽 port **8765**（可設環境變數 `PORT`）。
- 資料寫入 **`bot/data/radata/`**（與 records 同目錄，持久存在）。
- 將 `bot/.env` 的 `GUN_RELAY_URL` 設為 `http://localhost:8765/gun` 即改走本機 relay。

適用本機或自架環境；Render 等雲端則需依第 2 節設定持久化磁碟。

## 5. 本專案相關腳本

| 腳本 | 用途 |
|------|------|
| `node bot/relay-server.js` | 啟動具 Radisk 持久化的迷你 relay（port 8765）。 |
| `node bot/clear-all-relay-nodes.js` | 清除 chat room 內所有節點（line_*、reply_* 等），並將清除清單寫入 `bot/data/relay-clear-log.json`。 |
| `node bot/list-relay-nodes.js` | 列出 relay 上目前可見的節點與前綴統計。 |
| `node bot/clear-line-tasks-on-relay.js` | 僅清除 line_* 節點（依 records.json）。 |

清除記錄會寫入 `bot/data/relay-clear-log.json`，可作為「何時清除了哪些 id」的持久化紀錄。
