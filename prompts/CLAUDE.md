# prompts/ 目錄局部規則

## 自動任務命名（唯一真相：config/frequency-limits.yaml）

- task_key 使用底線，禁用連字號
- 自動任務 prompt：`todoist-auto-{task_key}.md`
- 結果 JSON 路徑：`results/todoist-auto-{task_key}.json`
- 結果 JSON agent 欄位：`"todoist-auto-{task_key}"`
- 新增任務時以上四處必須一致；`validate_config.py --check-auto-tasks` 驗證

**黃金規則**：`frequency-limits.yaml` 的 key 是**唯一真相來源**，prompt 檔名、結果 JSON 檔名、`agent` 欄位三者必須完全一致（含底線）。

**新增自動任務 checklist**：
1. `config/frequency-limits.yaml` 加入 task_key（底線）
2. `prompts/team/todoist-auto-{task_key}.md`（底線）
3. Prompt 內 `results/todoist-auto-{task_key}.json`（底線）
4. Prompt 內 `"agent": "todoist-auto-{task_key}"`（底線）
5. `run-todoist-agent-team.ps1` 的 `$AutoTaskTimeoutOverride`（底線）
6. `config/timeouts.yaml` 的 `phase2_timeout_by_task`（底線）

## 結果 JSON 格式（符合 config/schemas/results-auto-task-schema.json）

- 必填：`task_key`、`status`、`agent`（或 `task_type`）
- status 合法值：`success` / `partial` / `failed` / `format_failed`
- 研究任務額外規則：status 禁止 `"partial"`（見各任務 prompt 說明）
- KB 寫入失敗時 status 可為 `"partial"`（合法降級場景）

## 禁止事項

- 禁止在 prompt 中硬編碼端點 URL（改用 `.env` 或 `config/`）
- 禁止在 prompt 中定義 TTL（改 `config/cache-policy.yaml`）
- 禁止在 prompt 中定義標籤路由規則（改 `config/routing.yaml`）
