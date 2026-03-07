# Gun Server 穩定性與安全性優化計畫

- **日期**：2026-03-07
- **作者**：系統架構 Agent（Claude Code）
- **版本**：v1.0
- **狀態**：定稿
- **系列**：gunjs-decentralized-db（階段：optimization）

---

## 1. 現況分析

### 1.1 環境概覽

| 項目 | 現況 |
|------|------|
| **Gun.js 版本** | 0.2020.1241（gun npm package） |
| **Node.js 環境** | 裸機部署於 Render.com（Free Tier） |
| **部署方式** | 獨立 Node.js 應用（`node index.js`），非 Docker |
| **監聽端口** | 8765（HTTP）或環境變數 `PORT` |
| **生產 URL** | `wss://gun.pdoont.us.kg/gun`（WSS 加密） |
| **持久化** | Gun RAD 存儲引擎（`radisk: true`），磁碟路徑 `radata/` |
| **心跳保活** | Cloudflare Workers Cron（每 10 分鐘 GET `/api/health`） |
| **前端** | 聊天室 UI（`index.html`，1479 行），含 SEA ECDH 握手 |
| **Bot 應用** | `bot.js`（663 行），FSM 任務處理 + Gun P2P 同步 |

### 1.2 網路拓撲

```
[Frontend Browser] ──WSS + SEA ECDH──> [Gun Relay :8765 (Render.com)]
                                              │
                                              │ Gun P2P Sync
                                              ▼
                                      [Bot Server (本地)]
                                              │
                                              ▼
                                      [radata/ 持久化]
```

### 1.3 目前觀測到的問題

**P0 嚴重（影響正確性）：**
- **B1**：ACK 邏輯錯誤 — `!ack.err` 將 null/undefined 誤判為失敗
- **B2**：重連後訊息重複 — `.on()` 未配對 `.off()` 清理
- **B3**：`sentMessageIds` 未隨重連清理，導致他人訊息誤判為自己發送
- **B4**：radisk 未啟用（bot.js）— 已修正（L172）

**P1 穩定性：**
- ACK 超時僅 5 秒，移動網路常 > 3 秒
- API 呼叫無指數退避機制
- 解密失敗 catch 區塊完全靜默
- Bot epub 預取 10 秒超時，無重試
- `claim_timeout` 硬編碼 10 分鐘

**P1 安全性：**
- Bot 私鑰（`keypair.json`）明文磁碟存儲
- CORS 設為 `origin: '*'`（完全開放）

---

## 2. 風險評估

| # | 風險因素 | 等級 | 影響 | 可能性 | 說明 |
|---|---------|------|------|--------|------|
| R1 | Render.com Free Tier 冬眠 | **高** | 服務中斷 5-30 秒 | 高 | 15 分鐘無流量自動冬眠，冷啟動需 5-30 秒 |
| R2 | 私鑰明文磁碟存儲 | **高** | 身份冒充、資料竊取 | 中 | `keypair.json` 含 ECDH epriv，任何磁碟存取權即可竊取 |
| R3 | CORS 完全開放 | **高** | CSRF/跨站攻擊 | 高 | `origin: '*'` 允許任何網域發送請求 |
| R4 | ACK 邏輯錯誤（B1-B3） | **高** | 訊息遺失/重複 | 高 | 用戶看到重複訊息或遺失確認 |
| R5 | 無記憶體/CPU 資源限制 | **中** | OOM 崩潰 | 中 | Node.js 預設堆積上限 ~1.5 GB，大量同步可能溢出 |
| R6 | RAD 存儲無上限 | **中** | 磁碟空間耗盡 | 中 | radata/ 持續增長，Render Free Tier 磁碟有限 |
| R7 | Gun Multicast 無法關閉 | **低** | 內網探測暴露 | 低 | 233.255.255.255:8765 廣播，本地網路可發現節點 |
| R8 | npm 依賴漏洞 | **中** | 供應鏈攻擊 | 中 | 未定期執行 `npm audit`，gun 0.2020.1241 較舊 |
| R9 | 無速率限制（Relay 層） | **中** | DoS 攻擊 | 中 | Relay `/api/health` 無速率限制（Bot 層已有 60 req/min） |
| R10 | 無日誌集中化 | **中** | 事故調查困難 | 高 | console.log 輸出未持久化，Render 日誌僅保留 7 天 |

