---
name: chatroom-query
version: 1.0.0
description: >
  bot.js REST API 互動 Skill。查詢 Gun.js 聊天室任務佇列、認領任務、執行後回報結果。
  支援健康檢查、待處理任務列舉、任務生命週期管理（claim→processing→completed）。
allowed-tools: [Read, Bash, Write]
triggers:
  - "chatroom"
  - "聊天室"
  - "bot.js"
  - "Gun.js 任務"
  - "任務佇列"
  - "pending 任務"
  - "wsc-bot"
---

# chatroom-query Skill v1.0.0

## API 連線資訊

- **Base URL**：`http://localhost:3001`
- **認證**：Bearer Token — `Authorization: Bearer $BOT_API_SECRET_KEY`
- **免認證端點**：`/api/health` 僅此一個

> ⚠️ **禁止使用 `echo $BOT_API_SECRET_KEY`** — Harness 會攔截。若 Token 未設定，直接在結果中記錄錯誤，不要嘗試讀取方式。

---

## 端點清單

### 健康檢查（無需認證）
```bash
curl -s http://localhost:3001/api/health
```
**回傳**：`{ "status":"ok", "connected":true, "pendingTasks":N, "uptime":秒數 }`

---

### 查詢待處理任務
```bash
curl -s -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  "http://localhost:3001/api/records?state=pending&limit=20"
```
**回傳**：`{ "total":N, "count":N, "records":[...] }`
**任務物件欄位**：`uid`、`content`（任務描述）、`is_research`（是否為研究任務）、`state`、`time`（建立時間）

---

### 查詢各狀態任務數
```bash
# pending
curl -s -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  "http://localhost:3001/api/records?state=pending&limit=1"
# claimed/processing — 同上，修改 state 參數
# completed（今日統計用）
curl -s -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  "http://localhost:3001/api/records?state=completed&limit=50"
```

---

### 認領任務（Claim）
```bash
# 先建立請求 JSON（避免 Windows bash inline JSON 問題）
cat > /tmp/claim_body.json << 'EOF'
{"worker_id": "claude-agent"}
EOF
curl -s -X PATCH \
  -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/claim_body.json \
  "http://localhost:3001/api/records/{uid}/claim"
rm -f /tmp/claim_body.json
```
**成功**：`{ "success":true, "claim_generation":N }`
**失敗**：409（已被認領）、404（不存在）、400（狀態不符）

---

### 更新任務狀態為 processing
```bash
cat > /tmp/state_body.json << 'EOF'
{"state": "processing", "worker_id": "claude-agent", "claim_generation": {N}}
EOF
curl -s -X PATCH \
  -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/state_body.json \
  "http://localhost:3001/api/records/{uid}/state"
rm -f /tmp/state_body.json
```

---

### 完成任務（提交結果）
```bash
# result 欄位為字串，使用 Write 工具建立 JSON 避免特殊字元問題
# 在 Python 中安全轉義結果
python -c "
import json, sys
result = '''執行完成，結果如下：...'''
body = {'claim_generation': {N}, 'result': result}
print(json.dumps(body, ensure_ascii=False))
" > /tmp/complete_body.json

curl -s -X PATCH \
  -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @/tmp/complete_body.json \
  "http://localhost:3001/api/records/{uid}/processed"
rm -f /tmp/complete_body.json
```
**成功**：`{ "success":true }`
**失敗**：409（認領世代不符 — 已被其他 worker 搶先）

---

### 查詢排程任務
```bash
# 定時任務
curl -s -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  "http://localhost:3001/api/scheduled-tasks?status=waiting&limit=10"

# Cron 排程
curl -s -H "Authorization: Bearer $BOT_API_SECRET_KEY" \
  "http://localhost:3001/api/cron-jobs"
```

---

## 快取策略

讀取 `config/cache-policy.yaml` 取得 `chatroom` 的 TTL：
- **TTL**：15 分鐘（任務佇列變化快，需短 TTL）
- **降級 TTL**：120 分鐘
- **快取檔案**：`cache/chatroom.json`

**快取格式**：
```json
{
  "cached_at": "2026-02-28T08:00:00Z",
  "ttl_minutes": 15,
  "source": "chatroom",
  "data": { "pending_count": 3, "records": [...] }
}
```

---

## 錯誤處理

| 情況 | 處理方式 |
|------|---------|
| bot.js 未啟動（連線拒絕） | `status=failed`，跳過任務認領，記錄原因 |
| `BOT_API_SECRET_KEY` 未設定 | 用健康檢查端點（不需認證）取得基本狀態；任務認領記錄「認證未配置」 |
| 409 Claim 衝突 | 跳過此任務，嘗試下一筆 pending 任務 |
| 409 Complete 世代不符 | 記錄錯誤，不重試（樂觀鎖失敗，任務可能已被釋放） |
| API 回傳非 200 | 記錄 HTTP 狀態碼，使用降級快取繼續執行 |

---

## Gun.js 資料結構（供參考）

```
gun.get('render_isolated_chat_room')  ← 聊天室訊息 graph
gun.get('wsc-bot/handshake')          ← epub + 簽章（G20 防 MITM）
  └── epub, sig
```

訊息由 SEA 加密，使用 ECDH sharedSecret。Claude Agent 透過 REST API 取得解密後的任務內容，不需直接操作 Gun.js graph。
