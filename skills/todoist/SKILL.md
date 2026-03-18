---
name: todoist
version: "2.1.0"
description: |
  Todoist 待辦事項整合 - 查詢、新增、完成、刪除任務。支援專案、標籤、優先級、截止日期等完整功能。
  Use when: 管理待辦事項、查詢今日任務、新增刪除任務、過濾優先級、Claude Chat 快速指派任務。
allowed-tools: Bash, Read, Write
cache-ttl: 30min
depends-on:
  - config/dependencies.yaml
triggers:
  - "todoist"
  - "待辦事項"
  - "todo"
  - "任務"
  - "今日任務"
  - "過期任務"
  - "新增任務"
  - "完成任務"
  - "指派任務"
  - "幫我新增"
  - "加一個任務"
  - "排進待辦"
  - "task"
  - "to-do list"
  - "待辦清單"
  - "to-do"
  - "待辦"
---

# Todoist 待辦事項整合

---

## Claude Chat 快速指派（互動模式）

> 在 Claude Chat 中說「新增任務」、「指派任務」或「幫我加一個待辦」時，
> 依照以下步驟從自然語言解析並直接寫入 Todoist。

### 步驟 1：解析意圖

從使用者的自然語言提取以下欄位：

| 欄位 | 自然語言線索 | 預設值 |
|------|------------|--------|
| `content` | 任務名稱（必填） | — |
| `due_string` | 時間詞（今天/明天/下週一/每天早上10點/本週五） | 不填（無截止日） |
| `priority` | 優先級詞（緊急/重要/p1/p2/一般） | `1`（p4） |
| `labels` | 標籤（工作/研究/知識庫/個人） | `[]` |
| `description` | 任務說明、備註 | 不填 |

**優先級關鍵字對照**：
- `緊急`、`p1`、`最高` → `4`
- `重要`、`高優先`、`p2` → `3`
- `一般`、`p3` → `2`
- 無特別說明 → `1`

**時間詞對照**（中文 → due_string）：
- 今天 → `today`
- 明天 → `tomorrow`
- 後天 → `in 2 days`
- 下週一 → `next monday`
- 每天 → `every day`
- 每週一 → `every monday`
- 本週五 / 這週五 → `this friday`
- 月底 → `last day of the month`

### 步驟 2：確認（若資訊不足）

若使用者說「新增一個任務」但**沒提供任務名稱**，直接詢問：
> 「請告訴我任務名稱（以及截止日期、優先級，可省略）」

若資訊齊全，**不需確認，直接建立**。

### 步驟 3：建立任務

1. 用 Write 工具建立 `tmp/task_add.json`，內容為任務 JSON
2. 執行 pwsh 呼叫 API
3. 刪除 `tmp/task_add.json`
4. 輸出確認訊息

**task_add.json 範例**：
```json
{
  "content": "完成季報初稿",
  "due_string": "tomorrow",
  "priority": 3,
  "labels": ["工作"]
}
```

**pwsh 呼叫**：
```bash
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
Invoke-RestMethod "https://api.todoist.com/api/v1/tasks" -Method Post `
  -Headers @{Authorization="Bearer $t"; "Content-Type"="application/json; charset=utf-8"} `
  -Body (Get-Content "tmp/task_add.json" -Raw) | ConvertTo-Json -Depth 5'
```

### 步驟 4：輸出確認訊息

```
✅ 已指派任務到 Todoist

📌 任務：{content}
📅 截止：{due_string 或 "無截止日"}
🔴/🟡/🔵/⚪ 優先級：{p1/p2/p3/p4}
🏷️ 標籤：{labels 或 "無"}
🆔 ID：{task.id}
```

---

### 常見指派範例

| 使用者說 | 解析結果 |
|---------|---------|
| `新增任務：明天早上寫週報` | content="明天早上寫週報", due_string="tomorrow" |
| `幫我加一個今天要完成的緊急任務：修復登入 Bug` | content="修復登入 Bug", due="today", priority=4 |
| `排進待辦：每週一開週會，標籤工作` | content="開週會", due="every monday", labels=["工作"] |
| `新增任務：研究 LLM Router，加到知識庫研究標籤` | content="研究 LLM Router", labels=["研究","知識庫"] |
| `加一個本週五截止的 p2 任務：提交費用報銷` | content="提交費用報銷", due="this friday", priority=3 |

