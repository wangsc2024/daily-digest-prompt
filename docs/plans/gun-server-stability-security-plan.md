# Gun Relay Server 穩定性與安全性優化計畫 v1.0

> **文件狀態**: v1.0 定稿
> **建立日期**: 2026-03-08
> **負責人**: 開發 / 運維 / 資安
> **標籤**: `Gun.js`, `Stability`, `Security`, `Ops`, `生產環境`
> **系列**: gunjs-decentralized-db（optimization 階段）

---

## 1. 背景說明

### 1.1 目標系統

本 Gun relay server（`my-gun-relay/index.js`）是一個基於 Node.js + Express + Gun.js 的即時訊息推送中繼節點，承擔以下職責：

- **P2P 中繼**：為 Gun.js 客戶端（bot.js、前端 index.html）提供 WebSocket 中繼
- **SEA 加密通訊**：透過 ECDH 金鑰交換建立端對端加密通道
- **Webhook 端點**：接收 make.com 外部自動化任務（`POST /api/task`）
- **資料持久化**：RAD（Radisk）本地儲存（`radata/` 目錄）

### 1.2 部署環境

| 項目 | 現況 |
|------|------|
| **作業系統** | Windows 10/11（MINGW64 + PowerShell 7） |
| **Node.js 版本** | >= 18（建議升級至 20 LTS） |
| **Gun.js 版本** | ^0.2020.1241（relay）/ ^0.2020.1235（bot） |
| **依賴套件** | express ^4.22.1, cors ^2.8.6, gun ^0.2020.1241 |
| **埠號** | 8765（relay）、3001（bot）、3002（groq-relay） |
| **外部 peer** | `wss://gun.pdoont.us.kg/gun`（可選同步） |
| **監控** | Cloudflare Workers keepalive（每 10 分鐘 GET /api/health） |
| **排程** | Windows Task Scheduler（每日 00:15 重啟） |

### 1.3 已有防護（bot.js 客戶端）

bot.js 已實施的安全措施（供 relay 參考移植）：

- ✅ `helmet` 安全標頭
- ✅ `express-rate-limit`（60 req/min API、300 req/min worker）
- ✅ timing-safe token 比較（`crypto.timingSafeEqual`）
- ✅ 全域 `unhandledRejection` / `uncaughtException` 處理
- ✅ Graceful shutdown（SIGTERM/SIGINT）
- ✅ 訊息去重 + 定時清理（防記憶體洩漏）
- ✅ SEA 簽章驗證（防 MITM）

---

## 2. 問題分析

### 2.1 安全漏洞清單

| # | 嚴重度 | 問題 | 現況 | 影響 |
|---|--------|------|------|------|
| S1 | 🔴 高 | 無 Rate Limiting | relay 端完全沒有速率限制 | DDoS / 暴力攻擊可導致服務癱瘓 |
| S2 | 🔴 高 | 無安全標頭 | 缺少 `helmet` 或等效設定 | XSS、clickjacking、MIME sniffing 風險 |
| S3 | 🔴 高 | Token 比較不安全 | `provided !== apiKey`（字串直接比較） | Timing attack 可逐位元破解 API key |
| S4 | 🟡 中 | CORS 過於寬鬆 | `origin: '*'` 適用 Gun peer，但 `/api/task` 不應如此 | webhook 端點可被任意來源呼叫 |
| S5 | 🟡 中 | 未使用 WSS | 本地部署用 WS，外部透過 Cloudflare 代理 | 若直接暴露則明文傳輸 |
| S6 | 🟡 中 | API key 可選 | `if (apiKey)` — 未設定時跳過驗證 | 忘記設定環境變數 = 無認證 |
| S7 | 🟡 中 | Gun.js 版本差異 | relay ^0.2020.1241 vs bot ^0.2020.1235 | 潛在相容性問題與安全修補缺漏 |
| S8 | 🟢 低 | 無 IP 黑名單機制 | 惡意 IP 可持續攻擊 | 自動化防護不足 |
| S9 | 🟢 低 | 靜態檔案全部暴露 | `express.static(__dirname)` | server 原始碼可能被直接下載 |

