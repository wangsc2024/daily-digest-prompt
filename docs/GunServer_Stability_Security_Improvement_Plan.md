# Gun Server 穩定性與安全性優化計畫

> **版本**：v1.0.0 | **日期**：2026-03-02 | **作者**：系統架構團隊
> **審查範圍**：`my-gun-relay`（Gun.js Relay 中繼伺服器）+ `wsc-bot01`（Bot 客戶端）
> **前置文件**：`gun-js-optimization-report-20260228.md`（應用層 27 項修補，本計畫為基礎設施層互補）
> **標籤**：`Gun`, `Server`, `Stability`, `Security`, `Improvement`, `WebSocket`, `P2P`

---

## 1. 背景與現況分析

### 1.1 系統架構概述

```
┌─────────────────────┐     WSS/HTTPS      ┌──────────────────────┐
│   index.html        │◄──────────────────►│   my-gun-relay       │
│   (前端聊天室)       │    Gun Protocol     │   (Gun.js Relay)     │
│   SEA E2E 加密       │                    │   Express + Gun      │
└─────────────────────┘                    │   Port: 8765         │
                                           └──────────┬───────────┘
┌─────────────────────┐     Gun P2P Sync               │
│   wsc-bot01/bot.js  │◄──────────────────────────────┘
│   (聊天機器人)       │
│   FSM + Groq AI     │
│   Express API :3001 │
└─────────────────────┘
```

### 1.2 部署環境

| 項目 | 現況 |
|------|------|
| **Gun.js 版本** | 0.2020.1241（2025-07-01，最新穩定版） |
| **Node.js** | 無版本鎖定（建議 ≥ 18 LTS） |
| **執行方式** | `node index.js`（無進程管理器） |
| **監聽埠** | 8765（HTTP，無 TLS） |
| **持久化** | RAD（`radata/` 目錄，約 2MB） |
| **CORS** | `origin: '*'`（完全開放） |
| **認證** | 無伺服器端認證（依賴 SEA 客戶端加密） |
| **監控** | `/api/health` 基本端點 |
| **日誌** | `console.log`（無結構化日誌） |
| **備份** | 無自動備份策略 |
| **進程管理** | 無（手動 `node index.js`） |

### 1.3 既有安全措施

| 措施 | 狀態 | 說明 |
|------|------|------|
| E2E 加密（SEA ECDH） | ✅ 已實作 | 訊息端到端加密，Relay 為盲中繼 |
| epub 簽章驗證 | ✅ 已實作 | 防 MITM 替換公鑰（2026-02-28 報告 B2） |
| DOMPurify XSS 防護 | ✅ 已實作 | 前端 Markdown 渲染消毒 |
| express-rate-limit | ✅ 已實作 | bot.js：60/300 req/min 兩級 |
| HTTPS/TLS | ❌ 未實作 | Relay 層無 TLS 終端 |
| Relay 速率限制 | ❌ 未實作 | Relay 端無連線/訊息限制 |
| 結構化日誌 | ❌ 未實作 | 無可查詢的操作日誌 |
| 備份策略 | ❌ 未實作 | radata 無備份 |

### 1.4 與既有優化報告的關係

| 報告 | 範疇 | 本計畫關係 |
|------|------|-----------|
| `gun-js-optimization-report-20260228.md` | 應用層：ACK 修正、去重、epub 驗證、渲染效能（27 項） | **互補**：本計畫聚焦基礎設施層 |
| 本計畫 | 基礎設施層：TLS、進程管理、監控、備份、防火牆、運維 | 建立在應用層修補之上 |

---

## 2. 穩定性優化方案

### 2.1 ST-01：進程管理器導入（PM2）

**問題說明**
目前以 `node index.js` 直接啟動，程式崩潰後無自動重啟，單點故障風險高。

**改善目標**
- 程式崩潰後 3 秒內自動重啟
- 支援 graceful shutdown（不丟失進行中的 WebSocket 連線）
- 記憶體超限自動重啟（防止記憶體洩漏導致的漸進式效能衰退）

**推薦技術**
PM2（Node.js 進程管理器），選擇原因：零配置重啟、內建日誌管理、監控面板、Windows 相容。

**實作步驟**

1. 安裝 PM2：
   ```bash
   npm install -g pm2
   ```

2. 建立 `ecosystem.config.js`：
   ```javascript
   module.exports = {
     apps: [{
       name: 'gun-relay',
       script: 'index.js',
       instances: 1,              // Gun.js 單進程（見 ST-02 說明）
       exec_mode: 'fork',
       max_memory_restart: '512M', // 記憶體超 512MB 自動重啟
       restart_delay: 3000,        // 重啟間隔 3 秒
       max_restarts: 10,           // 10 分鐘內最多重啟 10 次
       min_uptime: '30s',          // 30 秒內崩潰視為不穩定
       watch: false,               // 生產環境不開 watch
       env: {
         NODE_ENV: 'production',
         PORT: 8765,
       },
       // Graceful shutdown
       kill_timeout: 10000,         // 等待 10 秒關閉
       listen_timeout: 8000,        // 等待 8 秒啟動
       shutdown_with_message: true, // 發送 SIGINT 而非 SIGKILL
     }]
   };
   ```

