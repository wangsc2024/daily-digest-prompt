-----

## name: pingtung-news
description: 屏東縣政府新聞查詢工具。查詢屏東縣最新新聞、依關鍵字搜尋新聞、依日期範圍篩選新聞稿。適用於查詢屏東新聞、屏東縣政、周春米縣長施政、屏東縣府公告等相關資訊。

# 屏東新聞通

查詢屏東縣政府新聞稿資料，支援 Claude Chat 與 Claude Code 環境。

## 資料來源

- **原始 API**：`https://www.pthg.gov.tw/OpenDataForm.aspx?s=05393D58A2AA3E5B`
- **MCP 服務**：`https://ptnews-mcp.pages.dev`
- **資料範圍**：2022年12月25日起（周春米縣長就職日）

-----

## 查詢方式：統一使用 Bash curl

> ⚠️ **重要**：不論 Claude Chat 或 Claude Code，一律使用 bash curl 呼叫 MCP 服務。
> Claude Chat 的 WebFetch 工具無法抓取非用戶提供的 URL（會回傳 PERMISSIONS_ERROR），
> 但 Claude Chat 具備 bash_tool，可直接執行 curl 指令。

### 可用 Tools

|Tool 名稱                |說明    |參數                       |
|-----------------------|------|-------------------------|
|`pingtung_news_latest` |取得最新新聞|count: 1-50（預設 10）       |
|`pingtung_news_search` |關鍵字搜尋 |keyword: 必填, limit: 1-100|
|`pingtung_news_by_date`|日期範圍查詢|start, end: YYYY-MM-DD 格式|

-----

## ⚠️ 重試機制（必讀）

縣府原始 API **間歇性不穩定**，經常回傳 521（Web Server Is Down）錯誤。
MCP 服務本身正常，但每次請求都會即時抓取縣府 API，因此會連帶失敗。

**關鍵原則：遇到 521 錯誤，不要放棄，自動重試！**

### 帶重試的查詢模板（推薦）

```bash
for i in 1 2 3 4 5; do
  result=$(curl -s -X POST https://ptnews-mcp.pages.dev/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pingtung_news_latest","arguments":{"count":3}}}')
  if echo "$result" | grep -q '"error"'; then
    sleep 2
    continue
  fi
  echo "$result"
  break
done
```

### 帶重試的搜尋模板

```bash
for i in 1 2 3 4 5; do
  result=$(curl -s -X POST https://ptnews-mcp.pages.dev/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pingtung_news_search","arguments":{"keyword":"長照","limit":10}}}')
  if echo "$result" | grep -q '"error"'; then
    sleep 2
    continue
  fi
  echo "$result"
  break
done
```

### 帶重試的日期查詢模板

```bash
for i in 1 2 3 4 5; do
  result=$(curl -s -X POST https://ptnews-mcp.pages.dev/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pingtung_news_by_date","arguments":{"start":"2026-02-01","end":"2026-02-28"}}}')
  if echo "$result" | grep -q '"error"'; then
    sleep 2
    continue
  fi
  echo "$result"
  break
done
```

> 💡 根據實測，通常重試 2-3 次即可成功。最多重試 5 次，每次間隔 2 秒。

-----

## 結果解析

MCP 回傳的 JSON 結構為雙層巢狀（text 欄位內含跳脫的 JSON 陣列）。
Claude 可以直接從 bash 輸出中讀取並整理，不需要額外用 python 解析。

### 回傳格式結構

```
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{
      "type": "text",
      "text": "[{\"id\":\"5094\",\"title\":\"...\",\"publishedAt\":\"...\",\"content\":\"...\",\"summary\":\"...\"}]"
    }]
  }
}
```

### 每則新聞欄位

|欄位           |說明               |
|-------------|-----------------|
|`id`         |新聞 ID            |
|`title`      |新聞標題             |
|`department` |發布單位代碼           |
|`publishedAt`|發布時間（ISO 8601 格式）|
|`content`    |新聞完整內容           |
|`summary`    |前 200 字摘要        |

-----

## 常見查詢對照

|用戶說法       |呼叫方式                                       |
|-----------|-------------------------------------------|
|「屏東最新新聞」   |`pingtung_news_latest`，count 依需求設定         |
|「屏東長照新聞」   |`pingtung_news_search`，keyword: “長照”       |
|「周春米相關新聞」  |`pingtung_news_search`，keyword: “周春米”      |
|「2024年1月新聞」|`pingtung_news_by_date`，start/end 設定範圍     |
|「旅遊相關新聞」   |`pingtung_news_search`，keyword: “觀光” 或 “旅遊”|

-----

## 輸出格式建議

### 新聞列表格式

```markdown
| # | 日期 | 標題 |
|---|------|------|
| 1 | 2024-01-15 | 新聞標題... |
| 2 | 2024-01-14 | 新聞標題... |
```

### 新聞詳情格式

```markdown
## 新聞標題

**日期**：2024-01-15 14:30

**內容**：
新聞完整內容...
```

-----

## 錯誤處理流程

```
呼叫 MCP → 成功？→ 是 → 解析並呈現結果
                → 否（521）→ 等 2 秒 → 重試（最多 5 次）
                              → 5 次都失敗 → 告知用戶「縣府 API 暫時無法連線，請稍後再試」
```

**禁止行為**：

- ❌ 第一次失敗就放棄，改用 web_search 或其他方式
- ❌ 告訴用戶「MCP 服務無法連線」（服務本身是正常的）
- ❌ 用之前對話中的快取資料冒充最新新聞

**正確行為**：

- ✅ 自動重試最多 5 次，間隔 2 秒
- ✅ 失敗時準確說明「縣府原始 API 暫時不穩定」
- ✅ 如果 `pingtung_news_latest` 失敗但 `pingtung_news_search` 可能成功（它們獨立快取），可以嘗試換一個 tool

-----

## 服務狀態檢查

```bash
curl -s https://ptnews-mcp.pages.dev/health
# 回傳：{"status":"ok","timestamp":"..."}
```

## 注意事項

1. **即時資料**：資料直接從縣府開放資料取得，確保最新
1. **5 分鐘快取**：MCP 服務會快取資料 5 分鐘
1. **日期格式**：查詢使用 `YYYY-MM-DD` 格式
1. **關鍵字搜尋**：會同時搜尋標題和內容
1. **521 錯誤**：縣府 API 間歇性不穩定，務必實作重試機制
1. **不同 tool 可能獨立快取**：latest 失敗時可嘗試 search 或 by_date