### 2.2 穩定性缺陷清單

| # | 嚴重度 | 問題 | 現況 | 影響 |
|---|--------|------|------|------|
| T1 | 🔴 高 | 無全域例外處理 | 缺少 unhandledRejection / uncaughtException | 未捕獲錯誤直接 crash |
| T2 | 🔴 高 | 單進程部署 | `node index.js` 直接執行 | 一個 crash = 全服務中斷 |
| T3 | 🟡 中 | 無 Graceful Shutdown | 無 SIGTERM/SIGINT 處理 | 強制關閉可能損壞 radata |
| T4 | 🟡 中 | 無記憶體洩漏偵測 | 長期運行無監控 | 緩慢 OOM 導致靜默失效 |
| T5 | 🟡 中 | Heartbeat 僅外部 | Cloudflare Workers 10 分鐘一次 | 最長 10 分鐘才發現服務離線 |
| T6 | 🟡 中 | 無自動重連 peer | 外部 peer 斷線後不重連 | P2P 同步靜默中斷 |
| T7 | 🟢 低 | radata 無備份策略 | 本地唯一份 | 磁碟故障 = 資料全失 |
| T8 | 🟢 低 | 日誌不結構化 | `console.log` 純文字 | 難以自動化分析問題 |

---

## 3. 穩定性優化方案

### 3.1 進程管理：PM2 多進程部署

**目的**：消除單點故障，自動重啟 crash 的進程。

**安裝與配置**：

```bash
npm install -g pm2
```

**ecosystem.config.js**（建立於 `my-gun-relay/` 根目錄）：

```javascript
module.exports = {
  apps: [{
    name: 'gun-relay',
    script: 'index.js',
    instances: 1,           // Gun.js 的 radata 不支援多進程共享寫入
    exec_mode: 'fork',      // 非 cluster（Gun 的 WebSocket 需要固定進程）
    watch: false,
    max_memory_restart: '300M',  // 記憶體超過 300MB 自動重啟
    exp_backoff_restart_delay: 100, // 指數退避重啟延遲
    max_restarts: 10,        // 10 分鐘內最多重啟 10 次
    min_uptime: '10s',       // 啟動後至少存活 10s 才算正常
    error_file: './logs/pm2-error.log',
    out_file: './logs/pm2-out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss',
    env: {
      NODE_ENV: 'production',
      PORT: 8765,
    }
  }]
};
```

> **⚠️ 重要**：Gun.js 的 RAD 儲存使用檔案鎖定，**不可** 使用 `cluster` 多實例模式。使用 `fork` + `instances: 1` + 自動重啟即可。

**啟動與管理**：

```bash
pm2 start ecosystem.config.js
pm2 save                    # 儲存進程列表
pm2 startup                 # 設定開機自啟（Windows 用 pm2-windows-startup）
pm2 monit                   # 即時監控
```

### 3.2 全域例外處理與 Graceful Shutdown

**目的**：防止未捕獲錯誤直接 crash，並確保正常關閉時 radata 不損壞。

在 `index.js` 加入以下程式碼（建議放在檔案最前面，`const express = require('express')` 之前）：

```javascript
// ─── 全域例外處理 ──────────────────────────────────────────
process.on('unhandledRejection', (reason, promise) => {
    console.error('[relay] unhandledRejection:', reason);
    // 不 exit，讓 PM2 處理
});

process.on('uncaughtException', (err) => {
    console.error('[relay] uncaughtException:', err);
    // 給 Gun 1s 時間 flush radata，然後退出讓 PM2 重啟
    setTimeout(() => process.exit(1), 1000);
});
```

**Graceful Shutdown**（放在 `server.listen()` 之後）：

```javascript
// ─── Graceful Shutdown ─────────────────────────────────────
function gracefulShutdown(signal) {
    console.log(`[relay] 收到 ${signal}，正在優雅關閉…`);
    server.close(() => {
        console.log('[relay] HTTP 伺服器已關閉');
        // Gun.js 會在進程結束時自動 flush radata
        process.exit(0);
    });
    // 5s 後強制退出
    setTimeout(() => {
        console.error('[relay] 強制關閉（超時 5s）');
        process.exit(1);
    }, 5000);
}

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
```

