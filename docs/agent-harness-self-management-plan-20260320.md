# Agent Harness 優化方案與自主管理落地計畫

日期：2026-03-20
目標：讓目前 harness 從「可偵測、可降級」提升到「可恢復、可量測、可回退」。

## 優化方向 1：恢復佇列消費者與 runtime override 閉環

- 實作概念：
  - 將 `autonomous_harness` 產生的 queue action 交由獨立 worker 消費。
  - 對非破壞性動作改採 runtime override，而不是直接硬重啟。
  - override 必須帶 `reason`、`expires_at`、blocked targets、parallelism cap。
- 預期效益：
  - queue 不再只是告警堆積。
  - 可在 1 個排程周期內把資源壓力、token budget、飢餓任務反映到實際執行策略。
  - 降低「知道問題但系統沒有採取動作」的治理落差。
- 風險：
  - override 過於保守時，可能讓系統長時間卡在 degraded mode。
- 緩解措施：
  - 所有 override 加 TTL。
  - 保留 reason 與 processed log。
  - 後續納入 success-rate / MTTR 回饋調參。
- 實作狀態：
  - 本次已完成第一版。

## 優化方向 2：Phase 2 snapshot / resume durability

- 實作概念：
  - 在 Phase 2 每個 agent 完成時落盤 snapshot。
  - 下次執行先讀 snapshot + `run-fsm`，僅重試未完成或失敗的 agent。
  - snapshot schema 應包含 `trace_id`、phase、completed_agents、artifact paths、expiry。
- 預期效益：
  - 避免單一 timeout 造成整批重跑。
  - 提升成功率與平均恢復時間。
  - 讓 self-healing 從「重啟重跑」升級成「續跑恢復」。
- 風險：
  - 過期 snapshot 或錯誤 artifact 可能導致髒恢復。
- 緩解措施：
  - 與 `run-fsm` 綁定。
  - snapshot TTL 與 artifact existence check。
  - 恢復前做 schema 驗證與 checksum 檢查。
- 實作狀態：
  - 尚未完成，列為下一個 P0。

## 優化方向 3：統一 execution trace schema 與 recovery causality

- 實作概念：
  - 將 spans、results、queue action、runtime override、self-heal request 統一到同一 trace schema。
  - 最小欄位：`trace_id`、`span_id`、`phase`、`task_key`、`status`、`artifacts`、`cause_chain`、`recovery_action`。
- 預期效益：
  - 失敗 run 可從單一 trace 回溯。
  - 可量化 resumed ratio、budget burn、top failure cause、top recovery action。
  - 讓 system-insight 與 postmortem 自動化。
- 風險：
  - 向後相容成本高，可能衝擊既有報表。
- 緩解措施：
  - 採 additive schema。
  - 新舊欄位共存一段時間。
  - 先從 auto-task 與 recovery path 開始。
- 實作狀態：
  - 尚未完成，列為 P1。

## 優化方向 4：SLO / Error Budget 治理強制化

- 實作概念：
  - 將 `daily_success_rate`、Phase 2 success rate、MTTR、queue backlog 定義成 SLI。
  - 以 28 天 error budget 驅動 freeze / postmortem / rollback。
- 預期效益：
  - 自治規則由「感覺不穩」變成「超出預算即觸發治理」。
  - 把 reliability 與 feature velocity 分離成可決策信號。
- 風險：
  - 初期基線不穩，容易誤判。
- 緩解措施：
  - 先用 warning-only。
  - 連續兩週收資料後再強制執行。
- 實作狀態：
  - 研究完成，尚未完整落地。

## 審查流程

1. 方案提交：研究報告 + 方案文件 + 變更清單。
2. 內部技術評審：檢查 durability、trace、rollback、資安邊界。
3. 測試驗證：
   - queue 消費
   - runtime override 生效
   - stale run / starvation / token pressure 三類故障情境
4. 反饋修正：更新方案、紀錄變更與未解決風險。

## 本輪變更紀錄

- R1：
  - 完成 recovery worker。
  - 完成 runtime override 機制。
  - 補上 worker / override 測試。
  - 保留 Phase 2 snapshot/resume 與 trace schema 為後續優先工作。
