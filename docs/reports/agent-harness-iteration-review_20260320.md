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

## 未完成項
1. `run-agent-team.ps1` 尚未讀取 runtime policy，現在只有 Todoist Phase 2 已接上自治降載。
2. `agent -p` 本機執行失敗，未能把 Cursor CLI 納入實際執行後端。
3. pytest 仍受環境 ACL 阻斷，需在可寫暫存環境重跑完整測試。
4. 尚未取得 wsngsc2025 的回覆確認，只能先完成通知發送與紀錄。