3. 在 `index.js` 加入 graceful shutdown：
   ```javascript
   process.on('SIGINT', () => {
     console.log('[Relay] 收到 SIGINT，開始優雅關閉...');
     server.close(() => {
       console.log('[Relay] HTTP 伺服器已關閉');
       process.exit(0);
     });
     // 10 秒後強制關閉
     setTimeout(() => process.exit(1), 10000);
   });
   ```

4. 啟動與管理：
   ```bash
   pm2 start ecosystem.config.js
   pm2 save          # 保存進程列表
   pm2 startup       # 設定開機自啟（Windows 需額外配置）
   ```

**驗證方式**
- 手動 `kill` 進程 → PM2 應在 3 秒內自動重啟
- 觸發 OOM（分配大 Buffer）→ PM2 應在記憶體超 512MB 時重啟
- `pm2 logs gun-relay` 確認日誌正常輸出

**估計資源**
- 人力：0.5 人天
- 測試：本機驗證即可

---

### 2.2 ST-02：Node.js Cluster 模式評估

**問題說明**
單進程架構在 CPU 密集型操作（大量 WebSocket 訊息解析）時可能成為瓶頸。

**改善目標**
評估是否需要多進程部署，以及 Gun.js 的 Cluster 限制。

**技術分析**

> **重要限制**：Gun.js 的記憶體內 graph（DAM layer）不支援原生跨進程共享。使用 Cluster 模式時，每個 Worker 維護獨立的 Gun 實例，需透過 Gun 自身的 peer-to-peer 機制同步，會引入額外的資料同步延遲。

**架構決策：維持單進程 + PM2**

| 方案 | 優點 | 缺點 | 適用場景 |
|------|------|------|---------|
| 單進程 + PM2 | 簡單、無同步問題、零延遲 | 單核心瓶頸 | **當前場景（推薦）** |
| Cluster（N Worker） | 多核心利用 | Graph 同步延遲、資料一致性風險 | 高併發（>1000 連線） |
| 多 Relay 實例 + Gun Peers | 水平擴展、高可用 | 架構複雜、需負載均衡 | 企業級部署 |

**理由**：目前連線數 < 10，CPU 使用率 < 5%，單進程完全足夠。未來若需擴展，優先考慮「多 Relay 實例 + Gun Peers」而非 Cluster。

**驗證方式**
- 監控 CPU 使用率，若持續 > 70% 再考慮 Cluster
- 記錄 WebSocket 連線數峰值

---

### 2.3 ST-03：WebSocket 連線保活與靜默斷線偵測

**問題說明**
PaaS 平台（如 Render.com）的 idle timeout 約 60 秒，無活動時會關閉 WebSocket 連線。Gun.js 雖有自動重連，但「靜默斷線」（TCP 連線未正常關閉）可能延遲數分鐘才偵測到。

**改善目標**
- 防止 idle timeout 導致的被動斷線
- 靜默斷線偵測時間從「數分鐘」縮短到「2 分鐘」
- 提供連線狀態統計指標

**實作步驟**

在 `index.js`（Relay 端）加入：

```javascript
// === WebSocket 連線保活 ===
const KEEPALIVE_INTERVAL_MS = 45 * 1000; // 低於多數 PaaS 的 60s idle timeout

setInterval(() => {
  // Gun.js 內部透過 WebSocket server 管理連線
  if (server._webSocketServer) {
    const clients = server._webSocketServer.clients;
    let aliveCount = 0;
    clients.forEach(ws => {
      if (ws.readyState === 1) { // OPEN
        ws.ping();  // 發送 WebSocket ping frame
        aliveCount++;
      }
    });
    if (aliveCount > 0) {
      console.log(`[WS] 保活 ping 已發送（${aliveCount} 個活躍連線）`);
    }
  }
}, KEEPALIVE_INTERVAL_MS);

// === 連線狀態追蹤 ===
let connStats = {
  totalConnections: 0,
  currentConnections: 0,
  peakConnections: 0,
  reconnections: 0,
  lastActivity: Date.now(),
};

gun.on('hi', () => {
  connStats.totalConnections++;
  connStats.currentConnections++;
  connStats.peakConnections = Math.max(
    connStats.peakConnections,
    connStats.currentConnections
  );
  connStats.lastActivity = Date.now();
  if (connStats.totalConnections > 1) connStats.reconnections++;
});

gun.on('bye', () => {
  connStats.currentConnections = Math.max(0, connStats.currentConnections - 1);
});
```

**驗證方式**
- 建立連線 → 等待 2 分鐘 → 確認連線未被 PaaS 關閉
- 拔網路線 → 確認 2 分鐘內偵測到斷線
- `/api/health` 回傳連線統計

**估計資源**
- 人力：0.5 人天
- 測試：需在 PaaS 環境測試

---

### 2.4 ST-04：RAD 資料維護與暫存檔清理

**問題說明**
非正常關機（SIGKILL、斷電）會殘留 `radata-*.tmp` 暫存檔。目前 git status 顯示有 2 個殘留的 .tmp 檔案。radata 目錄無大小限制，長期運行會持續增長。

**改善目標**
- 啟動時自動清理殘留的 .tmp 檔案
- radata 目錄加入 .gitignore
- 建立 radata 大小監控基線

**實作步驟**

