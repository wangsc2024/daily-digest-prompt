# Phase 結果檔案 Schema 規範

> **版本**：schema_version = 1
> **最後更新**：2026-02-28
> **用途**：定義 Todoist 與每日摘要 Agent 團隊模式中所有 `results/*.json` 中間結果檔案的格式，作為 Phase 1 → Phase 2 → Phase 3 之間的介面契約。

---

## 1. 總覽：所有結果檔案一覽

| 檔案路徑 | 產出方 | 消費方 | 用途 |
|---------|-------|-------|------|
| `results/todoist-plan.json` | Phase 1 (todoist-query) | Phase 2 + Phase 3 (assemble) | 執行計畫與路由決策 |
| `results/todoist-task-{rank}.md` | Phase 1 (todoist-query) | Phase 2 各任務 Agent | 子 Agent prompt 檔案 |
| `results/todoist-result-{rank}.json` | Phase 2 各任務 Agent | Phase 3 (assemble) | Todoist 任務執行結果 |
| `results/todoist-auto-{key}.json` | Phase 2 各自動任務 Agent | Phase 3 (assemble) | 自動任務執行結果 |
| `results/todoist.json` | Phase 1 (fetch-todoist) | Phase 2 (assemble-digest) | Todoist 資料擷取結果 |
| `results/news.json` | Phase 1 (fetch-news) | Phase 2 (assemble-digest) | 屏東新聞擷取結果 |
| `results/hackernews.json` | Phase 1 (fetch-hackernews) | Phase 2 (assemble-digest) | HN AI 文章擷取結果 |
| `results/gmail.json` | Phase 1 (fetch-gmail) | Phase 2 (assemble-digest) | Gmail 郵件擷取結果 |
| `results/security.json` | Phase 1 (fetch-security) | Phase 2 (assemble-digest) | Skill 安全掃描結果 |

**生命週期**：所有結果檔案在 Phase 3 完成後由 todoist-assemble Agent 或 run-*-team.ps1 腳本清理。

---

## 2. todoist-plan.json Schema

Phase 1 的 `todoist-query` Agent 寫入，Phase 2 和 Phase 3 均依賴此檔案決策。

### 共用欄位

| 欄位 | 類型 | 說明 |
|-----|------|------|
| `agent` | string | 固定值 `"todoist-query"` |
| `status` | string | `"success"` 或 `"failed"` |
| `fetched_at` | string | ISO 8601 UTC 時間戳（`date -u +%Y-%m-%dT%H:%M:%S` 取得） |
| `plan_type` | string | 三種之一：`"tasks"` / `"auto"` / `"idle"` |
| `tasks` | array | 可處理的 Todoist 任務（`plan_type=auto/idle` 時為空陣列） |
| `auto_tasks` | object or null | 自動任務計畫（`plan_type=tasks` 時為 null） |
| `filter_summary` | object | 篩選各階段統計數 |
| `skipped_tasks` | array | 被跳過的任務列表（含跳過原因） |
| `sync_warnings` | object | 未匹配標籤警告 |
| `skills_used` | array | 本次使用的 Skill 列表 |
| `error` | string or null | 錯誤訊息（正常時為 null） |

### plan_type = "tasks"

有可處理的 Todoist 待辦時，`tasks` 陣列包含已路由、計分、排序的任務：

```json
{
  "agent": "todoist-query",
  "status": "success",
  "fetched_at": "2026-02-28T00:30:00",
  "plan_type": "tasks",
  "tasks": [
    {
      "rank": 1,
      "task_id": "abc123",
      "content": "任務名稱",
      "priority": 4,
      "tier": 1,
      "confidence": 100,
      "score": 4.8,
      "matched_skills": ["todoist", "knowledge-query"],
      "allowed_tools": "Read,Bash,Write",
      "prompt_file": "results/todoist-task-1.md"
    }
  ],
  "auto_tasks": null,
  "filter_summary": {
    "api_total": 10,
    "after_date_filter": 8,
    "not_yet_due": 2,
    "after_time_filter": 6,
    "after_closed_filter": 5,
    "processable": 2,
    "skipped": 3
  },
  "skipped_tasks": [
    { "task_id": "xyz", "content": "跳過的任務", "reason": "實體行動" }
  ],
  "sync_warnings": { "unmatched_labels": [], "suggestion": null },
  "skills_used": ["todoist", "api-cache"],
  "error": null
}
```

