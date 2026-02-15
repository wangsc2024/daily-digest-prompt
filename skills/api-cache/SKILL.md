---
name: api-cache
version: "1.0.0"
description: |
  HTTP 回應快取與降級。快取 API 回應避免限速，故障時自動降級使用過期快取。
  Use when: 快取、cache、降級、API 故障。
allowed-tools: Bash, Read, Write
triggers:
  - "快取"
  - "cache"
  - "降級"
  - "API 故障"
---

# API Cache Skill - HTTP 回應快取

## 用途
快取外部 API 回應，避免重複呼叫被限速，API 故障時提供降級服務。

## 快取目錄
`cache/`

## 快取檔案格式

每個 API 來源一個 JSON 檔案：

| 來源 | 檔名 | 有效期 |
|------|------|--------|
| Todoist | `cache/todoist.json` | 30 分鐘 |
| 屏東新聞 | `cache/pingtung-news.json` | 6 小時 |
| HN AI 新聞 | `cache/hackernews.json` | 2 小時 |
| 知識庫 | `cache/knowledge.json` | 1 小時 |

快取檔案結構：
```json
{
  "cached_at": "2026-02-11T08:00:00",
  "ttl_minutes": 30,
  "source": "todoist",
  "data": { ... 原始 API 回應 ... }
}
```

## 使用流程

### 讀取快取（API 呼叫前）

1. 用 Read 工具讀取對應的快取檔案
2. 若檔案不存在 → 直接呼叫 API
3. 若檔案存在，檢查時效：
   - 用 Bash 取得當前時間戳記：`date -u +%s`
   - 用 Bash 取得快取時間戳記：`date -u -d "CACHED_AT" +%s` （替換 CACHED_AT）
   - 計算差值（秒），換算為分鐘
   - 若在有效期內 → 使用快取資料，跳過 API 呼叫
   - 若已過期 → 呼叫 API

### 寫入快取（API 呼叫成功後）

1. 將 API 回應包裝為快取格式
2. 用 Write 工具寫入對應的快取檔案

### 降級使用（API 呼叫失敗時）

1. 若 API 呼叫失敗（timeout、錯誤碼、無回應）
2. 嘗試讀取快取檔案（即使已過期）
3. 若有過期快取可用：
   - 使用快取資料
   - 在摘要中標注：`⚠️ 資料來自快取（更新時間：HH:MM）`
4. 若無快取可用：
   - 回報錯誤，該區塊標注「服務暫時不可用」

## 降級決策表

所有 prompt（含 daily-digest、todoist、team mode）統一參照此表：

| API 來源 | TTL | 降級時限 | 降級標記 |
|---------|-----|---------|---------|
| Todoist | 30 分鐘 | 24 小時 | `⚠️ 資料來自快取（HH:MM）` |
| 屏東新聞 | 6 小時 | 24 小時 | `⚠️ 資料來自快取（HH:MM）` |
| HN AI | 2 小時 | 24 小時 | `⚠️ 資料來自快取（HH:MM）` |
| 知識庫 | 1 小時 | 24 小時 | `⚠️ 資料來自快取（HH:MM）` |
| Gmail | 30 分鐘 | 24 小時 | `⚠️ 資料來自快取（HH:MM）` |

**規則**：API 失敗時，若快取存在且未超過「降級時限」→ 使用過期快取並標記；否則回報「服務不可用」。

## 快取檔案清理

快取檔案不需要定期清理（會被覆寫），但超過 24 小時的快取視為無效，降級時也不使用。

## 簡化判斷邏輯（給 Agent 的偽代碼）

```
function get_data(source):
  cache_file = "cache/{source}.json"

  // 1. 嘗試讀取快取
  if cache_file exists:
    cache = read(cache_file)
    age_minutes = (now - cache.cached_at) in minutes
    if age_minutes <= cache.ttl_minutes:
      return cache.data  // 快取命中

  // 2. 呼叫 API
  try:
    data = call_api(source)
    write_cache(cache_file, data)  // 寫入快取
    return data
  catch:
    // 3. API 失敗，嘗試降級
    if cache_file exists AND age_minutes <= 1440:  // 24 小時內
      return cache.data + "[來自快取]" 標記
    else:
      return error("服務不可用")
```

## 快取命中追蹤（必做）

Agent 執行期間，必須維護以下計數器，供寫入 digest-memory 時使用：

| 計數器 | 說明 | 更新時機 |
|--------|------|---------|
| `cache_hits` | 快取命中次數 | 每次從快取取得有效資料時 +1 |
| `api_calls` | API 實際呼叫次數 | 每次執行外部 curl 呼叫時 +1 |
| `cache_degraded` | 降級使用過期快取次數 | API 失敗且使用過期快取時 +1 |

### 追蹤流程

每次執行快取流程時，按以下邏輯更新計數器：

```
function get_data(source):
  cache_file = "cache/{source}.json"

  // 1. 嘗試讀取快取
  if cache_file exists:
    cache = read(cache_file)
    age_minutes = (now - cache.cached_at) in minutes
    if age_minutes <= cache.ttl_minutes:
      cache_hits += 1              // ← 快取命中，遞增計數器
      output "[cache] {source}: 快取命中（{age_minutes}分鐘前）"
      return cache.data

  // 2. 呼叫 API
  try:
    api_calls += 1                 // ← API 呼叫，遞增計數器
    data = call_api(source)
    write_cache(cache_file, data)
    output "[api] {source}: API 成功，已更新快取"
    return data
  catch:
    // 3. API 失敗，嘗試降級
    if cache_file exists AND age_minutes <= 1440:  // 24 小時內
      cache_degraded += 1          // ← 降級使用，遞增計數器
      output "[degraded] {source}: API 失敗，降級使用過期快取"
      return cache.data + "[來自快取]" 標記
    else:
      output "[error] {source}: 服務不可用"
      return error("服務不可用")
```

### 輸出日誌格式

每個快取操作必須輸出一行日誌（方便追蹤）：
- `[cache] todoist: 快取命中（15分鐘前）`
- `[api] pingtung-news: API 成功，已更新快取`
- `[degraded] hackernews: API 失敗，降級使用過期快取`
- `[error] knowledge: 服務不可用`

### 寫入 digest-memory

執行結束時，將計數器寫入 `context/digest-memory.json` 的 `skill_usage` 區塊：
```json
"skill_usage": {
  "total_skills": 12,
  "used_skills": 11,
  "cache_hits": 2,      // ← 從計數器取值
  "api_calls": 3,       // ← 從計數器取值
  "cache_degraded": 0,  // ← 新增欄位
  "knowledge_imports": 0
}
```

> **重要**：`cache_hits` 為 0 表示快取完全沒發揮作用，應檢查 TTL 設定或呼叫頻率。

---

## 注意事項
- 用 Write 工具建立 JSON 檔案，確保 UTF-8 編碼
- 快取檔名固定，每次覆寫（不累積）
- 快取僅供每日摘要 Agent 使用，Todoist Agent 不使用快取（需即時資料）
- `cached_at` 使用 ISO 8601 UTC 格式
- **執行開始時**，先輸出當前快取狀態（存在/不存在/距上次更新時間）以便追蹤
