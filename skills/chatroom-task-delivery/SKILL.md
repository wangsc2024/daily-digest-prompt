---
name: chatroom-task-delivery
version: "1.0.0"
description: |
  Gun.js chatroom 任務投遞診斷與修復流程。
  Use when: 診斷 /api/task 已回 ok 但 bot 未入列、records.json 無任務、worker 持續輪詢卻沒有 pending、relay 與 bot 握手或 receipt 異常等問題。
allowed-tools: Read, Grep, Bash
cache-ttl: "N/A"
triggers:
  - "chatroom delivery"
  - "task delivery"
  - "mk_"
  - "/api/task"
  - "未入列"
  - "未執行"
  - "假成功"
  - "receipt timeout"
  - "bot receipt"
  - "Gun relay 任務"
---

# Chatroom Task Delivery

用於診斷 `my-gun-relay -> Gun graph -> bot.js -> records.json -> worker` 的投遞鏈。

## 核心原則

不要把 `/api/task` 的 `ok:true` 當成任務已入列。
必須分開驗證四段：

1. relay 是否成功寫入 Gun
2. bot 是否成功 receipt 並寫入 `records.json`
3. worker 是否看見 `pending`
4. 任務是否進入 `claimed/processing/completed`

## 必查檔案

- `D:/Source/my-gun-relay/index.js`
- `D:/Source/daily-digest-prompt/bot/bot.js`
- `D:/Source/daily-digest-prompt/bot/lib/routes.js`
- `D:/Source/daily-digest-prompt/bot/data/records.json`
- `D:/Source/daily-digest-prompt/bot/logs/task_log_YYYY-MM-DD.log`

## 標準檢查流程（四段式診斷）

### 步驟 1：確認 msgId 是否真的入列

優先查 records.json：

```powershell
# 替換 mk_123 為實際 msgId
rg -n "mk_123|msg_123" D:\Source\daily-digest-prompt\bot\data\records.json
```

**預期輸出**（正常情況）：
```
42:  "msgId": "mk_123",
43:  "status": "pending",
```

**若查無結果**：
- **診斷**：問題在 relay 到 bot/store 之間
- **下一步**：先不要看 worker，直接跳至步驟 3 檢查 relay

### 步驟 2：確認 worker 是否正常輪詢

查看最近 200 行 task_log：

```powershell
# 替換日期為今日
Get-Content D:\Source\daily-digest-prompt\bot\logs\task_log_2026-03-13.log -Tail 200
```

**預期輸出**（worker 正常但無任務）：
```
[2026-03-13 10:00:00] 目前沒有新任務需要處理
[2026-03-13 10:05:00] 目前沒有新任務需要處理
```

**診斷**：
- 若反覆出現「目前沒有新任務需要處理」→ worker 正常，pending 池沒有收到任務
- 若出現 claim/processing → worker 正常且有任務執行

### 步驟 3：確認 relay 成功語意是否過早

讀 relay 的 `/api/task` 端點實作：

```powershell
# 用 Read 工具讀取 my-gun-relay/index.js
# 搜尋 /api/task 路由實作
```

**檢查點**：
- 若只驗證 Gun `put` ack 就回 `ok:true`，屬於**假成功風險**
- **正確做法**：應等待 bot receipt 或明確回 `receipt_timeout`

### 步驟 4：檢查 bot 去重是否吞掉重送

讀 bot.js 的 `startMessageLoop()` 實作：

```powershell
# 用 Read 工具讀取 bot/bot.js
# 搜尋 startMessageLoop 函數
```

**檢查點**：
- 若在 `raw === null` 或解密失敗時就寫入 `processedMessages`
- **風險**：同 id 重送會被永久跳過
- **正確做法**：僅在成功解密且入列後才標記為已處理

## 修復準則

- relay 成功回應必須代表「bot 已入列」，不是「Gun 已寫入」
- 若 bot 未在 timeout 內 receipt，API 必須回失敗或 timeout，不可回 `ok:true`
- bot 不可對暫時無法解密的訊息做永久去重
- 重送應沿用同一 `msgId`，讓查詢與補償一致

## 診斷報告標準格式

完成四段式檢查後，輸出以下格式的診斷報告：

```markdown
## Chatroom Task Delivery 診斷報告

**msgId**: `mk_xxx`（或測試 ID）

### 鏈路檢查結果
| 階段 | 狀態 | 證據 |
|------|------|------|
| relay 寫入 Gun | ✅/❌ | `/api/task` 回應：`ok:true` |
| bot receipt 入列 | ✅/❌ | `records.json` 是否含 msgId |
| worker 輪詢 pending | ✅/❌ | `task_log` 是否出現任務 |
| 任務執行完成 | ✅/❌ | status: pending/claimed/completed |

### 根因分析
- 若 relay ❌：檢查 Gun relay 日誌，確認 Gun.put() 是否成功
- 若 bot receipt ❌：檢查 bot.js 解密邏輯或去重邏輯
- 若 worker pending ❌：檢查 worker 輪詢間隔或 records.json 格式
- 若執行 ❌：檢查 worker 執行日誌或 claim 機制

### 修復建議
（依根因提供具體修復步驟）
```

## 驗證標準

同一筆測試任務必須依序看到：

1. `/api/task` 回 `delivery_status=queued`（或改良的成功語意）
2. `records.json` 出現對應 `msgId`
3. `task_log` 出現 claim / processing / completed 或至少 claim

若第 1 步仍回 `ok:true` 但第 2 步缺失，視為**未修復**。

## 降級機制

若任一階段檢查失敗（檔案不存在、服務未啟動等）：
1. **跳過該階段檢查**，在診斷報告中標註「無法驗證」
2. **繼續剩餘檢查**，避免整個診斷流程中斷
3. **最終建議**：優先修復可檢查的階段，再補齊缺失的驗證
