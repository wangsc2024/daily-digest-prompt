# Todoist REST API v2 完整參考

## 認證

所有請求需要 Bearer Token：

```
Authorization: Bearer YOUR_API_TOKEN
```

取得 Token: https://todoist.com/app/settings/integrations/developer

## 端點總覽

| 資源 | 端點 |
|------|------|
| 任務 | `/rest/v2/tasks` |
| 專案 | `/rest/v2/projects` |
| 區段 | `/rest/v2/sections` |
| 標籤 | `/rest/v2/labels` |
| 留言 | `/rest/v2/comments` |

## 任務 API

### 取得所有任務

```
GET https://api.todoist.com/rest/v2/tasks
```

參數：
- `project_id` (string): 專案 ID
- `section_id` (string): 區段 ID  
- `label` (string): 標籤名稱
- `filter` (string): 過濾條件
- `lang` (string): 語言代碼
- `ids` (string): 任務 ID，逗號分隔

### 建立任務

```
POST https://api.todoist.com/rest/v2/tasks
```

Body：
```json
{
  "content": "任務標題",
  "description": "任務描述",
  "project_id": "2203306141",
  "section_id": "7025",
  "parent_id": null,
  "order": 1,
  "labels": ["工作", "重要"],
  "priority": 4,
  "due_string": "tomorrow at 12:00",
  "due_date": "2025-01-30",
  "due_datetime": "2025-01-30T12:00:00Z",
  "due_lang": "zh",
  "assignee_id": "2671355",
  "duration": 30,
  "duration_unit": "minute"
}
```

### 取得單一任務

```
GET https://api.todoist.com/rest/v2/tasks/{task_id}
```

### 更新任務

```
POST https://api.todoist.com/rest/v2/tasks/{task_id}
```

### 完成任務

```
POST https://api.todoist.com/rest/v2/tasks/{task_id}/close
```

### 重新開啟任務

```
POST https://api.todoist.com/rest/v2/tasks/{task_id}/reopen
```

### 刪除任務

```
DELETE https://api.todoist.com/rest/v2/tasks/{task_id}
```

## 過濾器語法

### 日期過濾

| 過濾器 | 說明 |
|--------|------|
| `today` | 今日到期 |
| `tomorrow` | 明日到期 |
| `yesterday` | 昨日到期 |
| `overdue` | 已過期 |
| `no date` | 無截止日期 |
| `7 days` | 未來 7 天 |
| `next week` | 下週 |
| `this month` | 本月 |
| `Jan 15` | 特定日期 |
| `before: Jan 20` | 某日期之前 |
| `after: Jan 10` | 某日期之後 |

### 優先級過濾

| 過濾器 | 說明 |
|--------|------|
| `p1` | 最高優先級（紅色） |
| `p2` | 高優先級（橙色） |
| `p3` | 中優先級（藍色） |
| `p4` | 低優先級（無色） |
| `no priority` | 無優先級（同 p4） |

### 位置過濾

| 過濾器 | 說明 |
|--------|------|
| `#專案名稱` | 特定專案 |
| `##父專案` | 專案及其子專案 |
| `/區段名稱` | 特定區段 |
| `@標籤` | 特定標籤 |

### 人員過濾

| 過濾器 | 說明 |
|--------|------|
| `assigned to: me` | 指派給我 |
| `assigned to: 名字` | 指派給特定人 |
| `assigned by: me` | 我指派的 |
| `assigned` | 有指派的 |
| `!assigned` | 未指派的 |

### 其他過濾

| 過濾器 | 說明 |
|--------|------|
| `recurring` | 循環任務 |
| `!recurring` | 非循環任務 |
| `subtask` | 子任務 |
| `!subtask` | 非子任務 |
| `shared` | 共享專案中的任務 |
| `created: today` | 今日建立 |
| `created before: -7 days` | 7 天前建立 |

### 運算子

| 運算子 | 說明 | 範例 |
|--------|------|------|
| `|` | 或 | `today | overdue` |
| `&` | 且 | `#工作 & p1` |
| `!` | 非 | `!p4` |
| `()` | 群組 | `(today | tomorrow) & p1` |

### 組合範例

```
# 今日或過期的高優先級任務
(today | overdue) & (p1 | p2)

# 工作專案中帶重要標籤的任務
#工作 & @重要

# 未來 7 天但不是 p4 的任務
7 days & !p4

# 指派給我的過期任務
assigned to: me & overdue
```

## 任務物件

```json
{
  "id": "2995104339",
  "assigner_id": "2671355",
  "assignee_id": null,
  "project_id": "2203306141",
  "section_id": null,
  "parent_id": null,
  "order": 1,
  "content": "Buy Milk",
  "description": "",
  "is_completed": false,
  "labels": [],
  "priority": 1,
  "comment_count": 0,
  "creator_id": "2671355",
  "created_at": "2019-12-11T22:36:50.000000Z",
  "due": {
    "date": "2025-01-30",
    "string": "Jan 30",
    "lang": "en",
    "is_recurring": false,
    "datetime": "2025-01-30T12:00:00.000000Z",
    "timezone": "Asia/Taipei"
  },
  "url": "https://todoist.com/showTask?id=2995104339",
  "duration": {
    "amount": 30,
    "unit": "minute"
  }
}
```

## 優先級值

| API 值 | 顯示 | 顏色 |
|--------|------|------|
| 4 | p1 | 紅色 |
| 3 | p2 | 橙色 |
| 2 | p3 | 藍色 |
| 1 | p4 | 無 |

**注意**：API 值與 UI 顯示相反（4 = p1 最高）

## 專案 API

### 取得所有專案

```
GET https://api.todoist.com/rest/v2/projects
```

### 建立專案

```
POST https://api.todoist.com/rest/v2/projects
```

Body：
```json
{
  "name": "專案名稱",
  "parent_id": null,
  "color": "blue",
  "is_favorite": false,
  "view_style": "list"
}
```

## 標籤 API

### 取得所有標籤

```
GET https://api.todoist.com/rest/v2/labels
```

### 建立標籤

```
POST https://api.todoist.com/rest/v2/labels
```

Body：
```json
{
  "name": "標籤名稱",
  "color": "red",
  "order": 1,
  "is_favorite": false
}
```

## 顏色值

可用顏色：`berry_red`, `red`, `orange`, `yellow`, `olive_green`, `lime_green`, `green`, `mint_green`, `teal`, `sky_blue`, `light_blue`, `blue`, `grape`, `violet`, `lavender`, `magenta`, `salmon`, `charcoal`, `grey`, `taupe`

## 速率限制

- 限制：450 請求 / 15 分鐘
- 超過返回 429 狀態碼
- Header `X-RateLimit-Remaining` 顯示剩餘次數

## 錯誤回應

```json
{
  "error": "error_message",
  "error_code": 400,
  "error_extra": {},
  "error_tag": "INVALID_REQUEST",
  "http_code": 400
}
```

| 狀態碼 | 說明 |
|--------|------|
| 400 | 請求格式錯誤 |
| 401 | 認證失敗 |
| 403 | 權限不足 |
| 404 | 資源不存在 |
| 429 | 請求過多 |
| 500 | 伺服器錯誤 |
