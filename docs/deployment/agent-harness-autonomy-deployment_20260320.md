# Agent Harness 自主管理部署手冊

## 1. 部署目標
在測試環境或等效生產環境啟用以下能力：
- 自動偵測新 agent / auto-task
- 監控狀態與故障恢復 queue
- 依資源與風險模式動態降載

## 2. 必要檔案
- `config/autonomous-harness.yaml`
- `tools/autonomous_harness.py`
- `run-agent-team.ps1`
- `run-todoist-agent-team.ps1`
- `state/*.json`

## 3. 前置條件
- Windows + PowerShell 7
- Python 3.9+
- 可讀寫專案 `state/` 與 `logs/`
- 若需 GPU 指標：主機需安裝 `nvidia-smi`

## 4. 部署步驟
1. 確認設定檔存在
   - `config/autonomous-harness.yaml`
2. 先執行 dry-run

```powershell
python tools/autonomous_harness.py --format json
```

3. 確認已生成以下檔案
   - `state/autonomous-harness-plan.json`
   - `state/autonomous-runtime.json`
   - `state/autonomous-agent-registry.json`
   - `state/autonomous-resource-snapshot.json`

4. 啟動主排程

```powershell
pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1
pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1
```

5. 驗證主排程 log 出現以下訊息
   - `[Autonomy] runtime mode=...`
   - `[Autonomy] fetch agents adjusted: ...`
   - `[Autonomy] auto-tasks adjusted: ...`

## 5. 建議排程
- `tools/autonomous_harness.py`
  - 每 5 分鐘一次
- `run-todoist-agent-team.ps1`
  - 依既有排程頻率

## 6. 驗收檢查
- 新增 `templates/auto-tasks/<new-task>.md` 後，重新執行 supervisor
  - `state/autonomous-agent-registry.json` 應出現新 task
- 當 `state/auto-task-fairness-hint.json` 顯示 starvation
  - `state/autonomous-runtime.json` 應切到 `degraded`
  - `run-agent-team.ps1` 應跳過 `security`、`chatroom` 等非核心 fetch agent
- 當 token budget 告警日期為當日
  - `blocked_task_keys` 應含高成本 task
  - `max_parallel_fetch_agents` 應下降

## 7. 回滾
1. 停止排程執行 `tools/autonomous_harness.py`
2. 保留 `run-todoist-agent-team.ps1`，刪除或忽略 `state/autonomous-runtime.json`
3. 視需要還原本輪修改的三個檔案：
   - `config/autonomous-harness.yaml`
   - `tools/autonomous_harness.py`
   - `run-agent-team.ps1`
   - `run-todoist-agent-team.ps1`