1. 啟動時清理暫存檔（`index.js`）：
   ```javascript
   const fs = require('fs');
   const path = require('path');

   // 清理 RAD 暫存檔（非正常關機殘留）
   function cleanupRadTempFiles() {
     const cwd = __dirname;
     try {
       const files = fs.readdirSync(cwd);
       const tmpFiles = files.filter(f =>
         f.startsWith('radata-') && f.endsWith('.tmp')
       );
       tmpFiles.forEach(f => {
         try {
           fs.unlinkSync(path.join(cwd, f));
           console.log(`[啟動] 清理 RAD 暫存檔: ${f}`);
         } catch {}
       });
       if (tmpFiles.length > 0) {
         console.log(`[啟動] 共清理 ${tmpFiles.length} 個暫存檔`);
       }
     } catch {}
   }

   cleanupRadTempFiles();
   ```

2. 更新 `.gitignore`：
   ```gitignore
   radata/
   radata-*
   ```

3. 在 `/api/health` 加入 radata 大小指標：
   ```javascript
   function getRadataSize() {
     const dir = path.join(__dirname, 'radata');
     if (!fs.existsSync(dir)) return 0;
     let total = 0;
     fs.readdirSync(dir).forEach(f => {
       try { total += fs.statSync(path.join(dir, f)).size; } catch {}
     });
     return total;
   }
   ```

**驗證方式**
- 建立假的 `radata-test.tmp` → 重啟 → 確認被清理
- `/api/health` 回傳 `radata_size_bytes` 欄位

**估計資源**
- 人力：0.25 人天

---

### 2.5 ST-05：健康檢查端點強化

**問題說明**
現有 `/api/health` 僅回傳基本的 `{ status: 'ok' }`，缺少記憶體、連線數、radata 大小等關鍵指標。

**改善目標**
提供完整的運行時健康指標，支援外部監控系統（Uptime Kuma、Prometheus）接入。

**實作步驟**

```javascript
app.get('/api/health', (req, res) => {
  const mem = process.memoryUsage();
  const wsClients = server._webSocketServer
    ? server._webSocketServer.clients.size
    : 0;

  const health = {
    status: 'ok',
    version: require('./package.json').version,
    uptime_seconds: Math.floor(process.uptime()),

    // 記憶體指標
    memory: {
      heap_used_mb: +(mem.heapUsed / 1024 / 1024).toFixed(1),
      heap_total_mb: +(mem.heapTotal / 1024 / 1024).toFixed(1),
      rss_mb: +(mem.rss / 1024 / 1024).toFixed(1),
      external_mb: +(mem.external / 1024 / 1024).toFixed(1),
    },

    // WebSocket 指標
    websocket: {
      current_connections: wsClients,
      peak_connections: connStats.peakConnections,
      total_connections: connStats.totalConnections,
      reconnections: connStats.reconnections,
    },

    // 持久化指標
    persistence: {
      radata_size_bytes: getRadataSize(),
    },

    // 告警
    warnings: [
      ...(mem.heapUsed > 384 * 1024 * 1024 ? ['heap_high'] : []),
      ...(wsClients > 50 ? ['connections_high'] : []),
      ...(getRadataSize() > 100 * 1024 * 1024 ? ['radata_large'] : []),
    ],

    timestamp: new Date().toISOString(),
  };

  // 如果有任何 warning，狀態改為 degraded
  if (health.warnings.length > 0) {
    health.status = 'degraded';
  }

  res.json(health);
});
```

**驗證方式**
- 訪問 `/api/health` 確認所有欄位正確回傳
- 使用 Uptime Kuma 設定監控（每 60 秒 ping 一次）
- 手動觸發 warning 條件確認狀態變為 `degraded`

**估計資源**
- 人力：0.5 人天
- 工具：Uptime Kuma（可選，免費自建）

---

### 2.6 ST-06：結構化日誌系統

**問題說明**
目前僅使用 `console.log`，無結構化日誌，難以追蹤問題和統計使用情況。

**改善目標**
- 所有日誌輸出為 JSON 格式
- 區分日誌等級（info/warn/error）
- 支援日誌輪轉（防止日誌檔案無限增長）

**推薦工具**
`pino`（Node.js 最快的 JSON logger），選擇原因：零依賴、低開銷、Node.js 原生 stream。

**實作步驟**

1. 安裝：
   ```bash
   npm install pino pino-pretty
   ```

2. 建立 `lib/logger.js`：
   ```javascript
   const pino = require('pino');

   const logger = pino({
     level: process.env.LOG_LEVEL || 'info',
     transport: process.env.NODE_ENV !== 'production'
       ? { target: 'pino-pretty', options: { colorize: true } }
       : undefined,
     base: { service: 'gun-relay' },
   });

   module.exports = logger;
   ```

3. 替換 `console.log`：
   ```javascript
   const logger = require('./lib/logger');

   // 修前
   console.log(`Gun relay server is running on port ${port}`);

   // 修後
   logger.info({ port }, 'Gun relay server started');
   ```

4. PM2 日誌輪轉：
   ```bash
   pm2 install pm2-logrotate
   pm2 set pm2-logrotate:max_size 50M
   pm2 set pm2-logrotate:retain 7
   ```

**驗證方式**
- 啟動後確認日誌為 JSON 格式
- 生產模式無 pretty print
- 日誌檔案超過 50MB 時自動輪轉

**估計資源**
- 人力：0.5 人天

---

### 2.7 ST-07：自動備份策略

**問題說明**
radata 目錄為 Gun.js 唯一的持久化存儲，無備份策略。磁碟損壞或誤刪將導致資料永久遺失。