---

## 3. 優化措施

### 3.1 穩定性優化

#### S1. 升級心跳保活機制（優先級：P0）

**現況**：Cloudflare Worker 每 10 分鐘 ping `/api/health`，但 Render Free Tier 15 分鐘冬眠。
**措施**：
- 將 Cron 頻率從 `*/10` 調整為 `*/5`（每 5 分鐘），確保不觸發冬眠
- 心跳回應加入 `lastActivity` 時間戳，便於監控實際活躍度
- 新增 `/api/health/deep` 端點，檢查 Gun graph 讀寫能力（非僅 HTTP 回應）

```javascript
// index.js — 深度健康檢查
app.get('/api/health/deep', async (req, res) => {
  const start = Date.now();
  try {
    const testKey = `_health_${Date.now()}`;
    await new Promise((resolve, reject) => {
      gun.get(testKey).put({ ts: Date.now() }, ack => {
        if (ack.err) reject(new Error(ack.err));
        else resolve();
      });
      setTimeout(() => reject(new Error('timeout')), 5000);
    });
    res.json({
      status: 'ok',
      latency_ms: Date.now() - start,
      gun_writable: true
    });
  } catch (e) {
    res.status(503).json({ status: 'degraded', error: e.message });
  }
});
```

#### S2. 修復 ACK 邏輯與重連去重（優先級：P0）

**措施**：
- **B1 修正**：ACK 判定改為 `if (ack.err)` 正向檢查錯誤，而非 `!ack.err` 負向判定
- **B2 修正**：`.on()` 監聽加入 `eventId` 追蹤，重連前先 `.off()` 清理舊監聽器
- **B3 修正**：重連時清空 `sentMessageIds` Set，並加入 TTL 自動過期（30 分鐘）

```javascript
// ACK 修正範例
gun.get('chat').set(msg, function(ack) {
  if (ack.err) {
    console.error('[ACK] 寫入失敗:', ack.err);
    retryWithBackoff(msg);
  } else {
    console.log('[ACK] 寫入成功');
  }
});
```

#### S3. 指數退避重試機制（優先級：P1）

**措施**：
- 所有外部 API 呼叫加入指數退避：初始 2 秒 → 4 秒 → 8 秒（最多 3 次）
- fetch 加入 `AbortSignal.timeout(8000)` 避免無限等待
- Bot epub 預取改為 3 次重試 + 12 秒超時

```javascript
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const resp = await fetch(url, {
        ...options,
        signal: AbortSignal.timeout(8000)
      });
      if (resp.ok) return resp;
    } catch (e) {
      if (i === maxRetries - 1) throw e;
      await new Promise(r => setTimeout(r, 2000 * Math.pow(2, i)));
    }
  }
}
```

#### S4. 資源限制與自動重啟（優先級：P1）

**措施**：
- 啟動指令加入 `--max-old-space-size=512`（限制 V8 堆積 512 MB）
- 使用 PM2 或 systemd 管理進程，設定崩潰自動重啟（最多 5 次/10 分鐘）
- 新增 `/api/metrics` 端點回報記憶體/CPU 使用量

```json
// ecosystem.config.js (PM2)
{
  "apps": [{
    "name": "gun-relay",
    "script": "index.js",
    "node_args": "--max-old-space-size=512",
    "max_restarts": 5,
    "restart_delay": 3000,
    "env": { "PORT": 8765 }
  }]
}
```

#### S5. RAD 存儲清理策略（優先級：P2）

**措施**：
- 定期清理超過 90 天的聊天訊息（Cron Job 或 Cloudflare Worker）
- 監控 `radata/` 目錄大小，超過 100 MB 時告警
- 考慮遷移至 Render Persistent Disk（付費）或外部 S3 備份

---

### 3.2 安全性優化

#### A1. 私鑰加密存儲（優先級：P0）

**現況**：`keypair.json` 含 ECDH 私鑰明文。
**措施**：
- 新增 `BOT_KEY_PASSPHRASE` 環境變數
- 啟動時用 AES-256-GCM 解密私鑰，關閉時不寫回明文
- 首次遷移腳本：讀取現有明文 → 加密 → 覆寫

