# Gun.js 加密聊天室任務指派系統：完整除錯研究報告

**日期**：2026-03-01
**專案**：daily-digest-prompt / wsc-bot
**狀態**：✅ 全工作流程驗證成功

---

## 一、系統架構概述

本系統實現一個基於 Gun.js 的去中心化加密聊天室，使用者可透過 UI 指派任務，Bot 接收並儲存，Worker 認領執行（`claude -p`），結果加密廣播回聊天室。

### 核心元件

```
index.html (chatroom UI)
    ↓ SEA.encrypt → Gun P2P Relay
         ↓ bot.js (接收 + 儲存)
              ↓ /api/records (HTTP REST)
                   ↓ process_messages.ps1 (Worker)
                        ↓ claude -p (AI 執行)
                        ↓ /api/records/:uid/processed
                   ↓ bot.js sendSystemReply
         ↓ Gun P2P Relay (廣播加密結果)
    ↑ SEA.decrypt → index.html (顯示結果)
```

### 技術棧

| 元件 | 技術 |
|------|------|
| P2P 資料庫 | Gun.js v0.2020.x |
| 非對稱加密 | Gun SEA (ECDH + ECDSA) |
| 後端 | Node.js + Express |
| Worker | PowerShell 7 + claude -p |
| Relay | Render.com / localhost:8765 |
| Chatroom ID | `render_isolated_chat_room` |

---

## 二、SEA 加密協定詳解

### 金鑰類型區分（關鍵易混淆點）

Gun SEA 使用兩種獨立金鑰對，初學者常混淆：

| 金鑰 | 演算法 | 用途 | 屬性名 |
|------|--------|------|--------|
| ECDH 金鑰對 | Curve25519 | 計算共享密鑰 | `epub` / `epriv` |
| ECDSA 金鑰對 | P-256 | 簽章驗證 | `pub` / `priv` |

**正確驗證方式**：
```javascript
// ❌ 錯誤：用 epub（ECDH）驗證 ECDSA 簽章
SEA.verify(hw.sig, hw.epub)  // 永遠失敗，回傳 undefined

// ✅ 正確：用 pub（ECDSA）驗證簽章
SEA.verify(hw.sig, hw.pub)   // 成功，回傳原始資料
```

### ECDH 共享密鑰計算

```javascript
// 對稱性：兩端計算結果相同
// 用戶端：
sharedSecret = await SEA.secret(botEpub, myPair)

// Bot 端：
sharedSecret = await SEA.secret(clientEpub, botPair)
// SEA.secret(A.epub, B.pair) === SEA.secret(B.epub, A.pair)
```

### 訊息加密格式（關鍵：與 index.html 完全一致）

```javascript
// ✅ 正確格式（index.html 使用，bot.js 預期）
const payload = JSON.stringify({ text: userMessage, ts: Date.now() });
const encryptedData = await SEA.encrypt(payload, sharedSecret);
const msgId = 'msg_' + randomBytes(8).toString('hex').slice(0, 12);
gun.get(chatRoomName).get(msgId).put(encryptedData); // 直接放，不包裝

// ❌ 錯誤格式（會導致 bot 無法解密）
gun.get(chatRoomName).get(String(Date.now())).put({ d: encrypted, ts: Date.now() });
```

**bot.js 解密流程**：
```javascript
gun.get(chatRoomName).map().on(async (data, id) => {
    // data = encryptedData（加密字串，非包裝物件）
    const raw = await SEA.decrypt(data, ss);
    // raw = { text: '...', ts: 123 }（JSON 自動解析）
    const text = typeof raw === 'string' ? raw : raw?.text;
});
```

---

## 三、握手協定設計

### Bot 發布端（bot.js init）

```javascript
// 模組層級變數（供 relay 重連補發使用）
let myPair = null;
let epubSig = null;

// 握手路徑發布（含 ECDSA pub 供客端驗證）
epubSig = await SEA.sign(myPair.epub, myPair);
gun.get('wsc-bot/handshake').put({ epub: myPair.epub, sig: epubSig, pub: myPair.pub });
gun.get('wsc-bot/handshake').get('bot-epub').put(myPair.epub); // 相容路徑

// Relay 重連自動補發（解決 Render.com 重啟後資料消失）
gun.on('hi', () => {
    if (myPair && epubSig) {
        gun.get('wsc-bot/handshake').put({ epub: myPair.epub, sig: epubSig, pub: myPair.pub });
    }
});
```

### 客端取得端（index.html / 測試腳本）

