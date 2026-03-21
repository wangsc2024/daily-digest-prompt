# Agent Harness 研究報告

日期：2026-03-20
範圍：`run-agent-team.ps1`、`run-todoist-agent-team.ps1`、`tools/autonomous_harness.py`、`config/autonomous-harness.yaml`、`CHANGELOG.md`、`context/*.json`、KB 既有研究與外部官方資料

## 1. 版本與研究邊界

- 目前系統使用的是專案內建 harness，而非外部套件。
- 可追溯版本基線：
  - `CHANGELOG.md` 顯示正式版本至少從 `0.1.0`（2026-02-15）演進到 `0.2.0`（2026-03-09）。
  - `Unreleased` 顯示 2026-03-20 前已加入 autonomous runtime、result schema、Skill registry、cursor CLI fallback 等能力。
  - `config/dependencies.yaml` 版本為 `2.0.0`，更新日 2026-03-17。
  - `config/autonomous-harness.yaml` 生成日為 2026-03-20，代表自治控制面屬最新一輪能力。
- 設計文件來源：
  - `docs/ARCHITECTURE.md`
  - `docs/agent-harness-autonomy-troubleshooting_20260320.md`
  - `agent_harness_research_plan.md`
  - KB 筆記：`Agent Harness 自主管理最終報告`、`Agent Harness 分議題深度研究筆記`

## 2. 現有架構與運作機制

### 2.1 核心執行拓樸

- `run-agent-team.ps1`
  - Daily digest 團隊模式。
  - Phase 0：circuit breaker 與 cache 狀態預計算。
  - Phase 1：平行 fetch agents。
  - Phase 2：assembly agent。
- `run-todoist-agent-team.ps1`
  - Todoist 三階段 harness。
  - Phase 1：query + route + plan。
  - Phase 2：平行 task/auto-task 執行。
  - Phase 3：assembly + close + notify。
- `tools/autonomous_harness.py`
  - 現行自治控制面。
  - 聚合 `run-fsm`、`scheduler-state`、`failure-stats`、`failed-auto-tasks`、`api-health`、fairness hint、token budget、heartbeat、resource snapshot。
  - 輸出 `state/autonomous-harness-plan.json` 與 `state/autonomous-runtime.json`。

### 2.2 已落地的自癒能力

- Instance lock、stale lock 清理。
- Phase timeout、retry、backoff。
- circuit breaker 預檢查與結果回寫。
- cache hit 跳過、degraded result fallback。
- `run-fsm.json` 追蹤 phase 狀態，含 stale running 清理。
- `failure-stats.json`、`scheduler-state.json`、`spans-*.json` 提供最小可觀測性。
- 自治 runtime policy 已能限制：
  - `max_parallel_auto_tasks`
  - `max_parallel_fetch_agents`
  - blocked fetch agents
  - heavy/research auto-task 開關
  - digest assembly mode / retries

### 2.3 已知限制

- `autonomous_harness.py` 原本只會「規劃」與「排隊」，沒有獨立 consumer 落實 queue action。
- recovery queue 已存在，但 `docs/agent-harness-autonomy-troubleshooting_20260320.md` 明確指出缺少常駐 consumer。
- 目前 durable execution 仍不足：
  - `ADR-20260318-028` 的 Phase 2 snapshot / resume 仍是 `Proposed`。
- trace 仍分散：
  - spans、results、structured logs、state 檔案尚未完全統一 schema。
- 自治治理仍偏 rule-based：
  - 能降載、能阻擋，但缺少閉環驗證與效果回寫。

## 3. 主要問題與根因

### 3.1 Self-healing 還沒形成閉環

- `autonomous_harness.py` 會產出 `restart_agent`、`queue_self_heal`、`rebalance_tasks`、`scale_down_workload`。
- 但原始架構中，除 `--execute` 的 restart 之外，多數 action 只是落到 queue。
- 這意味控制面已存在，執行面仍不完整。

### 3.2 Durability 不足

- `system-insight.json` 顯示近 7 天成功率僅 `84.6%`，低於 90% 目標。
- 主要 recurring causes：`phase_failure`、`timeout`。
- 這與 KB / ADR 中提出的「Phase 2 snapshot recovery」缺口一致。

### 3.3 治理指標尚未轉成強制機制

- `avg_io_per_call` 約 `24315`，明顯高於門檻。
- `cache_hit_ratio` 僅 `20.7%`。
- `auto_task_fairness` 雖已改善，但仍需持續維持。
- 目前多是報表警示，尚未全部轉成強制的 budget / guard / rollback 機制。

## 4. 外部參考與對照

- OpenTelemetry 指出 trace 應由 span DAG 組成，適合把 phase、task、retry、artifact 串成單一因果鏈。
  - https://opentelemetry.io/docs/reference/specification/overview/
  - https://opentelemetry.io/docs/concepts/signals/
- Google SRE 的 error budget policy 建議把 SLO miss、單一 incident budget burn 與 postmortem 直接連動。
  - https://sre.google/workbook/error-budget-policy/
- KB 中既有研究已把 LangGraph 的 durable execution、Langfuse 的 trace/prompt versioning、pre-commit 的 declarative guard registry 納入對照來源。

## 5. 本次實作補強

### 5.1 新增自治恢復 worker

- 新增 `tools/autonomous_recovery_worker.py`
- 功能：
  - 消費 `state/autonomous-recovery-queue.json`
  - 處理 `restart_agent`
  - 將 `queue_self_heal`、`rebalance_tasks`、`scale_down_workload` 實際轉為 runtime override
  - 寫入 `state/autonomous-self-heal-requests.json`
  - 回刷 `state/autonomous-runtime.json`

### 5.2 新增 runtime override 機制

- `tools/autonomous_harness.py` 現在會讀取 `state/autonomous-runtime-overrides.json`
- override 可：
  - 提高 mode floor（normal -> degraded/recovery）
  - 收斂並行度
  - 額外封鎖 fetch agents / task keys
  - 附帶 expiry 與 reason

### 5.3 設定與測試同步補齊

- `config/autonomous-harness.yaml`
  - 新增 `runtime_override_path`
  - 新增 `self_heal_request_path`
  - 新增 `recovery_worker` TTL / timeout 配置
- 測試：
  - `tests/tools/test_autonomous_harness.py`
  - `tests/tools/test_autonomous_recovery_worker.py`

## 6. 結論

- 現有 harness 已具備控制面雛形，但原本缺少 queue consumer，因此離真正 self-management 還差「執行與回寫」這一步。
- 本次補強把控制面與恢復佇列打通，讓系統可以把自治判斷落成暫時降載、重平衡與自癒請求紀錄，形成第一個可驗證閉環。
- 下一個最高優先缺口不是再加更多規則，而是補 durable snapshot/resume 與統一 trace schema，否則成功率與恢復時間仍難穩定達標。