### plan_type = "auto"

無可處理 Todoist 任務，改觸發自動任務輪轉。`selected_tasks` 由 round-robin 演算法選出（1-4 個）：

```json
{
  "agent": "todoist-query",
  "status": "success",
  "fetched_at": "2026-02-28T00:30:00",
  "plan_type": "auto",
  "tasks": [],
  "auto_tasks": {
    "selected_tasks": [
      {
        "key": "shurangama",
        "name": "楞嚴經研究",
        "current_count": 1,
        "limit": 5,
        "execution_order": 1,
        "prompt_file": "prompts/team/todoist-auto-shurangama.md"
      }
    ],
    "next_execution_order_after": 2,
    "all_exhausted": false,
    "summary": {
      "total_limit": 45,
      "total_used": 5,
      "remaining": 40,
      "selected_count": 1,
      "max_per_run": 4
    }
  },
  "filter_summary": { "api_total": 5, "after_date_filter": 3, "after_closed_filter": 0, "processable": 0, "skipped": 3 },
  "sync_warnings": { "unmatched_labels": [], "suggestion": null },
  "skipped_tasks": [],
  "skills_used": ["todoist", "api-cache"],
  "error": null
}
```

**重要**：`key` 欄位的值（底線命名，如 `tech_research`）必須與 `config/frequency-limits.yaml` 的 task key 一致，且對應 prompt 檔案命名規則為 `prompts/team/todoist-auto-{key}.md`。

### plan_type = "idle"

今日所有自動任務均已達上限（total_used >= total_limit）：

```json
{
  "plan_type": "idle",
  "tasks": [],
  "auto_tasks": {
    "selected_tasks": [],
    "next_execution_order_after": null,
    "all_exhausted": true,
    "summary": { "total_limit": 45, "total_used": 45, "remaining": 0, "selected_count": 0, "max_per_run": 4 }
  }
}
```

---

## 3. results/fetch-*.json Schema（每日摘要 Phase 1）

每日摘要 Phase 1 各擷取 Agent 的輸出格式。共用欄位：

| 欄位 | 類型 | 說明 |
|-----|------|------|
| `agent` | string | Agent 識別名稱（如 `"fetch-todoist"`） |
| `status` | string | `"success"` 或 `"failed"` |
| `source` | string | `"api"` / `"cache"` / `"cache_degraded"` / `"failed"` |
| `fetched_at` | string | ISO 8601 UTC 時間戳 |
| `skills_used` | array | 使用的 Skill 列表 |
| `data` | object | 實際資料（結構依 Agent 不同） |
| `error` | string or null | 錯誤訊息 |

### results/todoist.json

```json
{
  "agent": "fetch-todoist",
  "status": "success",
  "source": "api",
  "fetched_at": "2026-02-28T00:30:00",
  "skills_used": ["todoist", "api-cache"],
  "data": { "tasks": [ /* Todoist API 回傳的完整任務陣列 */ ] },
  "error": null
}
```

### results/news.json

```json
{
  "agent": "fetch-news",
  "status": "success",
  "source": "api",
  "fetched_at": "2026-02-28T00:30:00",
  "retry_count": 0,
  "skills_used": ["pingtung-news", "api-cache"],
  "data": {
    "news": [
      { "title": "新聞標題", "date": "2026-02-28", "url": "https://...", "summary": "摘要" }
    ]
  },
  "error": null
}
```

### results/hackernews.json