**改善目標**
- 每日自動備份 radata 目錄
- 保留最近 7 天的備份
- 備份驗證機制

**實作步驟**

建立 `scripts/backup-radata.ps1`：

```powershell
# Gun Server radata 自動備份
$RelayDir = "D:\Source\my-gun-relay"
$BackupDir = "$RelayDir\backups"
$RetentionDays = 7

# 建立備份目錄
if (!(Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir }

# 壓縮備份
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = "$BackupDir\radata_$timestamp.zip"
Compress-Archive -Path "$RelayDir\radata" -DestinationPath $backupFile -Force

# 清理過期備份
Get-ChildItem "$BackupDir\radata_*.zip" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
  Remove-Item -Force

# 輸出結果
$size = (Get-Item $backupFile).Length / 1MB
Write-Host "[備份] 完成: $backupFile ($([math]::Round($size, 2)) MB)"
```

設定 Windows Task Scheduler（每日 03:00 執行）。

**驗證方式**
- 手動執行備份腳本 → 確認 zip 檔案包含完整 radata 目錄
- 等待 8 天 → 確認第 1 天備份被自動清理
- 模擬還原：解壓 zip → 替換 radata → 重啟 Gun → 確認資料恢復

**估計資源**
- 人力：0.25 人天
- 備份空間：約 50MB/週（以目前 2MB radata × 7 天計算，含壓縮）

---

## 3. 安全性強化方案

### 3.1 SE-01：TLS/HTTPS 終端

**風險描述**
目前 Relay 以 HTTP（明文）運行在 port 8765。雖然 Gun.js 訊息已有 SEA E2E 加密，但 WebSocket 握手階段、健康檢查端點、以及 Gun 的 DAM 協定 header 仍以明文傳輸，可被中間人攔截。

**改善目標**
- 所有連線使用 HTTPS/WSS
- TLS 1.2+ 且禁用弱密碼套件
- 支援自動憑證更新

**推薦方案**

| 方案 | 優點 | 缺點 | 適用場景 |
|------|------|------|---------|
| **A. Nginx 反向代理 + Let's Encrypt** | 成熟、高效能、自動續簽 | 需額外部署 Nginx | **自建伺服器（推薦）** |
| B. Node.js 直接 HTTPS | 簡單、無依賴 | 需手動管理憑證 | 開發/測試 |
| C. Cloudflare Tunnel | 零配置 TLS、DDoS 防護 | 依賴第三方、WebSocket 支援需設定 | 快速部署 |
| D. PaaS 內建 TLS | 零配置 | 綁定平台 | 已在 Render.com |

**方案 A 實作步驟（Nginx 反向代理）**

1. 安裝 Nginx + Certbot：
   ```bash
   # Linux（如未來遷移到 VPS）
   sudo apt install nginx certbot python3-certbot-nginx
   ```

2. Nginx 配置（`/etc/nginx/sites-available/gun-relay`）：
   ```nginx
   server {
       listen 80;
       server_name gun-relay.yourdomain.com;
       return 301 https://$host$request_uri;
   }

   server {
       listen 443 ssl http2;
       server_name gun-relay.yourdomain.com;

       ssl_certificate /etc/letsencrypt/live/gun-relay.yourdomain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/gun-relay.yourdomain.com/privkey.pem;
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
       ssl_prefer_server_ciphers on;

       # HSTS（啟用後無法降級回 HTTP）
       # add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

       # WebSocket 支援（Gun.js 必需）
       location / {
           proxy_pass http://127.0.0.1:8765;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;

           # WebSocket 超時（Gun.js 心跳）
           proxy_read_timeout 120s;
           proxy_send_timeout 120s;
       }

       # 健康檢查無需 WebSocket 升級
       location = /api/health {
           proxy_pass http://127.0.0.1:8765;
           proxy_set_header Host $host;
       }
   }
   ```

3. 取得憑證：
   ```bash
   sudo certbot --nginx -d gun-relay.yourdomain.com
   ```

4. 自動續簽（Certbot 預設已設定 cron）。

**方案 B 實作步驟（Node.js 直接 HTTPS，Windows 本機開發用）**

```javascript
const https = require('https');
const fs = require('fs');

// 自簽憑證（僅開發用）
// 生產環境應使用 Let's Encrypt 或正式 CA 憑證
const server = https.createServer({
  key: fs.readFileSync('certs/server.key'),
  cert: fs.readFileSync('certs/server.crt'),
  minVersion: 'TLSv1.2',
}, app);

const gun = Gun({ web: server, radisk: true, axe: false });
server.listen(8765, () => {
  console.log('[Relay] HTTPS server running on port 8765');
});
```

**驗證方式**
- `curl -v https://gun-relay.yourdomain.com/api/health` 確認 TLS 連線
- SSL Labs 測試（ssllabs.com）評分 ≥ A
- 前端 `wss://` 連線正常

**估計資源**
- 人力：1 人天（方案 A）/ 0.25 人天（方案 B）
- 費用：Let's Encrypt 免費 / 正式 CA 憑證約 $10-50/年

---

### 3.2 SE-02：CORS 策略收緊

**風險描述**
目前 CORS 設定為 `origin: '*'`，允許任何網站的 JavaScript 連線到 Relay。雖然 Gun.js Relay 的設計理念是公開中繼節點，但若為私有部署，應限制來源。