```javascript
const crypto = require('crypto');

function encryptKeypair(keypair, passphrase) {
  const key = crypto.scryptSync(passphrase, 'gun-relay-salt', 32);
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const encrypted = Buffer.concat([
    cipher.update(JSON.stringify(keypair), 'utf8'),
    cipher.final()
  ]);
  return {
    iv: iv.toString('hex'),
    tag: cipher.getAuthTag().toString('hex'),
    data: encrypted.toString('hex')
  };
}
```

#### A2. CORS 白名單收緊（優先級：P0）

**現況**：`origin: '*'`（完全開放）。
**措施**：
- 收緊為明確白名單：生產域名 + localhost 開發

```javascript
const allowedOrigins = [
  'https://gun.pdoont.us.kg',
  'http://localhost:8765',
  'http://127.0.0.1:8765'
];

app.use(cors({
  origin: (origin, cb) => {
    if (!origin || allowedOrigins.includes(origin)) cb(null, true);
    else cb(new Error('CORS blocked'));
  },
  credentials: true
}));
```

#### A3. Relay 層速率限制（優先級：P1）

**措施**：
- 對 Relay `/api/*` 端點加入速率限制：100 req/min/IP
- 對 WebSocket 連線數加入上限：50 concurrent connections
- 異常流量自動封鎖 IP（5 分鐘）

```javascript
const rateLimit = require('express-rate-limit');

const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 100,
  message: { error: 'Too many requests' }
});
app.use('/api/', apiLimiter);
```

#### A4. 安全掃描自動化（優先級：P1）

**措施**：
- 每週執行 `npm audit --audit-level=high`
- 整合 Snyk 或 GitHub Dependabot 自動掃描
- Gun 0.2020.1241 版本評估升級可行性（確認不破壞 P2P 同步）

```bash
# 定期安全掃描（加入 CI/CD 或本地 Cron）
npm audit --audit-level=high --json > audit-report.json
```

#### A5. WebSocket 連線認證（優先級：P1）

**措施**：
- WebSocket 握手階段驗證 JWT Token 或 API Key
- 未認證連線限制為唯讀（僅接收廣播，不可寫入）
- 連線逾時 30 分鐘無活動自動斷開

#### A6. 日誌審計與異常偵測（優先級：P2）

**措施**：
- 結構化日誌輸出（JSON 格式），包含 timestamp、event、source_ip
- 記錄所有認證失敗、異常大量 put 操作、CORS 拒絕事件
- 日誌推送至外部服務（如 Logtail、Datadog Free Tier）或本地 JSONL 輪轉

---

## 4. 實施步驟與時間表

| 階段 | 措施 | 優先級 | 預估工時 | 目標完成日 | 負責人 |
|------|------|--------|---------|-----------|--------|
| **Phase 1：緊急修復** | | | | | |
| 1.1 | S2: ACK 邏輯修正（B1-B3） | P0 | 2h | 2026-03-08 | 開發者 |
| 1.2 | A2: CORS 白名單收緊 | P0 | 0.5h | 2026-03-08 | 開發者 |
| 1.3 | A1: 私鑰加密存儲 | P0 | 1.5h | 2026-03-08 | 開發者 |
| **Phase 2：穩定性強化** | | | | | |
| 2.1 | S1: 心跳頻率 + 深度健康檢查 | P0 | 1h | 2026-03-09 | 開發者 |
| 2.2 | S3: 指數退避重試 | P1 | 1h | 2026-03-09 | 開發者 |
| 2.3 | S4: PM2 + 資源限制 | P1 | 1.5h | 2026-03-10 | 開發者 |
| **Phase 3：安全加固** | | | | | |
| 3.1 | A3: Relay 速率限制 | P1 | 1h | 2026-03-10 | 開發者 |
| 3.2 | A4: npm audit 自動化 | P1 | 0.5h | 2026-03-10 | 開發者 |
| 3.3 | A5: WebSocket 連線認證 | P1 | 2h | 2026-03-12 | 開發者 |
| **Phase 4：可觀測性** | | | | | |
| 4.1 | A6: 結構化日誌 + 審計 | P2 | 2h | 2026-03-14 | 開發者 |
| 4.2 | S5: RAD 存儲清理策略 | P2 | 1h | 2026-03-14 | 開發者 |