### 3.3 Heartbeat 與自動重連

**目的**：自我偵測健康狀態 + 斷線 peer 自動重連。

#### 3.3.1 增強 Health Check 端點

```javascript
// 增強版 health check（取代現有的簡易版）
const startTime = Date.now();
let requestCount = 0;

app.get('/api/health', (req, res) => {
    requestCount++;
    const memUsage = process.memoryUsage();
    res.json({
        status: 'ok',
        uptime: Math.floor(process.uptime()),
        uptimeHuman: formatUptime(process.uptime()),
        peers: peers.length,
        relayReady: !!sharedSecret,
        memory: {
            rss: Math.round(memUsage.rss / 1024 / 1024) + 'MB',
            heapUsed: Math.round(memUsage.heapUsed / 1024 / 1024) + 'MB',
            heapTotal: Math.round(memUsage.heapTotal / 1024 / 1024) + 'MB',
        },
        requestCount,
        timestamp: new Date().toISOString(),
    });
});

function formatUptime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
}
```

#### 3.3.2 自我 Heartbeat 檢查

```javascript
// 每 60 秒自我檢查（內部 heartbeat）
setInterval(() => {
    const mem = process.memoryUsage();
    const heapMB = Math.round(mem.heapUsed / 1024 / 1024);

    // 記憶體警告
    if (heapMB > 200) {
        console.warn(`[relay] ⚠️ 記憶體使用偏高: ${heapMB}MB`);
    }

    // 若 sharedSecret 遺失嘗試重新初始化
    if (!sharedSecret && relayPair) {
        console.log('[relay] sharedSecret 遺失，嘗試重新初始化…');
        initRelayIdentity().catch(e =>
            console.error('[relay] 重新初始化失敗:', e.message)
        );
    }
}, 60_000);
```

### 3.4 負載均衡與流量限速

**目的**：防止突發流量導致服務失效。

#### 3.4.1 NGINX 反向代理（推薦生產部署）

若部署至 VPS/雲端，建議在 Gun relay 前方加 NGINX：

```nginx
# /etc/nginx/sites-available/gun-relay
upstream gun_relay {
    server 127.0.0.1:8765;
}

server {
    listen 443 ssl http2;
    server_name gun.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/gun.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/gun.yourdomain.com/privkey.pem;

    # WebSocket 代理
    location /gun {
        proxy_pass http://gun_relay;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;  # WebSocket 長連線
        proxy_send_timeout 86400s;
    }

    # API 端點
    location /api/ {
        proxy_pass http://gun_relay;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # API 層級 Rate Limiting
        limit_req zone=api burst=10 nodelay;
    }

    # 拒絕直接存取靜態檔案
    location ~ \.(js|json|md)$ {
        deny all;
    }
}

# Rate Limiting 區域定義
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;
```

#### 3.4.2 應用層 Rate Limiting（即時可用）

不需 NGINX，直接在 Express 層實作：

```javascript
const rateLimit = require('express-rate-limit');

// API 端點限速（/api/*）
const apiLimiter = rateLimit({
    windowMs: 60 * 1000,    // 1 分鐘
    max: 30,                // 最多 30 次
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'Too many requests, try again later' },
    keyGenerator: (req) => req.ip || req.socket.remoteAddress,
});

app.use('/api/', apiLimiter);

// WebSocket 連線不受 Express rate limit 控制
// Gun.js WebSocket 由 Gun 內部處理
```

### 3.5 資料備份策略

**目的**：防止 radata 損壞或磁碟故障導致資料遺失。