**改善目標**
- 私有部署時限制允許的 origin 清單
- 記錄來自非預期 origin 的請求

**實作步驟**

```javascript
const ALLOWED_ORIGINS = process.env.CORS_ORIGINS
  ? process.env.CORS_ORIGINS.split(',').map(s => s.trim())
  : ['*'];  // 預設仍開放（向下相容）

app.use(cors({
  origin: (origin, callback) => {
    // 無 origin 的請求（如 Server-to-Server）允許通過
    if (!origin) return callback(null, true);

    if (ALLOWED_ORIGINS.includes('*') || ALLOWED_ORIGINS.includes(origin)) {
      callback(null, true);
    } else {
      logger.warn({ origin }, 'CORS 拒絕未授權來源');
      callback(new Error('不允許的來源'), false);
    }
  },
  credentials: false, // Gun.js 不需要 credentials
}));
```

**環境變數**：
```bash
# 私有部署時設定
CORS_ORIGINS=https://myapp.example.com,https://localhost:3000
```

**驗證方式**
- 設定 CORS_ORIGINS → 從未授權 origin 發請求 → 確認被拒絕
- 不設定 CORS_ORIGINS → 確認向下相容（允許所有）

**估計資源**
- 人力：0.25 人天

---

### 3.3 SE-03：Gun.js 訊息大小限制

**風險描述**
Gun.js Relay 無內建的訊息大小限制。惡意用戶可以透過 `gun.get('any').put(giant_data)` 灌入大量資料，導致：
- radata 快速膨脹
- 記憶體耗盡
- 其他用戶的 `.on()` 同步效能下降

**改善目標**
- 單筆 put 操作限制在 10KB 以內
- 超過限制的 put 被靜默丟棄並記錄
- HTTP 請求 body 限制在 1MB

**實作步驟**

```javascript
// 1. Express body 大小限制
app.use(express.json({ limit: '1mb' }));

// 2. Gun.js 層級 put 大小限制
const MAX_PUT_SIZE_BYTES = 10 * 1024; // 10KB

gun.on('in', function(msg) {
  if (msg.put) {
    const size = JSON.stringify(msg.put).length;
    if (size > MAX_PUT_SIZE_BYTES) {
      logger.warn({
        size,
        limit: MAX_PUT_SIZE_BYTES,
        keys: Object.keys(msg.put).slice(0, 5),
      }, 'Gun put 大小超過限制，已丟棄');
      return; // 不傳遞給下游
    }
  }
  this.to.next(msg); // 正常傳遞
});
```

**驗證方式**
- 發送 > 10KB 的 put → 確認被丟棄且有日誌
- 發送 < 10KB 的 put → 確認正常處理
- 發送 > 1MB 的 HTTP 請求 → 確認回傳 413

**估計資源**
- 人力：0.25 人天

---

### 3.4 SE-04：連線速率限制（Relay 層）

**風險描述**
Relay 端無連線限制，單一 IP 可建立無限 WebSocket 連線，消耗伺服器資源。

**改善目標**
- 單一 IP 最多 5 個 WebSocket 連線
- 每分鐘最多 10 個新連線
- 超過限制時回傳 429 並記錄

**實作步驟**

```javascript
const connTracker = new Map(); // IP → { connections: number, lastReset: number }
const MAX_CONN_PER_IP = 5;
const MAX_NEW_CONN_PER_MIN = 10;
const WINDOW_MS = 60 * 1000;

// HTTP 層速率限制（影響 WebSocket 升級握手）
app.use((req, res, next) => {
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim()
    || req.socket.remoteAddress;
  const now = Date.now();

  let entry = connTracker.get(ip);
  if (!entry || now - entry.lastReset > WINDOW_MS) {
    entry = { connections: 0, newInWindow: 0, lastReset: now };
  }

  entry.newInWindow++;
  connTracker.set(ip, entry);

  if (entry.newInWindow > MAX_NEW_CONN_PER_MIN) {
    logger.warn({ ip, count: entry.newInWindow }, '連線速率超限');
    return res.status(429).json({ error: 'Too many connections' });
  }

  next();
});

// 定期清理追蹤記錄
setInterval(() => {
  const cutoff = Date.now() - WINDOW_MS;
  for (const [ip, entry] of connTracker) {
    if (entry.lastReset < cutoff) connTracker.delete(ip);
  }
}, WINDOW_MS);
```

**驗證方式**
- 從同一 IP 快速建立 11 個連線 → 第 11 個回傳 429
- 等待 1 分鐘 → 確認限制重置

**估計資源**
- 人力：0.5 人天

---

### 3.5 SE-05：安全 HTTP Headers

**風險描述**
缺少標準安全 headers，瀏覽器可能不啟用安全防護（如 XSS 過濾、點擊劫持防護）。

**改善目標**
加入業界標準的安全 HTTP headers。

**推薦工具**
`helmet`（Express 安全 middleware），一行啟用 11 種安全 header。

**實作步驟**

```bash
npm install helmet
```

```javascript
const helmet = require('helmet');

app.use(helmet({
  contentSecurityPolicy: false,  // Gun.js 需要 inline script
  crossOriginEmbedderPolicy: false, // Gun.js 需要跨域資源
}));
```

**啟用的安全 Headers**：

