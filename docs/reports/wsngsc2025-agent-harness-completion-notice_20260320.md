# 完成通知：Agent Harness 自主管理優化已完成

收件對象：wsngsc2025  
日期：2026-03-20

## 研究與優化概述
- 已完成 agent harness 的研究、現況審查、優化設計與程式落地。
- 本輪重點是將既有狀態檔、故障統計、公平性、token budget、heartbeat 與資源訊號整合成單一自治 supervisor。
- 同時新增 agent 自動發現 registry，讓新 fetch prompt / auto-task template 可被自動納入控制面，且 daily-digest 與 Todoist 兩條 harness 都會讀取同一份 runtime policy。
- 其中 daily-digest harness 已補齊 Phase 2 assembly 自治 gate，可依 supervisor policy 自動切換 `full / degraded / skip`，避免在 recovery 模式下繼續消耗高成本組裝流程。

## 實作成果與測試報告
- 已落地檔案：
  - `tools/autonomous_harness.py`
  - `config/autonomous-harness.yaml`
  - `run-agent-team.ps1`
  - `run-todoist-agent-team.ps1`
  - `tests/tools/test_autonomous_harness.py`
- 已生成狀態輸出：
  - `state/autonomous-harness-plan.json`
  - `state/autonomous-runtime.json`
  - `state/autonomous-agent-registry.json`
  - `state/autonomous-resource-snapshot.json`
- 本機驗證：
  - `python tools/autonomous_harness.py --format json` 成功
  - 已可實際量測 CPU / memory / GPU，避免低權限帳號下資源欄位為 `null`
  - runtime 已進入 `degraded` 模式，並輸出 `blocked_task_keys`、`blocked_fetch_agents`
  - recovery 手動情境驗證確認只保留 `todoist/news/hackernews` 三個核心 fetch agent
  - pytest 受主機 ACL 限制，失敗點位於 pytest 暫存目錄建立/清理，不是本次邏輯錯誤
  - Cursor CLI 已依規定建立任務檔並實際嘗試 `agent -p`，但本機回傳 `[internal]`，因此本輪以本地 harness 腳本與 Python supervisor 作為正式執行路徑

## 後續維護建議
1. 以排程固定執行 `tools/autonomous_harness.py`，形成監控閉環。
2. 補一個 recovery worker，主動消費 `state/autonomous-recovery-queue.json`。
3. 將資源趨勢、done_cert 成功率與 recovery 結果長期化，作為自治調優依據。
4. 規劃將 supervisor 升級為常駐 control plane service，以支援跨節點調度。