```json
{
  "agent": "fetch-hackernews",
  "status": "success",
  "source": "api",
  "fetched_at": "2026-02-28T00:30:00",
  "skills_used": ["hackernews-ai-digest", "api-cache"],
  "data": {
    "articles": [
      { "id": 12345678, "title_en": "原始英文標題", "title_zh": "正體中文標題", "url": "https://...", "score": 256, "comments": 128 }
    ],
    "scanned_count": 30,
    "matched_count": 5
  },
  "error": null
}
```

### results/gmail.json

```json
{
  "agent": "fetch-gmail",
  "status": "success",
  "source": "api",
  "fetched_at": "2026-02-28T00:30:00",
  "skills_used": ["gmail", "api-cache"],
  "data": { "emails": [ /* 郵件陣列 */ ], "total_count": 10, "important_count": 2 },
  "error": null
}
```

### results/security.json

```json
{
  "agent": "fetch-security",
  "status": "success",
  "fetched_at": "2026-02-28T00:30:00",
  "skills_used": ["skill-scanner"],
  "data": {
    "skills_scanned": 23,
    "safe_skills": 21,
    "findings": { "critical": 0, "high": 0, "medium": 2, "low": 0, "info": 14 },
    "has_critical_or_high": false,
    "per_skill": [
      { "name": "todoist", "is_safe": true, "max_severity": "MEDIUM", "findings_count": 3 }
    ]
  },
  "error": null
}
```

---

## 4. results/todoist-auto-{key}.json Schema（Todoist 自動任務）

Phase 2 各自動任務 Agent 的輸出。檔名中的 `{key}` 必須與 `config/frequency-limits.yaml` 的 task key 完全一致（底線命名，如 `shurangama`、`tech_research`、`git_push`）。

### 共用欄位

| 欄位 | 類型 | 說明 |
|-----|------|------|
| `agent` | string | `"todoist-auto-{key}"` 或 `"todoist-{key}"` |
| `status` | string | `"success"` / `"partial"` / `"failed"` / `"no_changes"` |
| `task_id` | null | 自動任務無 Todoist task_id，固定為 null |
| `type` | string | 任務類型 key（如 `"shurangama"`、`"log_audit"`、`"git_push"`） |
| `duration_seconds` | number | 執行耗時（秒），填 0 由 PowerShell 外部計算 |
| `done_cert` | object | 品質認證物件（見下方） |
| `summary` | string | 一句話執行摘要 |
| `error` | string or null | 錯誤訊息 |

**done_cert 結構**：
```json
{ "status": "DONE", "quality_score": 4, "remaining_issues": [] }
```
- `status`：`"DONE"` / `"PARTIAL"` / `"FAILED"`
- `quality_score`：1-5 的整數

### 研究類自動任務範例（shurangama、tech_research 等）

```json
{
  "agent": "todoist-auto-shurangama",
  "status": "success",
  "task_id": null,
  "type": "shurangama",
  "topic": "楞嚴經三科七大義理解析",
  "kb_imported": true,
  "duration_seconds": 0,
  "done_cert": { "status": "DONE", "quality_score": 4, "remaining_issues": [] },
  "summary": "完成楞嚴經三科七大研究，已匯入知識庫",
  "error": null
}
```

### 系統維護類範例（log_audit）

```json
{
  "agent": "todoist-logaudit",
  "status": "success",
  "task_id": null,
  "type": "log_audit",
  "findings_count": 3,
  "fixes_count": 2,
  "kb_imported": true,
  "duration_seconds": 0,
  "done_cert": { "status": "DONE", "quality_score": 4, "remaining_issues": [] },
  "summary": "發現 3 個問題，修正 2 個",
  "error": null
}
```

### Git 推送類範例（git_push）

檔案名稱：`results/todoist-auto-gitpush.json`（注意：key 為 `gitpush`，非 `git_push`）