```javascript
// 優先主路徑（含 ECDSA 驗證），失敗則 fallback
gun.get('wsc-bot/handshake').once(async (hw) => {
    if (!hw?.epub) return;            // null 或未就緒，等 fallback
    const verified = await SEA.verify(hw.sig, hw.pub);
    if (verified !== hw.epub) return; // 驗證失敗（中間人攻擊？）
    resolve(hw.epub);
});

// Fallback 2s: bot-epub 相容路徑
setTimeout(() => {
    gun.get('wsc-bot/handshake').get('bot-epub').once(epub => {
        if (epub) resolve(epub);
    });
}, 2000);
```

### 多用戶握手（client epub 發布）

```javascript
// 兩條路徑都發，確保 bot 收到
gun.get('wsc-bot/handshake').get('client-epub').put(myPair.epub);  // 向下相容
gun.get('wsc-bot/handshake').get('clients').get(myPair.pub).put(myPair.epub); // 多用戶
```

**握手等待時間**：發布 epub 後需等待 **8 秒**，讓 Bot 的 Gun 監聽器收到並呼叫 `registerClient(epub)` 建立 sharedSecret。

---

## 四、Debug 過程：發現的 Bug 與根因

### Bug 1：SEA.verify 使用錯誤的金鑰（高嚴重性）

**症狀**：`autoFetchBotEpub()` 永遠失敗，顯示「⚠ 逾時」

**根因**：
```javascript
// ❌ 舊版：用 epub（ECDH）驗證 ECDSA 簽章 → 永遠回傳 undefined
const verified = await SEA.verify(hw.sig, hw.epub);
if (verified !== hw.epub) { resolve(null); return; }

// ✅ 修正：用 pub（ECDSA）驗證
const verified = await SEA.verify(hw.sig, hw.pub);
```

**影響檔案**：`D:\Source\my-gun-relay\index.html`

---

### Bug 2：Relay 重啟後 Bot epub 消失（中嚴重性）

**症狀**：Render.com relay 每 ~15 分鐘重啟後，新連線的客端無法取得 Bot epub

**根因**：bot.js 只在 `init()` 時發布一次 epub，relay 重啟後 radisk 資料消失，Bot 的 Gun 實例再次連上後未補發

**修復**：
```javascript
let epubSig = null; // 模組層級，供重連使用

// 在 init() 中：
epubSig = await SEA.sign(myPair.epub, myPair);

// gun.on('hi') 補發邏輯：
gun.on('hi', () => {
    if (myPair && epubSig) {
        gun.get('wsc-bot/handshake').put({ epub: myPair.epub, sig: epubSig, pub: myPair.pub });
        gun.get('wsc-bot/handshake').get('bot-epub').put(myPair.epub);
    }
});
```

---

### Bug 3：Bot 自身回覆被誤存為新任務（中嚴重性）

**症狀**：Bot 廣播的 `[系統回覆]` 被再次解密並存為待執行任務

**根因**：Bot 加密 `JSON.stringify({text, ts})` 後，`SEA.decrypt` 回傳 **物件**（自動解析 JSON），`String({text, ts})` = `"[object Object]"` 不含 `[系統回覆]` → 過濾失效

**修復**：
```javascript
let text;
if (typeof raw === 'string') {
    text = raw;
} else if (raw && typeof raw === 'object' && raw.text) {
    text = raw.text; // bot 回覆格式：{text, ts}
} else {
    text = raw != null ? String(raw) : '';
}
if (!text || text.startsWith('[系統回覆]')) return; // 正確過濾
```

---

### Bug 4：settings.json Hook 路徑損壞（高嚴重性）

**症狀**：所有 PreToolUse Hook（Bash/Write/Edit/Read）全部失敗

**根因**：JSON 中的 Windows 路徑使用反斜線，bash 將其解析為逃逸字元：
- `"python D:\\Source\\..."` → bash 解析 → `D:Sourcedaily-digest-prompthooks...`（路徑損壞）

**修復**：所有 hook command 改用正斜線：
```json
{ "command": "python D:/Source/daily-digest-prompt/hooks/pre_bash_guard.py" }
```

---

### Bug 5：Worker CLAUDECODE 巢狀 Session 阻擋（高嚴重性）

**症狀**：Task Scheduler 每次執行 Worker，`claude -p` 在 <1 秒內返回，結果為錯誤訊息

**根因**：
- Claude Code 將 `CLAUDECODE` 設為用戶層級環境變數
- Windows Task Scheduler 在同一用戶 session 執行，繼承此環境變數
- `claude -p` 偵測到 `CLAUDECODE` 後拒絕啟動（防止巢狀 session 崩潰）

**症狀確認**：
```
Error: Claude Code cannot be launched inside another Claude Code session.
Nested sessions share runtime resources and will crash all active sessions.
To bypass this check, unset the CLAUDECODE environment variable.
```