```powershell
# backup-radata.ps1 — 每日排程備份
$RelayDir = "D:\Source\my-gun-relay"
$BackupDir = "D:\Backups\gun-relay"
$Date = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupPath = Join-Path $BackupDir "radata_$Date"

# 建立備份目錄
New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null

# 複製 radata（排除鎖定檔案）
Copy-Item -Path "$RelayDir\radata\*" -Destination $BackupPath -Recurse -ErrorAction SilentlyContinue

# 保留最近 7 天，刪除舊備份
Get-ChildItem $BackupDir -Directory |
    Sort-Object CreationTime -Descending |
    Select-Object -Skip 7 |
    Remove-Item -Recurse -Force

Write-Host "✅ radata 備份完成: $BackupPath"
```

**排程**：加入 `HEARTBEAT.md`，每日 00:10（在 relay 重啟 00:15 之前）。

---

## 4. 安全性加固方案

### 4.1 安全標頭（Helmet）

**目的**：防 XSS、clickjacking、MIME sniffing 等 Web 攻擊。

```bash
cd D:\Source\my-gun-relay
npm install helmet
```

```javascript
const helmet = require('helmet');

// 基本安全標頭（放在 CORS 之後、路由之前）
app.use(helmet({
    contentSecurityPolicy: false,  // Gun.js 需要 eval（SEA 用）
    crossOriginEmbedderPolicy: false,  // 允許跨域嵌入
}));
```

### 4.2 Timing-Safe Token 驗證

**目的**：防止計時攻擊逐字元破解 API key。

```javascript
const crypto = require('crypto');

function timingSafeEqual(a, b) {
    if (!a || !b) return false;
    const bufA = Buffer.from(a);
    const bufB = Buffer.from(b);
    if (bufA.length !== bufB.length) return false;
    return crypto.timingSafeEqual(bufA, bufB);
}

// 在 /api/task 中替換現有的字串比較
// 原：if (provided !== apiKey) { ... }
// 新：
if (!timingSafeEqual(provided, apiKey)) {
    return res.status(401).json({ error: 'Unauthorized' });
}
```

### 4.3 強制 API Key（移除可選機制）

**目的**：消除「忘記設定環境變數 = 無認證」的風險。

```javascript
// 啟動時檢查必要環境變數
if (!process.env.API_SECRET_KEY) {
    console.error('[relay] ❌ 錯誤：API_SECRET_KEY 環境變數未設定');
    console.error('[relay] 請在環境變數或 .env 檔案中設定 API_SECRET_KEY');
    process.exit(1);
}
```

### 4.4 靜態檔案安全

**目的**：防止伺服器原始碼被直接下載。

```javascript
// 取代 express.static(__dirname)
// 改為只暴露 public/ 子目錄
app.use(express.static(path.join(__dirname, 'public')));
```

將 `index.html` 移至 `public/` 子目錄，其他檔案（`index.js`、`package.json`）不再被暴露。

### 4.5 CORS 分級策略

**目的**：Gun peer 需要寬鬆 CORS，但 API 端點應限制來源。

```javascript
const cors = require('cors');

// Gun peer 路由：寬鬆 CORS（保持現行為）
app.use('/gun', cors({ origin: '*' }));

// API 路由：限制來源
const apiCorsOptions = {
    origin: (origin, callback) => {
        // 允許無 origin（server-to-server 呼叫如 make.com）
        if (!origin) return callback(null, true);
        // 允許本地開發
        const allowedOrigins = [
            'http://localhost:3001',
            'http://localhost:8765',
            'https://gun.pdoont.us.kg',
        ];
        if (allowedOrigins.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error('Not allowed by CORS'));
        }
    },
    methods: ['GET', 'POST'],
    allowedHeaders: ['Content-Type', 'Authorization'],
};

app.use('/api/', cors(apiCorsOptions));
```

### 4.6 WSS（TLS 加密 WebSocket）

**目的**：確保 WebSocket 傳輸加密，防止中間人嗅探。

#### 方案 A：Cloudflare Proxy（推薦，現行方案）

目前透過 Cloudflare 代理 `gun.pdoont.us.kg`，已自動提供 TLS。確認事項：

- ✅ Cloudflare SSL/TLS 設定為 **Full (strict)**
- ✅ WebSocket 已在 Cloudflare Dashboard 啟用
- ✅ 不直接暴露 8765 埠到公網

#### 方案 B：自建 TLS（若不走 Cloudflare）