| Header | 效果 |
|--------|------|
| `X-Content-Type-Options: nosniff` | 防止 MIME 類型嗅探 |
| `X-Frame-Options: SAMEORIGIN` | 防止點擊劫持 |
| `X-XSS-Protection: 0` | 停用過時的 XSS 過濾（由 CSP 取代） |
| `Strict-Transport-Security` | 強制 HTTPS（需先啟用 TLS） |
| `X-DNS-Prefetch-Control: off` | 防止 DNS 預取洩漏 |
| `X-Download-Options: noopen` | IE 下載防護 |
| `X-Permitted-Cross-Domain-Policies: none` | 防止 Flash/PDF 跨域 |
| `Referrer-Policy: no-referrer` | 不洩漏 referrer |

**驗證方式**
- `curl -I https://gun-relay.yourdomain.com` 確認 headers 存在
- SecurityHeaders.com 掃描評分 ≥ B

**估計資源**
- 人力：0.25 人天

---

### 3.6 SE-06：金鑰管理強化

**風險描述**
Bot 的 ECDH 私鑰以明文 JSON 存於磁碟（`keypair.json`），檔案系統存取即洩露。金鑰無輪替機制，一旦洩露無法撤銷。

**改善目標**
- 私鑰可選加密存儲（環境變數設定密碼）
- 金鑰定期輪替（每 30 天）
- 輪替時自動重新公告 epub

**實作步驟**（整合於 `bot.js`）

```javascript
const KEYPAIR_ROTATION_DAYS = parseInt(process.env.KEYPAIR_ROTATION_DAYS || '30');
const KEY_PASSPHRASE = process.env.BOT_KEY_PASSPHRASE;

// 加密存儲
async function saveKeypair(pair) {
  const data = KEY_PASSPHRASE
    ? { encrypted: await SEA.encrypt(JSON.stringify(pair), KEY_PASSPHRASE) }
    : pair;
  fs.writeFileSync(KEYPAIR_PATH, JSON.stringify(data, null, 2), 'utf8');
  fs.writeFileSync(KEYPAIR_META_PATH, JSON.stringify({
    createdAt: Date.now(),
    rotationDays: KEYPAIR_ROTATION_DAYS,
    encrypted: !!KEY_PASSPHRASE,
  }), 'utf8');
}

async function loadKeypair() {
  const raw = JSON.parse(fs.readFileSync(KEYPAIR_PATH, 'utf8'));
  if (raw.encrypted && KEY_PASSPHRASE) {
    return JSON.parse(await SEA.decrypt(raw.encrypted, KEY_PASSPHRASE));
  }
  return raw;
}

// 輪替檢查
async function checkKeypairRotation() {
  if (!fs.existsSync(KEYPAIR_META_PATH)) return false;
  const meta = JSON.parse(fs.readFileSync(KEYPAIR_META_PATH, 'utf8'));
  const daysSince = (Date.now() - meta.createdAt) / 86400000;
  return daysSince > KEYPAIR_ROTATION_DAYS;
}
```

**驗證方式**
- 設定 `BOT_KEY_PASSPHRASE=test123` → 確認 keypair.json 內容已加密
- 修改 meta 的 createdAt 為 31 天前 → 確認輪替觸發
- 輪替後確認 Relay 上的 epub 更新

**估計資源**
- 人力：0.5 人天

---

### 3.7 SE-07：Node.js 執行環境安全

**風險描述**
Node.js 版本未鎖定、npm 依賴未定期審計。過時的 Node.js 可能有已知漏洞。

**改善目標**
- 鎖定 Node.js 最低版本要求
- 定期依賴審計
- 啟動時檢查環境安全

**實作步驟**

1. `package.json` 加入引擎限制：
   ```json
   {
     "engines": {
       "node": ">=18.0.0"
     }
   }
   ```

2. 建立 `scripts/security-audit.ps1`：
   ```powershell
   Write-Host "=== Gun Server 安全審計 ==="

   # Node.js 版本檢查
   $nodeVersion = node -v
   Write-Host "[Node.js] 版本: $nodeVersion"

   # npm audit
   Write-Host "`n[npm audit] 掃描已知漏洞..."
   Set-Location D:\Source\my-gun-relay
   npm audit --production

   # 依賴更新檢查
   Write-Host "`n[npm outdated] 過時套件..."
   npm outdated

   Write-Host "`n=== 審計完成 ==="
   ```

3. 每月執行一次（可加入 Windows Task Scheduler）。

**驗證方式**
- Node.js < 18 時啟動失敗
- `npm audit` 零漏洞
- `npm outdated` 無重大版本落後

**估計資源**
- 人力：0.25 人天（初次設定），每月 0.1 人天（例行審計）

---

## 4. 實作與驗證流程

### 4.1 實作優先級與排程

```
Phase 1（緊急，第 1 週）
├── ST-01 PM2 進程管理器         [0.5d] ★ 最高優先
├── ST-04 RAD 暫存檔清理         [0.25d]
├── SE-05 安全 HTTP Headers      [0.25d]
└── SE-03 訊息大小限制            [0.25d]
    小計：1.25 人天

Phase 2（重要，第 2 週）
├── SE-01 TLS/HTTPS 終端         [1d] ★ 安全性最高優先
├── ST-05 健康檢查端點強化        [0.5d]
├── SE-02 CORS 策略收緊           [0.25d]
└── SE-04 連線速率限制             [0.5d]
    小計：2.25 人天

