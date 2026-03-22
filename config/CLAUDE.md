# config/ 目錄局部規則

## 單一定義原則（修改前先確認唯一真相來源）

| 配置項目 | 唯一真相來源 |
|---------|------------|
| 快取 TTL | `cache-policy.yaml` |
| task_key | `frequency-limits.yaml`（auto-task 命名的唯一真相） |
| Todoist 標籤路由 | `routing.yaml` |
| LLM 模型選擇 | `llm-router.yaml` |
| 端點 URL | `.env` 或 `dependencies.yaml`（若存在） |
| Hook 攔截規則 | `hook-rules.yaml` |
| 各 Agent 超時 | `timeouts.yaml` |

## YAML 版本管理

- 每個 YAML 頂部必須有 `version:` 欄位
- 影響現有行為的修改 → 遞增版本號
- 純新增欄位（向後相容）→ 不需遞增

## 計畫檔存放

計畫檔一律放在 `docs/plans/` 目錄下（格式：`{feature}-plan.md`）；寫入專案外僅會觸發 Write Guard 告警（不阻擋）。

## 高影響配置修改後的必要驗證

| 修改目標 | 驗證指令 |
|---------|---------|
| `hook-rules.yaml` | `uv run pytest tests/hooks/` |
| `frequency-limits.yaml` | `uv run python hooks/validate_config.py --check-auto-tasks` |
| `routing.yaml` | 觀察下次 todoist-query 執行的路由日誌 |
| `llm-router.yaml` | `uv run python tools/llm_router.py --task-type <type> --dry-run` |