```bash
# Let's Encrypt 證書取得
sudo certbot certonly --standalone -d gun.yourdomain.com
```

```javascript
const https = require('https');
const fs = require('fs');

const sslOptions = {
    key: fs.readFileSync('/etc/letsencrypt/live/gun.yourdomain.com/privkey.pem'),
    cert: fs.readFileSync('/etc/letsencrypt/live/gun.yourdomain.com/fullchain.pem'),
};

const server = https.createServer(sslOptions, app).listen(443);
```

### 4.7 依賴安全掃描自動化

**目的**：定期檢查 npm 依賴的已知漏洞。

```powershell
# check-npm-audit.ps1 — 加入每週排程
$RelayDir = "D:\Source\my-gun-relay"
$BotDir = "D:\Source\daily-digest-prompt\bot"

$results = @()
foreach ($dir in @($RelayDir, $BotDir)) {
    Push-Location $dir
    $audit = npm audit --json 2>$null | ConvertFrom-Json
    if ($audit.metadata.vulnerabilities.high -gt 0 -or $audit.metadata.vulnerabilities.critical -gt 0) {
        $results += "[⚠️ $($dir | Split-Path -Leaf)] high=$($audit.metadata.vulnerabilities.high) critical=$($audit.metadata.vulnerabilities.critical)"
    }
    Pop-Location
}

if ($results.Count -gt 0) {
    # 透過 ntfy 告警
    $body = @{
        topic = "wangsc2025"
        title = "npm 安全警報"
        message = $results -join "`n"
        priority = 4
    } | ConvertTo-Json
    $body | Out-File -Encoding utf8 "npm_alert.json"
    curl -s -H "Content-Type: application/json; charset=utf-8" -d "@npm_alert.json" "https://ntfy.sh" | Out-Null
    Remove-Item "npm_alert.json" -ErrorAction SilentlyContinue
}
```

### 4.8 防火牆與連線限制

**本地部署（Windows）**：

```powershell
# 僅允許本地與 Cloudflare 存取 8765
# Windows Firewall 規則（需管理員權限）
New-NetFirewallRule -DisplayName "Gun Relay - Local Only" `
    -Direction Inbound -Protocol TCP -LocalPort 8765 `
    -RemoteAddress LocalSubnet -Action Allow

# 封鎖所有其他來源
New-NetFirewallRule -DisplayName "Gun Relay - Block External" `
    -Direction Inbound -Protocol TCP -LocalPort 8765 `
    -Action Block
```

**Linux 生產環境（ufw）**：

```bash
sudo ufw allow from 127.0.0.1 to any port 8765
sudo ufw allow from 173.245.48.0/20 to any port 8765  # Cloudflare IP 範圍
sudo ufw deny 8765
```

### 4.9 請求體大小限制

```javascript
// 限制 JSON body 大小（防止大 payload 攻擊）
app.use(express.json({ limit: '100kb' }));
```

---

## 5. 效能最佳化方案

### 5.1 記憶體管理

```javascript
// 定期記錄記憶體使用（每 5 分鐘）
setInterval(() => {
    const mem = process.memoryUsage();
    const heapMB = Math.round(mem.heapUsed / 1024 / 1024);
    const rssMB = Math.round(mem.rss / 1024 / 1024);

    // 結構化日誌
    console.log(JSON.stringify({
        type: 'metrics',
        heap_mb: heapMB,
        rss_mb: rssMB,
        uptime_s: Math.floor(process.uptime()),
        timestamp: new Date().toISOString(),
    }));
}, 5 * 60_000);
```

### 5.2 Gun.js 調優參數

```javascript
const gun = Gun({
    web: server,
    peers: peers,
    radisk: true,
    localStorage: false,
    axe: false,           // 關閉 mesh optimizer（小規模部署不需要）
    multicast: false,     // 關閉 UDP multicast
    file: 'radata',       // 明確指定儲存路徑
    // 效能調優
    chunk: 2 * 1024 * 1024,  // RAD 分片大小 2MB
    until: 2 * 1000,         // 防洪等待時間 2s
});
```

### 5.3 結構化日誌

```javascript
// 簡易結構化日誌工具
function log(level, msg, data = {}) {
    console.log(JSON.stringify({
        level,
        msg,
        ...data,
        ts: new Date().toISOString(),
    }));
}

