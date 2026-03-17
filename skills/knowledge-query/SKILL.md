---
name: knowledge-query
version: "1.0.0"
description: |
  個人知識庫查詢與匯入。查詢 localhost:3000 知識庫筆記，或將研究成果匯入。
  Use when: 知識庫、筆記、搜尋筆記、匯入、研究成果、知識查詢。
allowed-tools: Bash, Read, Write
cache-ttl: 60min
depends-on:
  - config/dependencies.yaml
triggers:
  - "知識庫"
  - "筆記"
  - "搜尋筆記"
  - "匯入"
  - "研究成果"
  - "知識查詢"
  - "KB"
  - "knowledge base"
  - "查詢筆記"
  - "寫入筆記"
  - "知識管理"
---

# 知識庫查詢與匯入

## 依賴注入（DI）

> 端點來源：`config/dependencies.yaml` → `skills.knowledge_query`（ADR-001 Phase 3）
> 執行前讀取 YAML 取得 `base_url`；若 YAML 不可讀則 fallback 使用下方預設值。
>
> **讀取片段**（在每個需要呼叫 API 的步驟開頭執行）：
> ```bash
> BASE=$(uv run python -X utf8 -c "import yaml; d=yaml.safe_load(open('config/dependencies.yaml')); print(d['skills']['knowledge_query']['api']['base_url'])" 2>/dev/null || echo "http://localhost:3000")
> ```

查詢個人知識庫取得筆記內容，或將研究成果匯入知識庫。

## 前提條件

知識庫服務必須在本機執行中：`http://localhost:3000`

## 欄位分工（重要）

知識庫有兩個內容欄位，用途不同：

| 欄位 | 格式 | 用途 | 匯入時怎麼填 |
|------|------|------|-------------|
| `contentText` | Markdown / 純文字 | **全文搜尋索引**（FTS5 + 向量搜尋） | **必填**：放你的 Markdown 內容 |
| `content` | Tiptap JSON | **前端編輯器渲染** | **不填**：後端從 contentText 自動生成 |

**規則：匯入時只需填 `contentText`，`content` 由後端自動轉換。**

---

## 查詢筆記

### 步驟 0：快取狀態確認（必做）

用 Read 讀取 `cache/knowledge.json`：
- 存在且 TTL 未過期（60 分鐘）→ 可直接使用快取資料
- 不存在或已過期 → 繼續步驟 1 呼叫 API

> 此步驟確保 Harness 記錄 `cache-read` 標籤，避免快取繞過警告。

### 步驟 1：確認服務是否運行

```bash
curl -s "http://localhost:3000/api/health"
```

若回傳錯誤或無回應，跳過知識庫區塊並在摘要中標註「知識庫服務未啟動」。

### 步驟 2：選擇查詢方式並取得筆記

知識庫 API 提供多種查詢方式，依情境選擇：

| 方式 | API | 適用情境 |
|------|-----|----------|
| **混合搜尋** | POST /api/search/hybrid | 一般查詢、高召回（語義＋關鍵字 RRF） |
| **語義搜尋** | POST /api/search/semantic | 概念性問題、模糊搜尋、相關主題 |
| **關鍵字搜尋** | POST /api/search/keyword | 精確詞、專有名詞、程式碼/錯誤訊息 |
| **標籤搜尋** | GET /api/search/tags/:tag | 依標籤瀏覽（如 #typescript） |
| **檢索上下文** | POST /api/search/retrieve | 取得格式化段落，由 Agent 自行組織回答（不呼叫 LLM） |
| **最近筆記** | GET /api/notes?limit=N | 僅列標題、不搜尋 |

**混合搜尋（推薦，每日回顧或一般問句）：**

```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"今日學習 筆記 重點\", \"topK\": 5}"
```

**語義搜尋（概念性問題）：**

```bash
curl -s -X POST "http://localhost:3000/api/search/semantic" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"什麼是依賴注入\", \"topK\": 3, \"minScore\": 0.6}"
```

**關鍵字搜尋（精確詞）：**

```bash
curl -s -X POST "http://localhost:3000/api/search/keyword" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"useState\", \"topK\": 10}"
```

**檢索上下文（從知識庫中回答型：只取資料、自己組織答案）：**

Windows 請用 JSON 檔案發送：

```bash
# 先以 Write 建立 body.json：{"query":"使用者問題","topK":5}
curl -s -X POST "http://localhost:3000/api/search/retrieve" \
  -H "Content-Type: application/json; charset=utf-8" -d @body.json
```

