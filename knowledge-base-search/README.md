# Knowledge Base Search

使用 **Hono** 框架與 **Mistral 3.2 small**（或 `mistral-small-latest`）建構的知識庫查詢系統，支援 **function calling** 與向量檢索。

## 功能

- **POST /query**：接受 JSON 格式查詢，回傳 `answer`、`functionCalls`、`sources`
- **向量檢索**：使用 Mistral Embed 將查詢與文件向量化，以餘弦相似度搜尋
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
| `LOG_LEVEL` | 選填，`info` / `debug` |

## 架構

- `src/server.ts`：Hono 路由、啟動、錯誤處理
- `src/retriever.ts`：向量檢索（Mistral Embed + InMemoryVectorStore）
- `src/vector-store.ts`：記憶體向量庫（可替換為 Pinecone/Weaviate）
- `src/tools.ts`：Function calling schema
- `src/function-executor.ts`：工具執行邏輯
- `src/seed.ts`：種子資料腳本（獨立執行可預先建置知識庫）

## 注意事項

- 內建向量庫為記憶體型，重啟後資料會消失；可改用 Pinecone、Weaviate 等外部服務
- `fetch_external_data` 僅允許 `http`/`https` URL，有逾時與 body 大小限制
- Mistral function calling 有次數限制，請避免過長對話
