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

## 注意事項
- 用 Write 工具建立 JSON 檔案，確保 UTF-8 編碼
- 快取檔名固定，每次覆寫（不累積）
- 快取僅供每日摘要 Agent 使用，Todoist Agent 不使用快取（需即時資料）
- `cached_at` 使用 ISO 8601 UTC 格式