**總預估工時**：~14 小時（分 4 個 Phase，跨 7 天）

---

## 5. 資源需求

### 5.1 硬體

| 資源 | 現況 | 建議 | 備註 |
|------|------|------|------|
| CPU | Render Free（共享） | Render Starter（1 vCPU） | 避免冷啟動延遲 |
| 記憶體 | 512 MB（Free Tier） | 1 GB | V8 heap 512 MB + OS overhead |
| 磁碟 | 臨時磁碟（重啟清除） | Persistent Disk 1 GB | radata/ 持久化 |

### 5.2 軟體

| 軟體 | 版本 | 用途 |
|------|------|------|
| Node.js | >= 18 LTS | 運行環境（建議 20 LTS） |
| Gun.js | 0.2020.1241 → 評估最新版 | P2P 同步引擎 |
| PM2 | >= 5.x | 進程管理與自動重啟 |
| express-rate-limit | >= 7.x | API 速率限制 |
| snyk / npm audit | 最新 | 依賴安全掃描 |

### 5.3 人力

| 角色 | 需求 | 說明 |
|------|------|------|
| 後端開發者 | 1 人 | 實施所有優化措施 |
| 測試 | 自測 | 測試環境優先驗證 |

---

## 6. 預期成效

### 6.1 穩定性指標

| 指標 | 現況（估計） | 目標 | 改善幅度 |
|------|-------------|------|---------|
| **MTBF**（平均無故障時間） | ~4 小時（因冬眠） | >= 72 小時 | 18x |
| **冷啟動時間** | 5-30 秒 | < 5 秒（心跳保活） | 6x |
| **訊息送達率** | ~85%（ACK bug） | >= 99% | +14% |
| **重連訊息重複率** | ~15% | < 1% | -14% |
| **平均回應延遲** | 200-500 ms | < 150 ms | 2-3x |

### 6.2 安全性指標

| 指標 | 現況 | 目標 | 改善幅度 |
|------|------|------|---------|
| **已知漏洞數** | 未掃描 | 0 高/嚴重 | 100% |
| **加密覆蓋率** | 70%（WSS + SEA） | 95%（+ 私鑰加密 + 日誌） | +25% |
| **CORS 開放度** | 完全開放 | 白名單 3 域名 | 限縮 |
| **未認證 API 端點** | 2（/health, relay） | 1（僅 /health） | -50% |
| **速率限制覆蓋** | 僅 Bot 層 | Relay + Bot 雙層 | +100% |

---

## 7. 測試與回滾計畫

### 7.1 測試環境

- 在本地 `localhost:8765` 完整模擬生產拓撲
- Bot + Relay + Frontend 三方測試握手流程
- 壓力測試：使用 `artillery` 或 `k6` 模擬 50 concurrent WebSocket 連線

### 7.2 回滾策略

| 階段 | 回滾方式 |
|------|---------|
| Phase 1（ACK/CORS/私鑰） | Git revert 至修改前 commit |
| Phase 2（心跳/重試/PM2） | Cloudflare Worker 恢復 */10 頻率 + 移除 PM2 |
| Phase 3（速率限制/認證） | 移除 express-rate-limit 中介軟體 |
| Phase 4（日誌/清理） | 停用日誌推送，保留本地 console.log |

### 7.3 備份

- 實施前備份 `radata/` 目錄
- 備份 `keypair.json`（加密後安全存放）
- 備份 `.env` 環境變數檔

---

## 8. 法規合規

- 聊天訊息經 SEA ECDH 端對端加密，僅通訊雙方可解密
- 無個人資料（PII）收集，不涉及 GDPR 範疇
- 私鑰加密存儲符合最小權限原則
- 日誌中不記錄訊息明文內容，僅記錄 metadata（timestamp、event type、source IP 遮罩）

---

## 參考文件

1. `D:\Source\daily-digest-prompt\docs\gun-js-optimization-report-20260228.md` — 27 項修補方案詳細規劃
2. `D:\Source\my-gun-relay\index.js` — Relay 伺服器主體（204 行）
3. `D:\Source\daily-digest-prompt\bot\bot.js` — Bot 應用伺服器（663 行）
4. Gun.js 官方文件：https://gun.eco/docs/
5. OWASP Node.js 安全最佳實踐
