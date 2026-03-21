# Agent Harness 迭代審查報告

## 第 1 輪
- 變更：新增 supervisor 原型與測試。
- 驗證：模擬 stale run、連續失敗、自動任務失敗。
- 問題：
  - 缺少 recovery queue 寫回。
  - restart 與 queue action 需要去重。

## 第 2 輪
- 變更：加入 action 去重、recovery queue、execute 僅處理 restart_agent。
- 驗證：dry-run 計畫輸出與單元測試。
- 結論：已可作為自治控制面的最小可用版本，但尚未接入動態資源調整與完整排程自註冊。

## 第 3 輪
- 變更：加入 fairness / token-budget / scheduler-heartbeat gate，並輸出 `state/autonomous-runtime.json`。
- 驗證：`python tools/autonomous_harness.py --format json` 實際輸出 `mode=degraded`，Todoist 排程新增 runtime policy 載入與 auto-task 降載路徑。
- 問題：
  - pytest 受本機暫存 ACL 影響，無法完成 session cleanup。
  - `agent -p` 仍回 `[internal]`，Cursor CLI 無法成為本輪可用後端。

## 第 4 輪
- 變更：
  - 將 fetch-agent 治理納入 runtime policy，新增 `max_parallel_fetch_agents`、`blocked_fetch_agents`、`allowed_fetch_agents`。
  - `run-agent-team.ps1` Phase 1 讀取 `state/autonomous-runtime.json`，在 `degraded/recovery` 模式下降載與封鎖非核心 fetch agent。
  - 測試擴充 recovery 模式下 fetch policy 驗證案例。
- 驗證：
  - `python tools/autonomous_harness.py --format json` 成功輸出 `max_parallel_fetch_agents=4`。
  - 以隔離測試目錄手動呼叫 `AutonomousHarness.build_plan()`，確認 recovery 模式下僅允許 `todoist/news/hackernews`。
- 問題：
  - Windows ACL 仍阻斷 pytest 的 tmp cleanup；需在權限正常主機補跑完整 pytest。

## 第 5 輪
- 變更：
  - 修正 `tools/autonomous_harness.py` 的 Windows 資源量測相容性，保留既有 PowerShell JSON 路徑，並新增 `typeperf` fallback。
  - 新增 `_parse_typeperf_value()` 與對應單元測試，避免低權限帳號下 CPU / 記憶體指標長期為 `null`。
- 驗證：
  - `python tools/autonomous_harness.py --format json` 現已輸出 CPU、memory、GPU 三類資源快照。
  - 實測快照：`cpu.percent=0.0`、`memory.percent=73.696734`、`memory.available_mb=14103.0`、`gpu.memory_percent=3.04`。
  - `python -m pytest tests/tools/test_autonomous_harness.py::test_parse_typeperf_value_extracts_numeric_sample --basetemp=tmp/pytest-autonomous-harness-fix2` 通過。
- 問題：
  - 完整 pytest 仍因本機 `tmp` ACL 導致 session cleanup 失敗。
  - Cursor CLI `agent -p` 經實際嘗試後仍回傳 `[internal]`，未能作為本輪可用執行後端。

## 未完成項
1. `run-agent-team.ps1` 的 Phase 2 assembly 尚未接自治 gate，目前僅 Phase 1 fetch 已接上。
2. `agent -p` 本機執行失敗，未能把 Cursor CLI 納入實際執行後端。
3. pytest 仍受環境 ACL 阻斷，需在可寫暫存環境重跑完整測試。
4. 尚未取得 wsngsc2025 的回覆確認，只能先完成通知發送與紀錄。