```json
{
  "agent": "todoist-gitpush",
  "status": "success",
  "task_id": null,
  "type": "git_push",
  "knowledge_sync": {
    "status": "success",
    "new_articles": 3,
    "updated_articles": 1,
    "pushed": true,
    "privacy_warnings": 0,
    "privacy_warning_detail": null
  },
  "commit_hash": "abc1234",
  "files_changed": 3,
  "duration_seconds": 0,
  "summary": "知識庫同步 +3 篇，已推送兩個 repo",
  "error": null
}
```

**Fail-Safe 機制**：部分 Agent（如 `log_audit`）在啟動後立即寫入 `status="failed"` 的佔位結果，成功完成後才覆寫為 `status="success"`。Phase 3 必須以最終讀取到的 JSON 為準。

---

## 5. results/todoist-result-{rank}.json Schema（Todoist 任務執行）

`plan_type = "tasks"` 時，Phase 2 各子 Agent 的輸出。`{rank}` 對應 `todoist-plan.json` 中 `tasks[].rank` 欄位（從 1 開始）。

```json
{
  "agent": "todoist-task-1",
  "status": "success",
  "task_id": "abc123",
  "type": "todoist_task",
  "content": "Todoist 任務名稱",
  "duration_seconds": 0,
  "done_cert": { "status": "DONE", "quality_score": 4, "remaining_issues": [] },
  "summary": "一句話執行摘要",
  "error": null
}
```

| 欄位 | 類型 | 說明 |
|-----|------|------|
| `agent` | string | `"todoist-task-{rank}"` |
| `status` | string | `"success"` / `"partial"` / `"failed"` |
| `task_id` | string | 對應的 Todoist Task ID（英數混合格式） |
| `type` | string | 固定值 `"todoist_task"` |
| `content` | string | Todoist 任務名稱（原文） |

---

## 6. Phase 3 容錯規則

Phase 3 (`todoist-assemble`) 在讀取結果檔案時必須遵循以下容錯規則：

### 6.1 結果檔案缺失

| 情境 | 處理方式 |
|-----|---------|
| `results/todoist-plan.json` 不存在 | Phase 3 直接結束，記錄錯誤到通知 |
| `results/todoist-result-{rank}.json` 不存在 | 標記該任務為 `failed`，不關閉 Todoist 任務 |
| `results/todoist-auto-{key}.json` 不存在 | 從 `todoist-plan.json` 的 `auto_tasks.selected_tasks` 推斷預期 key，標記為 `failed` |

### 6.2 狀態判斷規則

- `status = "success"` → 關閉 Todoist 任務（僅 `plan_type=tasks`），更新頻率計數
- `status = "partial"` → 不關閉，附加部分完成評論，降低優先級
- `status = "failed"` → 不關閉，附加失敗評論，依 `is_recurring` 決定處理方式
- `status = "no_changes"` → 視同 success，不需關閉 Todoist 任務

### 6.3 key 正規化

Phase 1 輸出的 `key` 欄位可能含連字號（如 `tech-research`）或底線（如 `tech_research`）。Phase 2 和 Phase 3 均以**底線格式為準**進行正規化比對（將 `-` 替換為 `_`）。

### 6.4 write_version 樂觀鎖

更新 `context/auto-tasks-today.json` 時，若偵測到 `write_version` 不一致（並行競態），以**最大值合併**各計數欄位後遞增版本號。

---

## 7. schema_version 追蹤

各結果檔案目前**不含** `schema_version` 欄位（版本由本規格文件統一管理）。若未來格式有 breaking change，需在以下位置同步更新：

1. 本文件（`specs/interface-spec/phase-results.md`）版本號
2. `run-todoist-agent-team.ps1` 中的解析邏輯
3. `prompts/team/todoist-query.md` 的結果格式指示
4. `prompts/team/todoist-assemble.md` 的讀取指示

**本規範版本**：`schema_version = 1`，對應專案 commit 68d87d1 及之後的架構。
