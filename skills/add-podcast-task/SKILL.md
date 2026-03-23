---
name: "add-podcast-task"
version: "1.0.1"
description: |
  新增一條 Todoist 輪轉 Podcast 自動任務時的完整檢核：在 auto-task-creator 六步之外，
  補齊 config/podcast.yaml 節目名、auto-task 模板中的 ntfy 標題契約、resolve_podcast_series.py／腳本對齊與驗證清單。
  Use when: 新增 Podcast 製作相關自動任務時，需要確保節目名稱、ntfy 標題、模板契約與腳本對齊。
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
cache-ttl: N/A
depends-on:
  - skills/auto-task-creator/SKILL.md
  - skills/ntfy-notify/SKILL.md
  - skills/knowledge-query/SKILL.md
  - config/podcast.yaml
triggers:
  - "新增podcast任務"
  - "新增 podcast 任務"
  - "add podcast task"
  - "建立 podcast 自動任務"
  - "podcast 自動任務"
  - "add-podcast-task"
---

# add-podcast-task Skill（新增 Podcast 自動任務）

## 用途

當要在本專案新增**與現有 `podcast_create` / `podcast_jiaoguangzong` 同級**的 Podcast 製作自動任務時，依本 Skill 執行。  
**一般自動任務**的 `task_key`、frequency、timeout、PS1 fallback 等，仍須先遵守 **`auto-task-creator`**；本 Skill 只補 **Podcast 管線專屬**步驟，避免 ntfy 標題與實際節目／slug 不符。

---

## 觸發時機

使用者或 Agent 說「新增 Podcast 任務」「建立 podcast 自動任務」「add podcast task」等時，**先讀** `skills/auto-task-creator/SKILL.md` 與本檔，再動手改檔。

---

## Phase 1：通用自動任務（必做）

依 **`skills/auto-task-creator/SKILL.md`** 完成全流程，並確保：

| 項目 | 規則（與 CLAUDE.md 一致） |
|------|---------------------------|
| `task_key` | **僅底線**，如 `podcast_my_series` |
| 檔名 | `prompts/team/todoist-auto-{task_key}.md`、`results/todoist-auto-{task_key}.json` |
| `config/frequency-limits.yaml` | `initial_schema` 計數欄、`task_rules` 後端、`tasks.{task_key}`（含 `template` 指向 team prompt） |
| `config/timeouts.yaml` | `phase2_timeout_by_task.{task_key}`（Podcast 含 TTS／合併／R2 者常為 2400–4000s） |
| `run-todoist-agent-team.ps1` | 若 timeout 較長，同步 `$AutoTaskTimeoutOverride` fallback |

---

## Phase 2：節目顯示名（ntfy 名實相符）

1. **Read** `config/podcast.yaml`。
2. 在 `notification.series_by_task` **新增一列**：

```yaml
  series_by_task:
    # ...既有鍵...
    {task_key}: "{節目顯示名稱}"
```

- `{節目顯示名稱}` = 推播標題上的品牌（例：**淨土學苑**、**知識電台**），**不要**拿 KB hybrid 查詢關鍵字硬當節目名。
- 若任務走「無 task_key 的純腳本」且依 **slug 前綴**判斷節目，須同步改 **`tools/resolve_podcast_series.py`**（在 `resolve()` 內為該前綴分支回傳對應 `series_by_task` 值，並維持 `--task {task_key}` 可查表）。

3. 確認 **`skills/ntfy-notify/SKILL.md`** 中「Podcast 類任務：標題節目名稱」一節仍與本設定一致。

---

## Phase 3：Auto-task 模板（`templates/auto-tasks/`）

1. 新增或複製 **`templates/auto-tasks/podcast-{task_key}.md`**（檔名慣例：`podcast-` 前綴 + `task_key`，全小寫與底線）。
2. 模板**必須**包含與現行專案一致的兩塊契約（可從 `podcast-create.md` / `podcast-jiaoguangzong.md` 複製後改寫）：
   - **任務識別與 ntfy 節目名稱**：寫明本任務的 `task_key`、`series_display_name` 來自 `config/podcast.yaml` 的哪個鍵、**標題格式** `🎙️ {series_display_name} Podcast：{本集短標題}`。
   - **步驟 ntfy**：依 `ntfy-notify` Skill，`title` 使用上一行的格式，**不得**寫死錯誤節目名。