回傳含 `formattedContext`，可直接作為 LLM 的 context，**僅根據此內容回答**。

**取得最近筆記列表：**

```bash
curl -s "http://localhost:3000/api/notes?limit=20"
```

### 步驟 3：產出摘要

從查詢結果中挑選 1-3 則最相關的筆記，格式：

```
📝 知識庫回顧
- [筆記標題]：一句話摘要
```

---

## 匯入筆記

將研究成果或整理內容匯入知識庫。

> **Windows 注意**：POST 的 inline JSON 在 Windows Bash 會失敗，必須用 JSON 檔案方式發送。

### 匯入步驟（使用 /api/import）

```bash
# 步驟 1：用 Write 工具建立 JSON 檔案（import_note.json）
#
# ⚠️ 重點：內容放在 contentText，content 不要填
#
# {
#   "notes": [
#     {
#       "title": "筆記標題",
#       "contentText": "你的 Markdown 內容\n\n## 子標題\n\n- 列表項\n- **粗體文字**",
#       "tags": ["標籤1", "標籤2"],
#       "source": "import"
#     }
#   ],
#   "autoSync": true
# }

# 步驟 2：用 curl 發送
curl -s -X POST "http://localhost:3000/api/import" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @import_note.json

# 步驟 3：刪除暫存檔
rm import_note.json
```

### contentText 支援的 Markdown 語法

後端會自動將以下語法轉為 Tiptap JSON：

- 標題（# ## ###）
- 段落（空行分隔）
- 無序列表（- 或 *）
- 有序列表（1. 2. 3.）
- 程式碼區塊（```）
- 引用區塊（>）
- 分隔線（---）
- **粗體**（\*\*text\*\*）
- *斜體*（\*text\*）
- 行內程式碼（\`code\`）
- 連結（[text](url)）

### 欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `title` | 是 | 筆記標題（最長 200 字元） |
| `contentText` | 是 | Markdown 或純文字內容（後端自動轉為 Tiptap JSON 存入 content） |
| `tags` | 否 | 標籤陣列，便於分類搜尋 |
| `source` | 否 | 僅接受：`manual`、`web`、`import`（預設 `import`） |

> **禁止**：不要自己填 `content` 欄位。讓後端從 `contentText` 自動生成 Tiptap JSON。

### 批量匯入（多筆）

一次最多匯入 100 筆：

```bash
# {
#   "notes": [
#     { "title": "筆記1", "contentText": "內容1", "tags": ["tag1"] },
#     { "title": "筆記2", "contentText": "內容2", "tags": ["tag2"] }
#   ],
#   "autoSync": true
# }
```

### 回應格式

```json
{
  "message": "Imported 1 notes, 0 failed",
  "result": {
    "success": true,
    "imported": 1,
    "failed": 0,
    "errors": [],
    "noteIds": ["uuid"]
  }
}
```

## 知識庫統計

查詢知識庫整體狀態（用於健康監控和記憶寫入）：

```bash
curl -s "http://localhost:3000/api/stats"
```

回傳欄位包含總筆記數、標籤統計等，用於 digest-memory.json 的 `knowledge` 區塊。

## 標籤列表

查詢現有所有標籤（用於匯入前的標籤一致性檢查）：

```bash
curl -s "http://localhost:3000/api/notes/tags"
```

## 從知識庫中回答（RAG 流程）

當任務為「從知識庫中找資料回答」時，建議流程：

1. 呼叫 **POST /api/search/retrieve**，body：`{"query": "使用者問題", "topK": 5}`（Windows 用 JSON 檔發送）。
2. 取回 `formattedContext`，作為 LLM 的 context。
3. **僅根據 formattedContext 的內容回答**；若為空或無相關筆記，如實說明「知識庫中暫無相關筆記」。

可選：先 **GET /api/stats** 了解筆記總數與健康狀態；需要單篇全文時用 **GET /api/notes/:id**。

## 注意事項

- 如果知識庫服務未啟動，不要報錯，只需在摘要中省略此區塊
- 查詢時依情境選 API：概念性用 semantic、精確詞用 keyword、一般用 hybrid、只要段落用 retrieve
- 匯入前先確認服務 health check 通過
- **匯入內容放 `contentText`，不要填 `content`**
- 不要手動建構 Tiptap JSON
- 匯入前用 `/api/search/hybrid` 去重（score > 0.85 即為重複）
