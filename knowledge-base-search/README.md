# Knowledge Base Search

使用 **Hono** 框架與 **Mistral 3.2 small**（或 `mistral-small-latest`）建構的知識庫查詢系統，支援 **function calling**、向量檢索、Daily Digest 長期記憶持久化與混合搜尋。

## 功能

- **POST /query**：接受 JSON 格式查詢，回傳 `answer`、`functionCalls`、`sources`
- **POST /api/import**：匯入或更新長期記憶筆記
- **POST /api/search/hybrid**：語義 + 關鍵字 + 新鮮度混合搜尋
- **POST /api/search/semantic**：純向量相似度搜尋
- **POST /api/search/keyword**：關鍵字搜尋
- **POST /api/search/retrieve**：回傳格式化上下文，供 Agent 直接注入
- **主題 / 時間 / 分層篩選**：所有 `/api/search/*` 與 `/api/notes` 均可依 `topic`、`memoryLayer`、`startDate`、`endDate` 過濾
- **持久化儲存**：預設寫入 `data/long_term_memory.json`，重啟後仍保留
- **記憶生命週期欄位**：`summary`、`tags`、`kind`、`topic`、`memoryLayer`、`importance`、`accessCount`、`expiresAt`
- **自動淘汰**：搜尋與匯入時清除過期記憶
- **Function Calling**：模型可呼叫 `fetch_external_data`（外部 API）、`search_knowledge_base`（額外搜尋）
- **錯誤處理**：模型失敗、向量搜尋失敗時回傳適當 HTTP 狀態碼

## 環境需求

- Node.js 18+
- `MISTRAL_API_KEY`（Mistral API 金鑰）

## 安裝

```bash
cd knowledge-base-search
npm install
cp .env.example .env
# 編輯 .env，填入 MISTRAL_API_KEY
```

## 執行

```bash
# 開發模式
npm run dev

# 建置與啟動
npm run build && npm start

# 預設 port 3000，可設定 PORT=8080 npm start
```

## API

### POST /query

```json
// 請求
{ "query": "什麼是 RAG？", "topK": 5 }

// 回應
{
  "answer": "RAG 是 Retrieval-Augmented Generation...",
  "functionCalls": [
    { "name": "search_knowledge_base", "arguments": { "query": "..." }, "result": [...] }
  ],
  "status": "success",
  "sources": [{ "id": "doc-1", "content": "..." }]
}
```

### GET /health

回傳 `{ "status": "ok", "timestamp": "..." }`

### POST /api/import

```json
{
  "notes": [
    {
      "title": "Daily Digest Memory - 2026-03-17",
      "contentText": "# 摘要\n...",
      "tags": ["Daily-Digest-Prompt", "long-term-memory", "daily-digest"],
      "source": "import",
      "summary": "今日摘要長期記憶",
      "kind": "digest",
      "importance": 0.8,
      "expiresAt": "2026-04-16T00:00:00+08:00"
    }
  ]
}
```

### POST /api/search/hybrid

```json
{ "query": "Daily Digest Memory 今日 AI 動態", "topK": 5 }
```

### 篩選參數

`POST /api/search/hybrid`、`/api/search/semantic`、`/api/search/keyword`、`/api/search/retrieve`
都可在 body 追加以下欄位：

```json
{
  "query": "AI digest",
  "topK": 5,
  "topic": "AI",
  "memoryLayer": "recent",
  "startDate": "2026-03-01",
  "endDate": "2026-03-31",
  "tags": ["daily-digest"]
}
```

`GET /api/notes` 亦支援同名 query string，例如：

```text
/api/notes?limit=20&topic=AI&memoryLayer=recent&startDate=2026-03-01&endDate=2026-03-31
```

## 每日摘要同步

可用 Python 工具將 `context/digest-memory.json` 自動寫入長期記憶，內建健康檢查、
去重與指數退避重試：

```bash
python tools/digest_sync.py --base-url http://localhost:3000 --max-retries 3
```

同步成功後，工具會回寫 `context/digest-memory.json` 的 `long_term_memory` 區塊，
更新 `last_sync_at`、`last_note_id`、`sync_status`。

也可直接用同一工具檢索過往每日摘要：

```bash
python tools/digest_sync.py --base-url http://localhost:3000 --query "AI 摘要" --topic AI --memory-layer recent --start-date 2026-03-01 --end-date 2026-03-31
```

## 測試

```bash
npm test
```

涵蓋：
- 基本查詢流程（mock）
- Function executor 單元測試
- 向量儲存與工具 schema 測試

## 環境變數

| 變數 | 說明 |
|------|------|
| `MISTRAL_API_KEY` | 必填，Mistral API 金鑰 |
| `MISTRAL_MODEL` | 選填，預設 `mistral-small-latest` |
| `PORT` | 選填，預設 3000 |
| `KB_STORE_PATH` | 選填，預設 `data/long_term_memory.json` |
| `LOG_LEVEL` | 選填，`info` / `debug` |

## 架構

- `src/server.ts`：Hono 路由、啟動、Daily Digest 相容 REST API
- `src/retriever.ts`：向量檢索（Mistral Embed + InMemoryVectorStore）
- `src/vector-store.ts`：檔案持久化向量庫、分層記憶與混合搜尋/淘汰邏輯
- `src/tools.ts`：Function calling schema
- `src/function-executor.ts`：工具執行邏輯
- `src/seed.ts`：種子資料腳本（獨立執行可預先建置知識庫）

## 注意事項

- 預設為本機 JSON 檔持久化，適合 Daily Digest 單機部署；若要上雲可再替換為 Pinecone、Weaviate 等外部服務
- `fetch_external_data` 僅允許 `http`/`https` URL，有逾時與 body 大小限制
- Mistral function calling 有次數限制，請避免過長對話