---

### 禁止行為

- **禁止**在沒有任務名稱時自行假設內容
- **禁止**用 `echo $TOKEN` 或子 shell 讀取 token（Harness 攔截）
- **禁止**省略 `rm tmp/task_add.json` 清理步驟
- **禁止**在週期性任務上設定 `due_string`（會清除週期設定）
- **禁止**在 Bash inline 用 `-d '{...}'` 傳 POST body（Windows 下會失敗）

---

## 依賴注入（DI）

> 端點來源：`config/dependencies.yaml` → `skills.todoist`（ADR-001 Phase 3）
> 執行前讀取 YAML 取得 `base_url`；若 YAML 不可讀則 fallback 使用下方預設值。
>
> **讀取片段**（在每個需要呼叫 API 的步驟開頭執行）：
> ```bash
> BASE=$(uv run python -X utf8 -c "import yaml; d=yaml.safe_load(open('config/dependencies.yaml')); print(d['skills']['todoist']['api']['base_url'])" 2>/dev/null || echo "https://api.todoist.com/api/v1")
> ```

透過 Todoist API v1（`/api/v1/`）管理任務。

> **注意**：舊版 REST API v2（`/rest/v2/`）已於 2026 年棄用（回傳 410 Gone）。
> 所有端點已遷移至 `/api/v1/`。回應格式從直接陣列改為 `{ "results": [...], "next_cursor": ... }`。

## 環境設定

> **Windows 注意**：`$TODOIST_API_TOKEN` 不會自動注入 Bash 環境，必須透過 PowerShell 讀取 `.env` 再呼叫 API。
> **禁止使用** `echo $TOKEN`、`$(cat .env | grep TOKEN)` 等方式——會被 Harness 攔截。

### 正確做法（必守）

| 做法 | 說明 |
|------|------|
| **pwsh -Command** | 使用本 SKILL 內所有「pwsh -Command」片段：先 `$env:TODOIST_API_TOKEN` 或 `Get-Content .env` 讀 token，再 `Invoke-RestMethod`。 |
| **Python** | 使用 `os.environ["TODOIST_API_TOKEN"]` 或 `python-dotenv` 載入後再呼叫 API（見下方 API 使用（Python））。 |
| **專案腳本** | 可呼叫 `skills/todoist/scripts/todoist.py`（會從環境變數讀 token）。 |

### 禁止做法（會被 Harness 攔截）

- **禁止** 在 Bash 內用 `curl -H "Authorization: Bearer $(cat .env \| grep ...)"` 或 `` `cat .env \| grep ...` `` 等子 shell 讀取 .env 後傳給 curl。
- **禁止** 任何 `$(...)` / 反引號 讀取 `.env`、`token.json`、`credentials` 等敏感檔並送入 curl/wget。

Token 取得：https://todoist.com/app/settings/integrations/developer

### Token 載入片段（所有 pwsh 呼叫共用）

```powershell
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
```

## 快速使用（Windows pwsh，推薦）

### 查詢今日 + 過期待辦（預設，推薦）

```bash
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
$r = Invoke-RestMethod "https://api.todoist.com/api/v1/tasks/filter?query=today%20%7C%20overdue" -Headers @{Authorization="Bearer $t"}
$r | ConvertTo-Json -Depth 10'
```

> **注意**：預設查詢今日 + 過期任務，確保昨日未執行的任務不被遺漏。
> 重複執行防護由過濾 B（`closed_task_ids`）承擔，而非限制查詢範圍。
>
> **重要**：API v1 的篩選端點為 `/tasks/filter?query=`，不是 `/tasks?filter=`。
> 後者的 `filter` 參數會被靜默忽略，回傳全部任務。

### 自訂過濾器

```bash
# 僅今日（不含過期）
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
(Invoke-RestMethod "https://api.todoist.com/api/v1/tasks/filter?query=today" -Headers @{Authorization="Bearer $t"}) | ConvertTo-Json -Depth 10'

# 未來 7 天
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
(Invoke-RestMethod "https://api.todoist.com/api/v1/tasks/filter?query=7%20days" -Headers @{Authorization="Bearer $t"}) | ConvertTo-Json -Depth 10'
```

