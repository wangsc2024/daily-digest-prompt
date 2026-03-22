---
name: "auto-task-creator"
version: "1.0.0"
description: "自動任務建立精靈：逐步引導使用者依 CLAUDE.md 的 6 步 checklist 正確新增自動任務，包含 frequency-limits.yaml、prompt 檔、timeouts.yaml、PS1 腳本，確保命名一致（底線），支援 allowed_days 星期限制設定"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
triggers:
  - "新增自動任務"
  - "add auto task"
  - "增加自動任務"
  - "auto-task-creator"
  - "建立自動任務"
  - "新自動任務"
  - "auto task checklist"
---

# auto-task-creator Skill

## 用途

引導使用者（或 Agent 自身）正確完成新增自動任務的全部步驟。
自動任務的 `task_key` 是**唯一真相來源**，6 個交付物必須命名一致。

---

## 觸發時機

使用者說「新增自動任務：XXX」或「增加一個自動任務」時啟動。

---

## Step 0：收集需求

詢問或確認以下欄位（若使用者已提供則跳過）：

| 欄位 | 說明 | 範例 |
|------|------|------|
| `task_key` | **底線命名**，與所有檔案一致 | `zen_koan` |
| `name` | 顯示名稱（日誌/通知用） | `禪宗公案推播` |
| `description` | 一句話任務目的 | `每週三/六推播一則禪宗公案` |
| `daily_limit` | 每日最多執行次數 | `1` |
| `allowed_days` | 選填，Python weekday（Mon=0…Sun=6）| `[2, 5]`（三/六） |
| `backend` | 執行後端（claude_sonnet45 / codex_exec / cursor_cli / claude_opus46） | `claude_sonnet45` |
| `timeout_seconds` | 估計執行時間（秒） | `300` |
| `skills` | 依賴的 Skill 清單 | `[ntfy-notify]` |
| `prompt_content` | Prompt 主要邏輯說明（可後續撰寫） | - |

> 若 `allowed_days` 有設定，務必在 `description` 中說明限制星期。

---

## Step 1：決定 execution_order

讀取 `config/frequency-limits.yaml`：

```bash
grep "execution_order" config/frequency-limits.yaml | sort -t: -k2 -n | tail -5
```

取目前最大值 + 1 作為新任務的 `execution_order`（停用任務 34/35 除外）。

---

## Step 2：建立 Prompt 檔案

**檔名規則**：`prompts/team/todoist-auto-{task_key}.md`（底線，絕不用連字號）

Prompt 標準結構：

```markdown
---
name: "todoist-auto-{task_key}"
template_type: "team_prompt"
version: "1.0.0"
released_at: "YYYY-MM-DD"
allowed_days: {allowed_days_list_or_remove_if_daily}
---
（角色宣告）
任務：（任務描述）
完成後將結果寫入 `results/todoist-auto-{task_key}.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

必須先讀取以下 SKILL.md：
- （skills 清單）

---

（主要步驟）

## 最後步驟：寫入結果 JSON
用 Write 覆寫 `results/todoist-auto-{task_key}.json`：
{
  "agent": "todoist-auto-{task_key}",
  "status": "success 或 partial 或 failed",
  "task_id": null,
  "type": "{task_key}",
  ...
}
```

---

## Step 3：更新 `config/frequency-limits.yaml`

需修改 **3 處**：

### 3a. `initial_schema` 段落（約第 48-78 行）

在 `"ntfy_review_count": 0,` 之後加入：

```yaml
    "{task_key}_count": 0,
```

### 3b. `task_rules` 對應後端（約第 159-197 行）

依 `backend` 欄位，在對應後端 list 加入：

```yaml
    - {task_key}   # {description}
