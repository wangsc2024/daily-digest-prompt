---
name: todoist
description: |
  Todoist 待辦事項整合 - 查詢、新增、完成、刪除任務。支援專案、標籤、優先級、截止日期等完整功能。
  Use when: 管理待辦事項、查詢今日任務、新增刪除任務、過濾優先級，or when user mentions todoist, 待辦, todo, 任務.
  Triggers: "todoist", "待辦事項", "todo", "任務", "今日任務", "過期任務", "新增任務", "完成任務", "task"
version: 2.0.0
allowed-tools: Bash, Read, Write
cache-ttl: 30min
---

# Todoist 待辦事項整合

透過 Todoist API v1（`/api/v1/`）管理任務。

> **注意**：舊版 REST API v2（`/rest/v2/`）已於 2026 年棄用（回傳 410 Gone）。
> 所有端點已遷移至 `/api/v1/`。回應格式從直接陣列改為 `{ "results": [...], "next_cursor": ... }`。

## 環境設定

```bash
export TODOIST_API_TOKEN="your_api_token"
```

Token 取得：https://todoist.com/app/settings/integrations/developer

## 快速使用（curl，推薦）

### 查詢僅今日待辦（預設）

```bash
curl -s "https://api.todoist.com/api/v1/tasks?filter=today" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```

> **注意**：預設僅查詢今日任務，不含過期任務，避免重複執行。

### 自訂過濾器

```bash
# 今日 + 過期（如需包含過期任務）
curl -s "https://api.todoist.com/api/v1/tasks?filter=today%20%7C%20overdue" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"

# 未來 7 天
curl -s "https://api.todoist.com/api/v1/tasks?filter=7%20days" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```

> 過濾器需 URL encode：`today | overdue` → `today%20%7C%20overdue`

### 新增任務

> **Windows 注意**：POST 請求的 inline JSON（`-d '{...}'`）在 Windows Bash 會失敗（error_code 42），
> 必須先用 Write 工具建立 JSON 檔案，再用 `-d @file.json` 發送。GET 查詢不受影響。

**Windows 環境（推薦）：**
```bash
# 步驟 1：用 Write 工具建立 JSON 檔案（例如 task.json）
# {"content":"完成報告","due_string":"tomorrow","priority":4}

# 步驟 2：用 curl 發送
curl -s -X POST "https://api.todoist.com/api/v1/tasks" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @task.json

# 步驟 3：刪除暫存檔
rm task.json
```

**macOS/Linux 環境：**
```bash
curl -s -X POST "https://api.todoist.com/api/v1/tasks" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"完成報告","due_string":"tomorrow","priority":4}'
```

### 完成任務

```bash
curl -s -X POST "https://api.todoist.com/api/v1/tasks/TASK_ID/close" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```

### 新增任務評論

> **Windows 注意**：POST 請求必須用 Write 工具建立 JSON 檔案，再用 `-d @file.json` 發送。

```bash
# 步驟 1：用 Write 工具建立 comment.json
# {"task_id":"TASK_ID","content":"評論內容"}

# 步驟 2：發送
curl -s -X POST "https://api.todoist.com/api/v1/comments" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @comment.json

# 步驟 3：刪除暫存檔
rm comment.json
```

### 更新任務（優先級、截止日期等）

> 用於失敗處理：降低優先級、重新排程到明天。

```bash
# 步驟 1：用 Write 工具建立 update.json
# 降低優先級：{"priority": 3}
# 重新排程：{"due_string": "tomorrow"}
# 同時修改：{"priority": 3, "due_string": "tomorrow"}

# 步驟 2：發送
curl -s -X POST "https://api.todoist.com/api/v1/tasks/TASK_ID" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @update.json

# 步驟 3：刪除暫存檔
rm update.json
```

---

## API 使用（Python）

```python
import os
import requests

TOKEN = os.environ["TODOIST_API_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# 查詢任務（注意：回應格式為 { "results": [...], "next_cursor": ... }）
def get_tasks(filter_query="today"):
    response = requests.get(
        "https://api.todoist.com/api/v1/tasks",
        headers=HEADERS,
        params={"filter": filter_query}
    )
    data = response.json()
    return data.get("results", [])

# 新增任務
def add_task(content, due_string=None, priority=1):
    data = {"content": content}
    if due_string:
        data["due_string"] = due_string
    if priority:
        data["priority"] = priority  # 4=p1最高, 1=p4最低

    response = requests.post(
        "https://api.todoist.com/api/v1/tasks",
        headers=HEADERS,
        json=data
    )
    return response.json()

# 完成任務
def complete_task(task_id):
    requests.post(
        f"https://api.todoist.com/api/v1/tasks/{task_id}/close",
        headers=HEADERS
    )
```

## 過濾器語法

| 過濾器 | 說明 |
|--------|------|
| `today` | 今日任務 |
| `tomorrow` | 明日任務 |
| `overdue` | 過期任務 |
| `7 days` | 未來 7 天 |
| `no date` | 無日期任務 |
| `p1`, `p2`, `p3`, `p4` | 按優先級 |
| `#專案名稱` | 特定專案 |
| `@標籤` | 特定標籤 |
| `assigned to: me` | 指派給我 |

組合：`today | overdue`（或）、`#工作 & p1`（且）

## 優先級對應

| API 值 | 顯示 | Emoji | 說明 |
|--------|------|-------|------|
| 4 | p1 | 🔴 | 最高優先級 |
| 3 | p2 | 🟡 | 高優先級 |
| 2 | p3 | 🔵 | 中優先級 |
| 1 | p4 | ⚪ | 低優先級 |

## 回應格式

### 列表查詢回應（GET /tasks）

```json
{
  "results": [ ...任務物件陣列... ],
  "next_cursor": null
}
```

> **重要**：任務列表在 `results` 欄位內，不是直接回傳陣列。使用 `jq '.results'` 或 `data["results"]` 取出。

### 任務物件結構

```json
{
  "id": "6fv24RhCvXv9hcvX",
  "content": "任務標題",
  "description": "任務描述",
  "project_id": "6Hc6Wfh53pQwCpH5",
  "priority": 4,
  "due": {
    "date": "2026-02-12",
    "timezone": null,
    "string": "today",
    "lang": "en",
    "is_recurring": false
  },
  "labels": ["工作", "重要"],
  "checked": false
}
```

> **注意**：Task ID 格式從純數字改為英數混合字串。

## 格式化輸出

```python
def format_tasks(tasks):
    EMOJI = {4: "🔴", 3: "🟡", 2: "🔵", 1: "⚪"}
    lines = []
    
    for task in sorted(tasks, key=lambda x: x.get("priority", 1), reverse=True):
        emoji = EMOJI.get(task.get("priority", 1), "⚪")
        content = task.get("content", "")
        
        # 檢查過期
        due = task.get("due", {})
        overdue = ""
        if due and due.get("date"):
            from datetime import datetime
            due_date = datetime.strptime(due["date"][:10], "%Y-%m-%d").date()
            if due_date < datetime.now().date():
                overdue = " ⏰(過期!)"
        
        lines.append(f"{emoji} {content}{overdue}")
    
    return "\n".join(lines)
```

## 錯誤處理

| 狀態碼 | 原因 | 解決方案 |
|--------|------|---------|
| 401 | Token 無效 | 檢查 TODOIST_API_TOKEN |
| 403 | 權限不足 | 確認 Token 權限 |
| 404 | 任務不存在 | 確認 task_id |
| 429 | 請求過多 | 等待後重試（限制 450/15min） |

## 參考資料

- 完整 API 文件：`references/api_reference.md`
- 過濾器語法：`references/filter_syntax.md`