// 使用範例
log('info', 'relay started', { port, peers: peers.length });
log('warn', 'high memory', { heapMB: 250 });
log('error', 'task write failed', { msgId, error: ack.err });
```

---

## 6. 實施時間表

| 階段 | 時間 | 措施 | 優先級 | 預估工時 |
|------|------|------|--------|---------|
| **Phase 1** | Week 1 | S2 Helmet + S3 Timing-Safe + S6 強制 API Key + T1 全域例外 + T3 Graceful Shutdown + S9 靜態檔案 | 🔴 P0 | 2h |
| **Phase 2** | Week 1-2 | S1 Rate Limiting + 4.9 請求體限制 + T2 PM2 部署 | 🔴 P0 | 3h |
| **Phase 3** | Week 2 | 3.3 增強 Health Check + 3.5 備份策略 + T8 結構化日誌 | 🟡 P1 | 2h |
| **Phase 4** | Week 3 | S4 CORS 分級 + S5 WSS 驗證 + 4.7 npm audit 排程 | 🟡 P1 | 2h |
| **Phase 5** | Week 4 | 3.4 NGINX 反向代理（若上雲）+ S8 IP 黑名單 + 4.8 防火牆 | 🟢 P2 | 3h |
| **Phase 6** | 持續 | 5.1 記憶體監控 + 5.2 Gun 調優 + 版本統一 | 🟢 P2 | 1h |

**總預估工時**：~13 小時（分 6 階段 4 週完成）

---

## 7. 驗收標準

### 7.1 安全性驗收

| # | 驗收項目 | 驗證方法 | 通過條件 |
|---|---------|---------|---------|
| A1 | Helmet 安全標頭 | `curl -I http://localhost:8765/api/health` | 回應包含 X-Content-Type-Options、X-Frame-Options |
| A2 | Rate Limiting | 連續 35 次 `curl /api/health` | 第 31 次起回傳 429 |
| A3 | Timing-Safe Token | 程式碼審查 | 使用 `crypto.timingSafeEqual` |
| A4 | 強制 API Key | 移除 env 中的 API_SECRET_KEY 後啟動 | 伺服器拒絕啟動並輸出錯誤訊息 |
| A5 | 靜態檔案保護 | `curl http://localhost:8765/index.js` | 回傳 404 |
| A6 | npm audit | 執行 `npm audit` | 無 high/critical 漏洞 |
| A7 | 請求體限制 | POST 超過 100kb 的 body | 回傳 413 |

### 7.2 穩定性驗收

| # | 驗收項目 | 驗證方法 | 通過條件 |
|---|---------|---------|---------|
| B1 | 全域例外處理 | 觸發未捕獲例外 | 不直接 crash，log 記錄後由 PM2 重啟 |
| B2 | Graceful Shutdown | 送 SIGTERM | 正常關閉 HTTP server + 退出碼 0 |
| B3 | PM2 自動重啟 | `pm2 stop gun-relay && pm2 start gun-relay` | 3 秒內恢復服務 |
| B4 | 記憶體監控 | 運行 24 小時 | heap 無持續增長趨勢 |
| B5 | Health Check 增強 | `curl /api/health` | 回傳 memory、uptime、requestCount |
| B6 | radata 備份 | 執行 backup-radata.ps1 | 備份目錄存在且檔案完整 |

### 7.3 效能驗收

| # | 驗收項目 | 驗證方法 | 通過條件 |
|---|---------|---------|---------|
| C1 | Health Check 延遲 | 10 次 curl 計時 | 平均 < 50ms |
| C2 | Webhook 延遲 | POST /api/task 計時 | 平均 < 500ms（含加密） |
| C3 | 記憶體基線 | 啟動後穩態 | heap < 100MB |

---

## 8. 成本效益分析