**修復**（process_messages.ps1）：
```powershell
# 清除 CLAUDECODE 環境變數（官方建議的合法繞過方式）
$savedClaudeCode = $env:CLAUDECODE
Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue
try {
    $output = & claude -p $effectiveContent --allowedTools "Read,Bash,Write" 2>&1
} finally {
    if ($null -ne $savedClaudeCode) { $env:CLAUDECODE = $savedClaudeCode }
}
```

**為何 wsc-bot01 不受影響**：wsc-bot01 使用 `npx @openai/codex exec`（OpenAI Codex CLI），無 CLAUDECODE 巢狀 session 限制。

---

### Bug 6：測試腳本訊息格式錯誤（中嚴重性）

**根因**：Node.js 測試腳本使用與 index.html 不同的訊息格式

| 格式項目 | 錯誤 | 正確 |
|---------|------|------|
| 加密內容 | 純文字字串 | `JSON.stringify({ text, ts })` |
| Gun 放置 | `put({ d: encrypted, ts })` | `put(encryptedData)` 直接放 |
| msgId | `String(Date.now())` | `'msg_' + randomHex(12)` |

---

## 五、完整工作流程驗證結果

```
10:44:02 → 用戶發送加密任務 msg_1f2a01c2e34b
10:44:03 → Bot 確認儲存：[系統回覆] 已將任務存為檔案 msg_1f2a01c2e34b.md (研究型: true)
10:46:10 → Task Scheduler Worker 啟動，發現 1 個待處理任務
10:46:10 → Worker 認領任務 msg_1f2a01c2e34b（generation: 0）
10:46:13 → 任務強化完成（33 字 → 1583 字）
10:46:13 → claude -p 開始執行（已清除 CLAUDECODE）
10:46:44 → 執行完畢（耗時 31 秒）
10:46:44 → /api/records/msg_1f2a01c2e34b/processed ← Worker 回報結果
10:46:44 → Bot sendSystemReply → 加密廣播結果至聊天室

任務內容：「請用繁體中文分析台灣 AI 產業三大發展機會」
執行結果：完整的三大發展機會分析（AI 晶片製造、精準健康、繁中 LLM）
```

**端對端成功耗時**：約 2.5-3 分鐘（含 Task Scheduler 等待 ~2 分鐘 + 執行 31 秒）

---

## 六、Gun.js 重要行為特性

### `.once()` 的 null 行為

`.once()` 在沒有快取資料時 **立即** 以 `null` 回呼，不等待 relay 回應。解法：
- 不在 `null` 時 resolve，改用多次 retry + fallback
- 等待 fallback path（bot-epub）at 3s/7s

### `.map().on()` 的歷史資料

`.map().on()` 附加後，Gun 會對**現有所有資料**觸發回呼，同時持續監聽新資料。這意味著 bot 重啟後附加監聽器，會重新收到所有歷史訊息（需用 `processedMessages` 去重）。

### Render.com Free Tier 限制

- 每 ~15 分鐘因閒置重啟一次
- 重啟後 `radisk` 資料消失（epub 等握手資料需補發）
- 解法：`gun.on('hi', () => republish epub)`

---

## 七、測試工具（bot 目錄）

| 工具 | 用途 | 耗時 |
|------|------|------|
| `test_full_workflow.mjs` | 任務指派 + Bot 確認（無等 Worker） | ~50s |
| `test_full_with_result.mjs` | 含 Worker 執行結果等待 | ~3-8 分鐘 |
| `test_e2e_full.mjs` | 完整端對端（10 分鐘等待） | ~10 分鐘 |

**執行方式**（需在 Claude Code 外部，避免 CLAUDECODE 衝突）：
```powershell
cd D:\Source\daily-digest-prompt\bot
node test_full_with_result.mjs
```

---

## 八、架構建議

1. **使用本地 relay 開發**：`http://localhost:8765/gun` 比 Render.com 穩定，避免重啟問題
2. **epub 握手等待**：客端發布 epub 後需等待至少 8 秒，確保 bot 建立 sharedSecret
3. **CLAUDECODE 管理**：所有 Task Scheduler 任務執行 `claude -p` 前必須清除此環境變數
4. **訊息格式一致性**：嚴格遵守 `JSON.stringify({text, ts})` + 直接 put（勿包裝）
5. **多路徑握手**：同時發布 `client-epub`（向下相容）和 `clients/<pub>` （多用戶）

---

## 九、關鍵參考資料

- **SEA 文件**：https://gun.eco/docs/SEA
- **ECDH vs ECDSA**：epub/epriv 用於 ECDH，pub/priv 用於 ECDSA 簽章
- **Claude Code 環境變數**：`CLAUDECODE` 防止巢狀 session，可用 `Remove-Item Env:\CLAUDECODE` 暫時清除
- **Gun.js .once() 行為**：無快取時立即 null 回呼，需多次重試
