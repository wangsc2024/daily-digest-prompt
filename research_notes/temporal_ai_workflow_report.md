# Temporal 深度研究報告

## 概述
Temporal 是以「Durable Execution（持久執行）」為核心的工作流引擎，定位不是純 no-code 編排器，而是給工程團隊用程式碼建構高可靠長流程系統。它特別適合需要跨服務、長時間、可恢復、可追蹤的 AI 工作流，例如多步推理、工具呼叫鏈、人機協作審批與異步補償流程。相較於只做任務排程的平台，Temporal 的重點是把流程狀態與事件歷史作為一等公民，讓流程在失敗、重啟、網路中斷後仍能從正確位置繼續。

## 技術架構
Temporal 採用「使用者執行環境」與「Temporal 叢集服務」分離架構。使用者端透過 SDK 撰寫 Workflow 與 Activity，Worker 透過 Task Queue 向 Temporal 服務輪詢任務；伺服器端由 History Service 與 Matching Service 等核心元件維護事件歷史、任務分派與執行推進。其關鍵設計是事件溯源（event sourcing）：每個 Workflow Execution 都有 append-only Event History，Worker 當機後可藉 replay 還原狀態。Workflow 需遵守 deterministic 約束，外部不確定操作放在 Activity，由重試、heartbeat、timeout 策略處理。

## 工作流核心能力
Temporal 在工作流層提供完整控制面：
- 觸發與排程：支援 Schedule（比傳統 cron 更彈性）、Start Delay、Backfill、Pause/Resume、Overlap Policy。
- 節點語義：Workflow Task、Activity Task、Query Task；並支援 Child Workflow、Continue-As-New、重試策略與補償模式。
- 訊息機制：Signals（非同步寫入）、Queries（唯讀查詢）、Updates（可等待結果的同步寫入）。
- 整合模式：Task Queue 可把不同服務、不同語言 Worker 串為單一流程，適合微服務與 AI 工具鏈協作。

## AI 整合機制
Temporal 在 AI 場景主要扮演「耐久編排層」而非模型抽象層。官方 AI Cookbook 已提供 OpenAI、Claude、LiteLLM、工具呼叫、HITL、Durable MCP server 等範例，顯示其整合策略偏向程式碼優先與 SDK 封裝。社群範例 `temporal-ai-agent` 展示了單 Agent 與多 Agent 模式，並同時支援 native tools 與 MCP tools；模型供應商由 LiteLLM 抽象，能切換 OpenAI/Anthropic/Gemini/Ollama。限制面在於：Temporal 不直接提供 no-code prompt 管理與模型評測儀表板，這部分通常要搭配 Langfuse、自建評測或應用層治理。

## 部署與維運
Temporal 支援 Self-hosted 與 Temporal Cloud 兩種路徑。Self-hosted 適合強合規、內網部署與資料主權場景；Cloud 適合快速上線與降低維運負擔。維運重點包括 Worker 水平擴展、Task Queue 分流、Event History 與 payload 管理（必要時採 claim-check pattern）、以及 Web UI/CLI 的可觀測與故障排查。官方說明也強調可逐步導入既有架構，不必一次性重寫整套系統。

## 與 daily-digest-prompt 的連結
對 daily-digest-prompt 這類 Claude Agent 系統，Temporal 可提供三項直接借鏡：
- Durable 任務鏈：把「研究→去重→KB 匯入→通知」做成可恢復長流程，避免中途失敗造成狀態不一致。
- 人機協作節點：用 Signal/Update 在關鍵節點（例如發布前審核）插入人工確認，同時保留完整歷史。
- 多 Worker 分工：將 Web 研究、摘要生成、KB 寫入拆為獨立 Activity，由 Task Queue 控制吞吐與重試，提升穩定性。

## 優缺點評估
**優點**：
- 耐久執行能力強，對長流程與失敗恢復非常成熟。
- 程式碼優先，對複雜條件分支、補償交易、多服務協作彈性高。
- AI 場景支援度持續提升（AI Cookbook、MCP 範例、Agent 範例齊全）。
- 可自架也可上雲，部署策略彈性大。

**缺點 / 限制**：
- 學習曲線高於 no-code 工具，需理解 deterministic/replay 等核心觀念。
- 非即用型 LLMOps 平台，模型評測、Prompt 管理、成本治理需額外整合。
- Event History 與 payload 若未治理，長對話或大型輸入會帶來儲存與效能壓力。

## 社群狀態
Stars：18.7k | Forks：1.4k | 最近更新：2026-03-02（`v1.30.1` release）

## 參考來源
- [temporalio/temporal（GitHub）](https://github.com/temporalio/temporal)
- [Temporal Docs 首頁](https://docs.temporal.io/)
- [How Temporal Works](https://temporal.io/how-it-works)
- [Temporal Architecture README](https://github.com/temporalio/temporal/blob/main/docs/architecture/README.md)
- [Temporal Workflow](https://docs.temporal.io/workflows)
- [What is a Temporal Activity?](https://docs.temporal.io/activities)
- [Temporal Workflow Message Passing](https://docs.temporal.io/encyclopedia/workflow-message-passing)
- [Temporal Schedule](https://docs.temporal.io/schedule)
- [AI Cookbook](https://docs.temporal.io/ai-cookbook)
- [temporal-community/temporal-ai-agent（GitHub）](https://github.com/temporal-community/temporal-ai-agent)
- [PrefectHQ/prefect（GitHub）](https://github.com/PrefectHQ/prefect)
- [dagster-io/dagster（GitHub）](https://github.com/dagster-io/dagster)