Phase 3（強化，第 3-4 週）
├── ST-06 結構化日誌系統           [0.5d]
├── ST-07 自動備份策略             [0.25d]
├── ST-03 WebSocket 保活           [0.5d]
├── SE-06 金鑰管理強化             [0.5d]
└── SE-07 Node.js 環境安全         [0.25d]
    小計：2.0 人天

總計：5.5 人天
```

### 4.2 前置作業

| 項目 | 說明 | 負責人 |
|------|------|--------|
| 備份現有程式碼 | `git tag v-pre-optimization` | 開發 |
| 備份 radata 目錄 | 手動壓縮 radata/ 存至安全位置 | 開發 |
| 建立測試環境 | 本機 + 測試用 Relay | 開發 |
| 確認 Node.js 版本 | `node -v` ≥ 18.0.0 | 開發 |
| npm audit baseline | 記錄目前的 audit 結果 | 開發 |

### 4.3 每項變更的驗證流程

```
1. 本機開發
   └── 修改程式碼 → 本機啟動測試 → 確認功能正常

2. 單元驗證
   └── 針對性測試（見各方案的「驗證方式」）

3. 整合驗證
   └── 前端（index.html）+ Relay（index.js）+ Bot（bot.js）聯調
   └── 確認 E2E 加密通訊正常
   └── 確認所有 /api/ 端點回應正確

4. 壓力測試（Phase 2 完成後）
   └── 10 個並行 WebSocket 連線
   └── 持續 30 分鐘無記憶體洩漏
   └── 斷線重連 10 次無資料遺失

5. 部署
   └── git push → 觀察 PM2 日誌
   └── 確認 /api/health 狀態正常
```

### 4.4 回滾計畫

| 情境 | 回滾步驟 |
|------|---------|
| PM2 啟動失敗 | `pm2 delete gun-relay` → 回退至 `node index.js` |
| TLS 配置錯誤 | 移除 Nginx 配置 → 直接暴露 HTTP 端口 |
| 連線限制過嚴 | 調高 `MAX_CONN_PER_IP` 或移除中介層 |
| 任何嚴重問題 | `git checkout v-pre-optimization` → 重新部署 |

---

## 5. 風險與應變措施

### 5.1 風險評估矩陣

| 風險 | 可能性 | 影響 | 風險等級 | 應變措施 |
|------|--------|------|---------|---------|
| PM2 與 Gun.js 不相容 | 低 | 高 | 中 | 回退至直接啟動 + systemd |
| TLS 憑證過期 | 中 | 高 | 高 | Certbot 自動續簽 + 過期前 7 天告警 |
| 訊息大小限制過嚴 | 中 | 中 | 中 | 可透過環境變數 `MAX_PUT_SIZE_KB` 動態調整 |
| CORS 收緊導致合法用戶被拒 | 低 | 中 | 低 | 預設 `*`（向下相容），僅私有部署才收緊 |
| Gun.js 版本升級破壞 API | 低 | 高 | 中 | 鎖定 package-lock.json + 升級前在測試環境驗證 |
| radata 損壞 | 低 | 高 | 中 | 每日自動備份 + 7 天保留 |
| 記憶體洩漏（長期運行） | 中 | 中 | 中 | PM2 自動重啟（512MB 上限）+ heap 監控告警 |

### 5.2 緊急應變流程

```
監控告警觸發
  │
  ├── 記憶體超限（heap > 512MB）
  │   └── PM2 自動重啟（max_memory_restart）
  │   └── 若持續超限 → 分析 heap dump → 找到洩漏源
  │
  ├── 連線數異常飆升
  │   └── 檢查 /api/health 的 websocket.current_connections
  │   └── 若為 DDoS → 啟用防火牆 IP 封鎖
  │   └── 若為合法流量 → 提高 MAX_CONN_PER_IP
  │
  ├── TLS 憑證即將過期
  │   └── certbot renew --dry-run 測試
  │   └── certbot renew 正式續簽
  │   └── nginx -s reload 重載配置
  │
  └── radata 損壞
      └── 停止 Gun Server
      └── 從最近備份還原 radata/
      └── 重啟 Gun Server
      └── 驗證資料完整性