```

### 3c. `tasks` 段落最後（最後一個任務之後）加入：

```yaml
  # --- {group_name}（{frequency_description}）---
  {task_key}:
    name: "{name}"
    daily_limit: {daily_limit}
    counter_field: "{task_key}_count"
    template: "prompts/team/todoist-auto-{task_key}.md"
    prompt_file: "prompts/team/todoist-auto-{task_key}.md"
    template_version: 1
    history_type: "{task_key}"
    execution_order: {execution_order}
    timeout_seconds: {timeout_seconds}
    result_suffix: "json"
    allowed_days: {allowed_days_or_omit}   # Mon=0,Tue=1,Wed=2,Thu=3,Fri=4,Sat=5,Sun=6
    skills: {skills_list}
    description: "{description}"
```

---

## Step 4：更新 `config/timeouts.yaml`

在 `phase2_timeout_by_task` 段落最後（`insight_briefing` 之後）加入：

```yaml
    {task_key}: {timeout_seconds}   # {description}
```

---

## Step 5：更新 `run-todoist-agent-team.ps1`（若 timeout 較長）

若 `timeout_seconds > 600`，在 `$AutoTaskTimeoutOverride` 的 hardcoded fallback 段落加入：

```powershell
    "{task_key}"   = {timeout_seconds}   # {description}
```

> 注意：`config/timeouts.yaml` 已是優先來源，此處為 fallback 值（兩者保持一致）。

---

## Step 6：驗證 Checklist

完成後逐一確認：

| # | 項目 | 驗證方式 |
|---|------|---------|
| ✅ | `frequency-limits.yaml` 新增 task_key（底線）| `grep "{task_key}" config/frequency-limits.yaml` |
| ✅ | `prompts/team/todoist-auto-{task_key}.md` 存在 | `ls prompts/team/todoist-auto-{task_key}.md` |
| ✅ | Prompt 內 `results/todoist-auto-{task_key}.json`（底線）| `grep "results/todoist-auto-" prompts/team/todoist-auto-{task_key}.md` |
| ✅ | Prompt 內 `"agent": "todoist-auto-{task_key}"`（底線）| 同上 |
| ✅ | `config/timeouts.yaml` 有對應 key | `grep "{task_key}" config/timeouts.yaml` |
| ✅ | `initial_schema` 有 `{task_key}_count` | `grep "{task_key}_count" config/frequency-limits.yaml` |

---

## allowed_days 設計說明

`allowed_days` 使用 **Python weekday 編號**（`datetime.datetime.now().weekday()`）：

| 值 | 星期 |
|----|------|
| 0  | 星期一（Mon） |
| 1  | 星期二（Tue） |
| 2  | 星期三（Wed） |
| 3  | 星期四（Thu） |
| 4  | 星期五（Fri） |
| 5  | 星期六（Sat） |
| 6  | 星期日（Sun） |

**機器強制機制**：`run-todoist-agent-team.ps1` Phase 0c 的 `is_allowed_today()` 函數會在飢餓偵測時過濾非允許日；Phase 1 LLM 讀取 `frequency-limits.yaml` 中的 `allowed_days` 欄位自行判斷是否選入本輪。

---

## 常見錯誤防範

| 錯誤 | 正確做法 |
|------|---------|
| `task_key` 用連字號（`zen-koan`）| 一律底線（`zen_koan`）|
| prompt 檔名用連字號（`todoist-auto-zen-koan.md`）| `todoist-auto-zen_koan.md` |
| `agent` 欄位不一致 | 必須 = `"todoist-auto-{task_key}"` |
| 忘記加 `initial_schema` 計數欄位 | `{task_key}_count: 0` |
| 忘記加 `task_rules` 後端對應 | 未列則預設 `cursor_cli` |
| `allowed_days` 格式錯誤 | 必須是整數 list：`[0, 3, 6]` |

---

## Podcast 自動任務

若 `task_key` 為 **Podcast 製作管線**（TTS、R2、雙主持人腳本等），在完成本 Skill 六步後，**另讀** **`skills/add-podcast-task/SKILL.md`**，補齊 `config/podcast.yaml` 的 `series_by_task`、auto-task 模板中的 ntfy 標題契約與 `resolve_podcast_series.py`／腳本對齊。