> 過濾器需 URL encode：`today | overdue` → `today%20%7C%20overdue`

### 新增任務

步驟 1：用 Write 工具建立 `task.json`（例如 `{"content":"完成報告","due_string":"tomorrow","priority":4}`）

步驟 2：用 pwsh 發送：
```bash
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
Invoke-RestMethod "https://api.todoist.com/api/v1/tasks" -Method Post `
  -Headers @{Authorization="Bearer $t"; "Content-Type"="application/json; charset=utf-8"} `
  -Body (Get-Content "task.json" -Raw) | ConvertTo-Json -Depth 10'
```

步驟 3：`rm task.json`

### 完成任務

```bash
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
Invoke-RestMethod "https://api.todoist.com/api/v1/tasks/TASK_ID/close" -Method Post -Headers @{Authorization="Bearer $t"}'
```

### 新增任務評論

步驟 1：用 Write 工具建立 `comment.json`（例如 `{"task_id":"TASK_ID","content":"評論內容"}`）

步驟 2：用 pwsh 發送：
```bash
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
Invoke-RestMethod "https://api.todoist.com/api/v1/comments" -Method Post `
  -Headers @{Authorization="Bearer $t"; "Content-Type"="application/json; charset=utf-8"} `
  -Body (Get-Content "comment.json" -Raw)'
```

步驟 3：`rm comment.json`

### 更新任務（優先級、截止日期等）

> 用於失敗處理：降低優先級、重新排程到明天。

> ⚠️ **週期性任務保護**：若任務 `due.is_recurring = true`，**不可設定 `due_string`**。
> Todoist API 接收到 `due_string` 更新時，會清除週期性設定（`is_recurring` 變為 `false`），
> 導致任務失去週期性。週期性任務失敗時，**僅降低 `priority`，不修改 `due_string`**。

步驟 1：用 Write 工具建立 `update.json`
- 降低優先級（適用所有任務）：`{"priority": 3}`
- 重新排程（僅限非週期性任務）：`{"due_string": "tomorrow"}`
- 同時修改（僅限非週期性任務）：`{"priority": 3, "due_string": "tomorrow"}`

步驟 2：用 pwsh 發送：
```bash
pwsh -Command '
$t = if ($env:TODOIST_API_TOKEN) { $env:TODOIST_API_TOKEN } else {
  (Get-Content "D:/Source/daily-digest-prompt/.env" -EA SilentlyContinue |
   Where-Object { $_ -match "^TODOIST_API_TOKEN=" } | Select-Object -First 1) -replace "^TODOIST_API_TOKEN=",""
}
Invoke-RestMethod "https://api.todoist.com/api/v1/tasks/TASK_ID" -Method Post `
  -Headers @{Authorization="Bearer $t"; "Content-Type"="application/json; charset=utf-8"} `
  -Body (Get-Content "update.json" -Raw) | ConvertTo-Json -Depth 10'
```

步驟 3：`rm update.json`

---

## API 使用（Python）

```python
import os
import requests

TOKEN = os.environ["TODOIST_API_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# 查詢任務（注意：回應格式為 { "results": [...], "next_cursor": ... }）
# API v1 篩選端點：/tasks/filter?query=  （不是 /tasks?filter=）
def get_tasks(filter_query="today"):
    response = requests.get(
        "https://api.todoist.com/api/v1/tasks/filter",
        headers=HEADERS,
        params={"query": filter_query}
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
    "timezone": "Asia/Taipei",
    "string": "every day at 11:00",
    "lang": "zh",
    "is_recurring": true,
    "datetime": "2026-02-12T03:00:00.000000Z"
  },
  "labels": ["工作", "重要"],
  "checked": false
}
```

> **`due` 欄位說明：**
> - `datetime`：帶時間的任務才有此欄位（UTC 格式）；全天任務此欄位為 `null`。
>   例：本地 `11:00 +08:00` = `"2026-02-12T03:00:00.000000Z"`（UTC）
> - `is_recurring`：`true` = 週期性任務（完成後自動生成下一個實例）；`false` = 一次性任務
> - **時間過濾**：若 `datetime` 不為 null 且 `datetime > 當前 UTC 時間`，代表任務尚未到執行時間，應跳過此輪

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