```

---

## 6. 後續維運建議

### 6.1 監控項目

| 指標 | 監控方式 | 告警閾值 |
|------|---------|---------|
| 伺服器可用性 | Uptime Kuma ping `/api/health` | 連續 3 次失敗 |
| 記憶體使用 | `/api/health` → `memory.heap_used_mb` | > 384 MB |
| WebSocket 連線數 | `/api/health` → `websocket.current_connections` | > 50 |
| radata 大小 | `/api/health` → `persistence.radata_size_bytes` | > 100 MB |
| TLS 憑證到期 | Certbot / 外部監控 | 到期前 7 天 |
| npm 漏洞 | `npm audit` 定期掃描 | 任何 high/critical |
| PM2 重啟次數 | `pm2 monit` | 1 小時內 > 3 次 |

### 6.2 日誌審查

| 頻率 | 檢查項目 |
|------|---------|
| 每日 | 過濾 `level: "error"` 或 `level: "warn"` 日誌 |
| 每週 | 檢查 WebSocket 連線統計、訊息丟棄記錄 |
| 每月 | npm audit、Node.js 版本檢查、備份完整性驗證 |

### 6.3 定期審查

| 頻率 | 項目 |
|------|------|
| 每月 | 依賴安全審計（`npm audit`） |
| 每季 | Gun.js 版本檢查、Node.js LTS 升級評估 |
| 每半年 | 完整安全架構審查（含此計畫更新） |
| 每年 | TLS 憑證策略檢視、密碼套件更新 |

### 6.4 文件更新機制

此計畫為**活文件**，應在以下時機更新：

- Gun.js 發布新版本
- 部署架構變更（如遷移 PaaS）
- 發現新的安全風險或漏洞
- 完成任何優化方案後，更新狀態欄

---

## 7. 附錄

### 7.1 參考文件

| 文件 | 用途 |
|------|------|
| `gun-js-optimization-report-20260228.md` | 應用層 27 項修補方案（互補本計畫） |
| [Gun.js GitHub](https://github.com/amark/gun) | 官方文檔與原始碼 |
| [Gun.js SEA 文檔](https://gun.eco/docs/SEA) | 加密模組文檔 |
| [OWASP Node.js 安全清單](https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html) | Node.js 安全最佳實踐 |
| [PM2 官方文檔](https://pm2.keymetrics.io/docs/usage/quick-start/) | 進程管理器使用指南 |

### 7.2 版本資訊

| 套件 | 目前版本 | 建議最低版本 |
|------|---------|-------------|
| gun | 0.2020.1241 | 0.2020.1241（已是最新） |
| express | 4.22.1 | 4.18.0+ |
| cors | 2.8.6 | 2.8.5+ |
| Node.js | 未鎖定 | ≥ 18.0.0 LTS |
| npm | 未鎖定 | ≥ 9.0.0 |
| 新增 pino | — | ≥ 8.0.0 |
| 新增 helmet | — | ≥ 7.0.0 |
| 新增 PM2 | — | ≥ 5.3.0 |

### 7.3 配置範例彙總

#### `ecosystem.config.js`（PM2 配置）

```javascript
module.exports = {
  apps: [{
    name: 'gun-relay',
    script: 'index.js',
    instances: 1,
    exec_mode: 'fork',
    max_memory_restart: '512M',
    restart_delay: 3000,
    max_restarts: 10,
    min_uptime: '30s',
    watch: false,
    env: {
      NODE_ENV: 'production',
      PORT: 8765,
      LOG_LEVEL: 'info',
      MAX_PUT_SIZE_KB: 10,
      MAX_CONN_PER_IP: 5,
      KEYPAIR_ROTATION_DAYS: 30,
    },
  }]
};
```

#### 環境變數一覽

| 變數名 | 預設值 | 說明 |
|--------|--------|------|
| `PORT` | 8765 | 監聽埠號 |
| `NODE_ENV` | development | 執行環境（production 啟用 JSON 日誌） |
| `GUN_PEERS` | （無） | 遠端 Relay 位址（逗號分隔） |
| `CORS_ORIGINS` | `*` | 允許的 CORS origin（逗號分隔） |
| `LOG_LEVEL` | info | 日誌等級（debug/info/warn/error） |
| `MAX_PUT_SIZE_KB` | 10 | Gun put 操作大小上限（KB） |
| `MAX_CONN_PER_IP` | 5 | 單一 IP 最大連線數 |
| `BOT_KEY_PASSPHRASE` | （無） | Bot 私鑰加密密碼（可選） |
| `KEYPAIR_ROTATION_DAYS` | 30 | 金鑰輪替天數 |

### 7.4 方案追蹤表

| 編號 | 方案名稱 | 類型 | Phase | 估時 | 狀態 |
|------|---------|------|-------|------|------|
| ST-01 | PM2 進程管理器 | 穩定性 | 1 | 0.5d | ⬜ 待實施 |
| ST-02 | Cluster 模式評估 | 穩定性 | — | — | ✅ 已評估（維持單進程） |
| ST-03 | WebSocket 保活 | 穩定性 | 3 | 0.5d | ⬜ 待實施 |
| ST-04 | RAD 暫存檔清理 | 穩定性 | 1 | 0.25d | ⬜ 待實施 |
| ST-05 | 健康檢查強化 | 穩定性 | 2 | 0.5d | ⬜ 待實施 |
| ST-06 | 結構化日誌 | 穩定性 | 3 | 0.5d | ⬜ 待實施 |
| ST-07 | 自動備份 | 穩定性 | 3 | 0.25d | ⬜ 待實施 |
| SE-01 | TLS/HTTPS | 安全性 | 2 | 1.0d | ⬜ 待實施 |
| SE-02 | CORS 收緊 | 安全性 | 2 | 0.25d | ⬜ 待實施 |
| SE-03 | 訊息大小限制 | 安全性 | 1 | 0.25d | ⬜ 待實施 |
| SE-04 | 連線速率限制 | 安全性 | 2 | 0.5d | ⬜ 待實施 |
| SE-05 | 安全 Headers | 安全性 | 1 | 0.25d | ⬜ 待實施 |
| SE-06 | 金鑰管理 | 安全性 | 3 | 0.5d | ⬜ 待實施 |
| SE-07 | 環境安全 | 安全性 | 3 | 0.25d | ⬜ 待實施 |

---

> **文件狀態**：v1.0.0 待審核
> **下次審查日期**：2026-09-02（6 個月後）
> **知識庫位置**：技術文檔 > 伺服器優化
> **審核人**：（待指定資深系統工程師）
