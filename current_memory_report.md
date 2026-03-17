# 現有長期記憶機制調查報告

> 更新日期：2026-03-18

## 外部來源狀態

- 原始說明 URL：`https://know-w.pages.dev/article/ai-agent-context-management-%E8%88%87--8fb70bab`
- 2026-03-17 於本機終端實際執行 `Invoke-WebRequest` 抓取失敗。
- 失敗訊息：`嘗試存取通訊端被拒絕，因為存取權限不足。 (know-w.pages.dev:443)`
- 已再嘗試透過 `agent -p` 執行唯讀分析，但 Cursor CLI 回傳 `Error: [internal]`。
- 後續透過本機知識庫筆記 `8fb70bab-5418-49ad-b267-4741958f82df` 取得同一篇文章的完整匯入副本，並以其中 `七、Daily-Digest-Prompt 專案的應用場景` 作為本次設計依據。

## 調查範圍

- `context/digest-memory.json`
- `tools/digest_sync.py`
- `tools/long_term_memory.py`
- `knowledge-base-search/README.md`
- `knowledge-base-search/src/vector-store.ts`
- `tests/tools/test_digest_sync.py`
- `tests/tools/test_long_term_memory.py`

## 現有長期記憶架構概述

目前系統的長期記憶分成兩層：

1. 狀態型記憶：`context/digest-memory.json`
2. 檢索型記憶：`knowledge-base-search` 的本機 JSON 持久化向量庫

### a. 資料模型

#### 1. `context/digest-memory.json`

主要欄位：

| 欄位 | 用途 |
|---|---|
| `last_run` / `last_run_status` / `run_count` | 執行時序與成功狀態 |
| `todoist` / `habits` / `learning` | 短期執行指標與連續天數 |
| `skill_usage` | API 呼叫、快取命中、匯入次數 |
| `knowledge` | 知識庫總筆記數、標籤與匯入量 |
| `digest_summary` | 最近一次摘要的一句話總結 |
| `long_term_memory` | 最後同步時間、最近 note id、保存天數 |

#### 2. `knowledge-base-search/src/vector-store.ts`

`StoredNote` 結構包含：

| 欄位 | 說明 |
|---|---|
| `id`, `title`, `contentText`, `summary` | 基本內容 |
| `tags`, `topic`, `kind` | 分類與檢索標記 |
| `memoryLayer` | 僅有 `recent` / `archive` 兩層 |
| `createdAt`, `updatedAt`, `lastAccessedAt`, `accessCount` | 生命週期與熱度 |
| `importance` | 排序加權 |
| `expiresAt` | 到期時間 |
| `digestDate` | 摘要日期 |
| `embedding` | 向量欄位 |

### b. 更新與刪除策略

#### 寫入策略

- `tools/digest_sync.py`
  - 讀取 `context/digest-memory.json`
  - 組成單篇 daily digest note
  - 透過 `/api/search/hybrid` 嘗試去重
  - 透過 `/api/import` 寫入知識庫
  - 回寫 `context/digest-memory.json.long_term_memory`

- `knowledge-base-search/src/vector-store.ts`
  - `upsertNote()` 支援新增或更新單筆 note
  - `addDocuments()` 可批次匯入文件
  - `persist()` 將全部資料寫入 `data/long_term_memory.json`

#### 清除策略

- `vector-store.ts`
  - `evictExpired()` 會刪除 `expiresAt < now` 的記錄
  - `getActiveNotes()` 在查詢前會直接忽略過期資料
- `tools/long_term_memory.py`
  - 目前只壓縮 `research-registry.json` 與 continuity 歷史
  - 尚未針對 daily/weekly/monthly 摘要層級做分層回收

### c. 查詢流程

目前主要查詢路徑在 `knowledge-base-search`：

1. `semantic search`
   - 以 embedding cosine similarity 比對
2. `keyword search`
   - 以 tokenize + 詞頻比對
3. `hybrid search`
   - 結合 semantic、keyword、importance、freshness
4. `retrieve`
   - 用 hybrid 結果產出 `formattedContext`

實際分數組成：

| 項目 | 權重 |
|---|---|
| semantic | 0.55 |
| lexical | 0.25 |
| importance | 0.10 |
| freshness | 0.10 |

## 目前替代方案與限制

### 現況判定

- 系統已具備「向量檢索能力」。
- 但它不是獨立向量資料庫，而是以本機 JSON 檔 + 程式內記憶體 Map 實作。

### 限制

1. 僅有 `recent/archive` 兩層，沒有 daily/weekly/monthly 分層摘要。
2. 沒有專屬 scheduler 來決定何時產出 daily/weekly/monthly digest。
3. 檢索前雖有 hybrid search，但尚未完整落地文章建議的 `時間衰減 + task-type boost`。
4. 摘要 note 缺少 `taskType` / `retrievalHints` 等可直接支持日常摘要檢索的欄位。
5. 多階段檢索只有 `retrieve -> formattedContext`，尚未把任務類型與 30 天時間窗當成正式檢索參數。
6. 尚未提供 100 筆摘要寫入的固定壓測腳本與標準化測試報告。

## 初步結論

現有系統已經有可用的長期記憶基礎，但偏向「單層 digest note + 本機向量索引」。若要符合跨對話、跨會話、跨時間段的一致性需求，必須補上：

- 三層摘要資料模型
- scheduler 觸發規則
- 脫敏與成本控制
- 分層 TTL / 備份 / 清除
- 多階段檢索流程
- `taskType + taskTags + 30 天時間窗 + 時間衰減` 檢索增強
- 可驗證的測試與部署資產
