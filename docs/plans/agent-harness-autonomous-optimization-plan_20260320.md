# Agent Harness 優化方案

## 範圍
- 現有 harness：`run-agent-team.ps1`、`run-todoist-agent-team.ps1`、`templates/auto-tasks/self-heal.md`
- 新增控制面：`tools/autonomous_harness.py`

## 改善目標
1. 用單一控制平面整合狀態與調度判斷。
2. 把 stale run、連續失敗、自動任務異常轉成可執行的 recovery queue。
3. 將自治決策從腳本內聯判斷提升為獨立、可測、可排程模組。

## 實作項目
1. 新增 `config/autonomous-harness.yaml`
2. 新增 `tools/autonomous_harness.py`
3. 新增 `tests/tools/test_autonomous_harness.py`
4. 新增研究報告與本方案文件
5. 新增 `state/autonomous-runtime.json` 的 runtime policy 輸出
6. 讓 `run-todoist-agent-team.ps1` 在 Phase 2 前讀取 runtime policy，實際降載 auto-task

## 執行命令
```powershell
uv run python tools/autonomous_harness.py --format json
uv run python tools/autonomous_harness.py --execute --format json
uv run pytest tests/tools/test_autonomous_harness.py
```

## 驗收條件對應
- 自動啟動：由 dispatch command 支援 restart_agent
- 錯誤自恢復：由 stale run / failed auto task / open circuit 轉 recovery action
- 資源自調整：由 runtime policy 控制 auto-task 平行度與重型任務是否允許執行

## 後續待做
1. 將 `run-agent-team.ps1` 與 `run-todoist-agent-team.ps1` 的部分風險判斷改由 supervisor 提供。
2. 把 `context-budget-monitor`、`task-fairness-analyzer` 之外的更多 guard（如 done_cert 比率）納入自治 gate。
3. 為 `autonomous_harness.py` 建立 Task Scheduler 或 HEARTBEAT 接入點。
