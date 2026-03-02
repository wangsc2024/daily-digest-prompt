---
name: groq
version: 1.0.0
description: Groq 快速推理 Skill — 透過本機 Relay 呼叫 Groq API，提供快速摘要、翻譯、分類、結構化萃取，作為 Claude 的低成本前處理層。
allowed-tools: [Bash, Write]
triggers:
  - groq
  - 快速摘要
  - 快速翻譯
  - en_to_zh
  - 英文摘要
  - 批次翻譯
  - 輕量分類
  - groq-relay
  - 前處理
depends-on: []
---

# Groq Skill — 快速推理前處理層

## 架構說明

```
Claude Code Agent
  └─ curl http://localhost:3001/groq/chat
       └─ groq-relay.js (port 3001，持有 GROQ_API_KEY)
            └─ Groq API (llama-3.1-8b-instant)
```

**安全設計**：Agent 不直接持有 API KEY，由 `bot/groq-relay.js` 代理，避免 pre_read_guard 攔截。

**降級設計**：Relay 不可用時，記錄 skip 並繼續主流程，**不中斷** Agent 執行。

---

## 前置確認

執行任何 Groq 操作前，先確認 Relay 服務可用：

```bash
curl -s --max-time 3 http://localhost:3001/groq/health
```

- 回傳 `{"status":"ok"}` → Relay 可用，繼續
- 連線拒絕 / 逾時 → Relay 未啟動，跳過 Groq 步驟，記錄 `groq_skipped: true`

---

## 四個操作模式

### 模式 1：summarize（一句話摘要）

**用途**：將一段文字壓縮為 30 字以內的正體中文摘要。

```bash
# 建立請求 JSON（用 Write 工具，確保 UTF-8）
# 然後執行：
curl -s --max-time 20 -X POST http://localhost:3001/groq/chat \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @/tmp/groq-request.json
```

請求 JSON 格式：
```json
{
  "mode": "summarize",
  "content": "要摘要的文字內容（最長 8000 字元）"
}
```

回應格式：
```json
{"result": "摘要文字（≤30字）", "cached": false, "model": "llama-3.1-8b-instant"}
```

---

### 模式 2：translate（英文轉正體中文）

**用途**：將英文文章標題或段落翻譯為正體中文，保留技術術語。

```json
{
  "mode": "translate",
  "content": "英文標題或段落"
}
```

回應：
```json
{"result": "正體中文譯文（技術術語原文括弧附上）", "cached": false}
```

**典型使用場景**：HN AI 新聞標題批次翻譯（替代 Claude 逐一翻譯，降低 token 消耗）。

---

### 模式 3：classify（主題分類）

**用途**：為文章或任務自動打主題標籤（JSON 輸出）。

```json
{
  "mode": "classify",
  "content": "文章標題或摘要"
}
```

回應：
```json
{"result": "{\"tags\":[\"人工智慧\",\"LLM\",\"開源\"]}", "cached": false}
```

注意：`result` 是 JSON 字串，需再次解析：`JSON.parse(response.result)`

---

### 模式 4：extract（結構化萃取）

**用途**：從非結構化文字中萃取關鍵資訊（JSON 輸出）。

```json
{
  "mode": "extract",
  "content": "文章全文或摘要"
}
```

回應：
```json
{"result": "{\"key_points\":[\"要點1\",\"要點2\"],\"summary\":\"摘要\",\"confidence\":\"high\"}", "cached": false}
```

---

## 完整操作範例（批次翻譯 HN 標題）

```bash
# 步驟 1：建立請求 JSON
# 用 Write 工具建立 /tmp/groq-hn-translate.json：
# {"mode":"translate","content":"Meta releases new open-source LLM with 70B parameters"}

# 步驟 2：呼叫 Relay
curl -s --max-time 20 -X POST http://localhost:3001/groq/chat \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @/tmp/groq-hn-translate.json

# 步驟 3：解析結果（從 JSON 的 result 欄位取值）
```

---

## 速率限制與快取

| 項目 | 預設值 | 說明 |
|------|--------|------|
| 免費方案限速 | 5 req/min | Relay 內建速率限制 |
| 快取 TTL | 5 分鐘 | 相同 mode+content 命中快取 |
| 請求逾時 | 20s | curl `--max-time` 設定 |
| 最大輸入長度 | 8000 字元 | Relay 自動截斷 |

**配額超限（429）回應**：
```json
{"error": "已達 Groq 配額上限，請稍後再試"}
```

遇到 429 時：等待 22 秒後重試一次，仍失敗則跳過。

---

## 降級策略

Groq Relay 失敗時，**不中斷主流程**，記錄 `groq_skipped: true` 並繼續：

```json
{
  "groq_skipped": true,
  "groq_skip_reason": "relay_unavailable | quota_exceeded | timeout",
  "fallback": "claude_inline"
}
```

結果檔案中加入 `groq_status` 欄位供 Phase 2（assemble-digest）參考。

---

## 與 llm-router.yaml 的關係

`config/llm-router.yaml` 定義哪些任務類型路由到 Groq：

| routing_rule | 映射 | 說明 |
|-------------|------|------|
| `news_summary` | groq | 新聞快速摘要 |
| `en_to_zh` | groq | 英文翻譯 |
| `topic_classify` | groq | 主題分類 |
| `policy_analysis` | claude | 政策深度解讀（保留給 Claude） |
| `code_review` | claude | 程式碼審查（保留給 Claude） |

---

## 啟動 Relay 服務

```powershell
# 手動啟動（開發時）
node bot/groq-relay.js

# 背景啟動
Start-Process -NoNewWindow node -ArgumentList "bot/groq-relay.js"

# 確認啟動
curl http://localhost:3001/groq/health
```

Relay 啟動後持續運行，不需每次請求重啟。建議整合到 Windows Task Scheduler 或隨 bot.js 一起啟動。