| 措施 | 新增依賴 | 開發成本 | 效益 |
|------|---------|---------|------|
| Helmet | `helmet` (43KB) | 低（5 行） | 阻擋 6 類 Web 攻擊 |
| Rate Limiting | `express-rate-limit` (15KB) | 低（10 行） | 防 DDoS / 暴力攻擊 |
| PM2 | `pm2`（全域） | 中（配置檔） | 自動重啟 + 監控 |
| Timing-Safe | 內建 `crypto` | 極低（5 行） | 消除計時攻擊 |
| 結構化日誌 | 無 | 低（封裝函式） | 自動化問題診斷 |
| NGINX | 系統套件 | 中（配置） | TLS + 負載均衡 + 靜態快取 |
| 備份 | 無 | 低（PS 腳本） | 災難恢復 |

**總新增依賴大小**：< 60KB（helmet + express-rate-limit）
**營運成本變化**：無額外費用（PM2 免費、NGINX 開源）

---

## 9. 風險評估

| 風險 | 機率 | 影響 | 緩解策略 |
|------|------|------|---------|
| Gun.js 不相容 helmet 標頭 | 低 | 中 | `contentSecurityPolicy: false` 已處理 |
| PM2 在 Windows 的穩定性 | 中 | 低 | 替代方案：使用 Windows Service 封裝 |
| Rate Limiting 誤擋合法請求 | 低 | 中 | 初始設 30/min，觀察後調整 |
| NGINX 配置錯誤中斷服務 | 中 | 高 | 先在測試環境驗證，保留 bypass 直連 |
| radata 備份期間 I/O 競爭 | 低 | 低 | 備份排程避開高峰時段 |

---

## 10. 附錄

### 10.1 完整修改後的 index.js 骨架

```javascript
// ─── 全域例外處理 ──────────────────────────────────────────
process.on('unhandledRejection', (reason) => { /* ... */ });
process.on('uncaughtException', (err) => { /* ... */ });

// ─── 啟動檢查 ─────────────────────────────────────────────
if (!process.env.API_SECRET_KEY) { process.exit(1); }

// ─── Express 初始化 ───────────────────────────────────────
const app = express();
app.use(helmet({ contentSecurityPolicy: false, crossOriginEmbedderPolicy: false }));
app.use(express.json({ limit: '100kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// ─── CORS 分級 ───────────────────────────────────────────
app.use('/gun', cors({ origin: '*' }));
app.use('/api/', cors(apiCorsOptions));

// ─── Rate Limiting ───────────────────────────────────────
app.use('/api/', apiLimiter);

// ─── 路由 ────────────────────────────────────────────────
app.get('/api/health', healthHandler);
app.post('/api/task', taskHandler);  // 含 timingSafeEqual 驗證

// ─── 啟動 ────────────────────────────────────────────────
const server = app.listen(port, () => { /* ... */ });
const gun = Gun({ web: server, /* ... */ });

// ─── Graceful Shutdown ───────────────────────────────────
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

// ─── 自我監控 ────────────────────────────────────────────
setInterval(selfHealthCheck, 60_000);
setInterval(metricsLog, 5 * 60_000);
```

### 10.2 快速修復檢查清單（Phase 1）

- [ ] `npm install helmet express-rate-limit`
- [ ] 加入 `process.on('unhandledRejection', ...)` 和 `uncaughtException`
- [ ] 加入 `gracefulShutdown()`
- [ ] 替換字串比較為 `crypto.timingSafeEqual()`
- [ ] 加入 `if (!process.env.API_SECRET_KEY) process.exit(1)`
- [ ] `express.static(__dirname)` → `express.static(path.join(__dirname, 'public'))`
- [ ] 建立 `public/` 目錄，移入 `index.html`
- [ ] 加入 `app.use(helmet(...))`
- [ ] 加入 `app.use(express.json({ limit: '100kb' }))`
- [ ] 執行 `npm audit` 確認無高危漏洞

---

*本文件為 Gun Relay Server 穩定性與安全性優化計畫 v1.0，歸屬 gunjs-decentralized-db 系列 optimization 階段。*