3. 其餘流程（選材、Deep Research、JSONL、TTS、`upload-podcast.ps1`、`podcast-history.json`）依該管線需求從既有模板嫁接。

---

## Phase 4：Team Prompt（`prompts/team/todoist-auto-{task_key}.md`）

1. `allowed_tools`／步驟中要求 Agent **Read** `templates/auto-tasks/podcast-{task_key}.md` 並嚴格依流程執行。
2. `in_progress` 結果 JSON 的 `summary` 字串應帶 **節目顯示名** + `task_key`（與 `series_by_task` 語意一致，避免仍寫舊的泛稱）。
3. 必讀清單須含 **`skills/ntfy-notify/SKILL.md`**；若會動 KB，含 **`skills/knowledge-query/SKILL.md`**。

---

## Phase 5：腳本化管線（若適用）

| 情境 | 動作 |
|------|------|
| 類似 **`tools/run_podcast_create.py`** | 以 `yaml.safe_load` 讀 `config/podcast.yaml`，用 `notification.series_by_task.{task_key}` 組 ntfy `title`，格式與模板相同。 |
| 類似 **`tools/article-to-podcast.ps1`** | 支援 `-SeriesDisplayName`；未傳時由 **`tools/resolve_podcast_series.py --task {task_key}` 或 `--slug`** 解析。排程若 slug 無法分辨節目（例：僅 `note-*`），**呼叫端必須傳 `-SeriesDisplayName`**（見 `run-podcast-latest-buddhist.ps1`）。 |

新增解析規則時，**同步**更新 `resolve_podcast_series.py` 的 docstring 與本 Skill 的 Phase 2 說明。

---

## Phase 6：驗證 Checklist（Podcast 加驗）

完成 Phase 1–5 後執行：

| # | 項目 | 驗證 |
|---|------|------|
| P1 | `series_by_task` 含 `{task_key}` | `grep "{task_key}" config/podcast.yaml` |
| P2 | 模板含「任務識別」與 ntfy 標題格式 | `grep -E "series_display_name|🎙️" templates/auto-tasks/podcast-{task_key}.md` |
| P3 | Team prompt 指向該模板 | `grep "templates/auto-tasks/podcast-{task_key}" prompts/team/todoist-auto-{task_key}.md` |
| P4 | Resolver 可查 task | `uv run python tools/resolve_podcast_series.py --task {task_key}` 輸出為預期節目名 |
| P5 | 與 auto-task-creator 六步一致 | 再跑 auto-task-creator 的驗證表（grep 結果檔、`agent` 欄位底線） |

---

## 與既有任務的對照

| task_key | 模板檔 | series_by_task 鍵 |
|----------|--------|-------------------|
| `podcast_create` | `templates/auto-tasks/podcast-create.md` | `podcast_create` → 知識電台（預設） |
| `podcast_jiaoguangzong` | `templates/auto-tasks/podcast-jiaoguangzong.md` | `podcast_jiaoguangzong` → 淨土學苑 |

新增任務時複製最接近的一條管線，再改 `task_key`、選材邏輯與 `series_by_task` 顯示名。

---

## 常見錯誤

| 錯誤 | 正確做法 |
|------|----------|
| ntfy 標題寫「教觀綱宗 Podcast」但 slug／品牌為淨土學苑 | 標題節目名只來自 `series_by_task`，KB 關鍵字只用於搜尋／metadata |
| 只加 frequency-limits，未加 `series_by_task` | Phase 2 必做 |
| 腳本硬編碼節目名 | 改為讀 `podcast.yaml` 或呼叫 `resolve_podcast_series.py` |
| `task_key` 含連字號 | 遵守 CLAUDE.md，一律底線 |

---

## 參考路徑（專案內）

- `config/podcast.yaml` — `notification.series_by_task`、`series_default`
- `tools/resolve_podcast_series.py`
- `templates/auto-tasks/podcast-create.md`、`podcast-jiaoguangzong.md`
- `prompts/team/todoist-auto-podcast_create.md`、`todoist-auto-podcast_jiaoguangzong.md`
- `tools/run_podcast_create.py`、`tools/article-to-podcast.ps1`、`run-podcast-latest-buddhist.ps1`
