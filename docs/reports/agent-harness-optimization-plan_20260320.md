# Agent Harness 優化方案（完整版）

**日期**：2026-03-20  
**範圍**：agent harness 研究、現狀分析、改進建議、實作步驟與驗收條件  
**任務來源**：Cursor CLI 執行，依 skills/cursor-cli、knowledge-query、web-research、ntfy-notify

---

## 1. 執行摘要

本方案基於專案既有 harness 實作、KB 研究策略簡報、外部文獻與網路研究，產出可量測、可驗證、可回退的 agent harness 自主管理優化體系。現有系統已具備控制面、恢復佇列、runtime override 與 recovery worker，本輪補齊：**量化 benchmark 指標**、**排程整合**、**通知閉環驗證**與**知識庫匯入**。

---

## 2. 研究發現與參考來源

### 2.1 Agent Harness 核心概念（外部文獻）

| 來源 | 作者/機構 | 發表日期 | 關鍵概念 |
|------|-----------|----------|----------|
| [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Anthropic | 2025-11-26 | 初始器 agent + 編碼 agent 雙階段、feature list、incremental progress、clean state、git commit 與 progress file |
| [Durable Execution for AI Agents](https://inference.sh/blog/agent-runtime/durable-execution) | inference.sh | 2025 | checkpoint、resumability、retry、idempotency；每步後 checkpoint，中斷後從 checkpoint 續跑 |
| [Improving Deep Agents with harness engineering](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/) | LangChain | 2025 | harness 優化可顯著提升表現（52.8%→66.5%），系統 prompt、tools、middleware、執行流程為核心組件 |
| [Kubernetes Self-Healing with AI Operators](https://markaicode.com/kubernetes-self-healing-ai-operators-2025/) | Markaicode | 2025 | 預測異常、根因分析、自校正、持續學習；AI operator 比 rule-based 降低 87% 停機 |
| [AI Agent Self-Healing: Recovery Patterns](https://zylos.ai/research/2026-03-02-ai-agent-self-healing-recovery-patterns) | Zylos Research | 2026-03 | 自動恢復與韌性模式 |

### 2.2 本專案現有架構（已落地）

- **控制面**：`tools/autonomous_harness.py` 聚合 run-fsm、scheduler-state、failure-stats、failed-auto-tasks、api-health、fairness、token budget、heartbeat、resource snapshot
- **恢復佇列**：`state/autonomous-recovery-queue.json`，由 `tools/autonomous_recovery_worker.py` 消費
- **Runtime override**：`state/autonomous-runtime-overrides.json` 可強制 degraded/recovery、blocked_task_keys、max_parallel
- **通知**：ntfy topic `wangsc2025`，依 ntfy-notify Skill 發送

### 2.3 KB 研究策略簡報缺口（context/kb-research-brief.json）

| 缺口類型 | 說明 |
|----------|------|
| optimization | 缺少可重複執行的 agent harness 效能與可靠性 benchmark 套件 |
| optimization | snapshot/resume、queue consumer、runtime override 三者的整合驗證仍不完整 |
| synthesis | 通知閉環與 SLO、approval gate、incident triage 的統一治理模型尚未建立 |

---

## 3. 現狀分析

### 3.1 優勢

- 單一控制面已收斂多種狀態來源
- 自動發現 agent registry（fetch-*.md、auto-tasks/*.md）
- 資源感知（CPU、memory、GPU）與 typeperf fallback
- 三段式 runtime profile：normal / degraded / recovery
- recovery worker 已處理 restart_agent、queue_self_heal、rebalance_tasks、scale_down_workload
- 10 個單元測試通過

### 3.2 限制

- 無常駐排程：`autonomous_harness.py` 與 `autonomous_recovery_worker.py` 未納入 HEARTBEAT.md
- Phase 2 snapshot/resume 仍為 Proposed（ADR-20260318-028）
- 無量化 benchmark：MTTR、resumed ratio、budget burn 未建立基線
- 通知成效未驗證：ntfy 發送成功率、噪音抑制、升級策略未量化

### 3.3 潛在風險

- 排程帳號下 typeperf 權限可能不足
- 跨節點調度尚未支援
- 單一 JSON 檔案作為 queue 的 durability 有限（無 WAL、無分散式鎖）

---

## 4. 改進建議

### 4.1 設計模式

- **Reconciliation loop**：借鏡 Kubernetes Operator，每 N 分鐘執行 harness → 比較 desired vs actual → 寫入 recovery queue
- **Policy-driven recovery**：閾值與規則驅動，避免人工看 log
- **Observability-first**：trace、span、guardrail、handoff 內建

### 4.2 效能調校

- 將 harness 與 recovery worker 納入排程（建議每 5 分鐘）
- 資源 snapshot 寫入長期趨勢檔，供自治調優
- 建立 benchmark 指標：success_rate、MTTR、queue_backlog、budget_burn

### 4.3 容錯機制

- 增加 checkpoint 頻率：每個 phase 完成後寫入 run-fsm
- 為 recovery queue 增加 WAL 或 atomic append（可選）
- 通知失敗時寫入 logs/ntfy/ 並重試

### 4.4 資源管理

- 已實作：CPU/memory/GPU 閾值觸發 scale_down_workload
- 建議：將 token budget burn 與 resource snapshot 寫入同一時間序列

---

## 5. 具體實作步驟與預估工時

| 步驟 | 內容 | 預估工時 |
|------|------|----------|
| 1 | 將 `autonomous_harness.py` 與 `autonomous_recovery_worker.py` 納入 HEARTBEAT.md 排程 | 0.5h |
| 2 | 建立 benchmark 指標表（success_rate、MTTR、queue_backlog、budget_burn）並寫入 state/ | 2h |
| 3 | 設計 snapshot/resume、override、通知的情境測試矩陣 | 1.5h |
| 4 | 將 resource_snapshot、done_cert、recovery 結果寫入長期趨勢檔 | 2h |
| 5 | 通知與 SLO 治理規格（分級、靜默、升級、approval gate） | 2h |

---

## 6. 測試計畫與驗證指標

### 6.1 單元測試（已通過）

- `tests/tools/test_autonomous_harness.py`：10 個
- `tests/tools/test_autonomous_recovery_worker.py`：2 個

### 6.2 整合測試情境

| 情境 | 預期行為 |
|------|----------|
| starvation_detected=true | runtime mode=degraded，max_parallel=2 |
| token_budget_alert | scale_down_workload 入隊 |
| heartbeat_stale | mode=recovery，queue_self_heal |
| CPU > 85% | scale_down_workload 入隊 |

### 6.3 驗收指標

- 系統在 48 小時內無人工介入完成啟動、監控、故障恢復與資源調整
- 成功率 >= 95%（測試環境 auto-task）
- 故障恢復時間 < 1 分鐘（stale run / heartbeat stale 進入 recovery queue）

---

## 7. 交付物清單

- 程式：`tools/autonomous_harness.py`、`tools/autonomous_recovery_worker.py`、`config/autonomous-harness.yaml`
- 狀態：`state/autonomous-*.json`
- 文件：本優化方案、部署手冊、故障排除
- 通知：ntfy topic `wsngsc2025` 完成通知

---

## 8. 參考資料完整列表

1. Anthropic - Effective harnesses for long-running agents (2025-11-26) https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
2. inference.sh - Durable Execution for AI Agents https://inference.sh/blog/agent-runtime/durable-execution
3. LangChain - Improving Deep Agents with harness engineering https://blog.langchain.com/improving-deep-agents-with-harness-engineering/
4. LangGraph 1.0 GA (2025-10-22) https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available
5. OpenAI Agents SDK (2025) https://platform.openai.com/docs/guides/agents-sdk/
6. AutoGen 0.4 launch (2025-01-17) https://devblogs.microsoft.com/autogen/autogen-reimagined-launching-autogen-0-4/
7. Temporal - Durable Execution https://docs.temporal.io/
8. Kubernetes self-healing docs https://kubernetes.io/docs/concepts/architecture/self-healing/
9. Markaicode - Kubernetes Self-Healing with AI Operators 2025 https://markaicode.com/kubernetes-self-healing-ai-operators-2025/
10. Zylos Research - AI Agent Self-Healing Recovery Patterns (2026-03) https://zylos.ai/research/2026-03-02-ai-agent-self-healing-recovery-patterns
11. OpenTelemetry Specification https://opentelemetry.io/docs/reference/specification/overview/
12. Google SRE Error Budget Policy https://sre.google/workbook/error-budget-policy/

---

## 9. 版本控制

- 文件版本：1.0
- 生成日期：2026-03-20
- 命名規則：`YYYYMMDD_文件名稱.md`
