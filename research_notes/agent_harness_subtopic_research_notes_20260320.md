# Agent Harness 分議題深度研究筆記

研究日期：2026-03-20  
研究對象：`D:\Source\daily-digest-prompt` 內的 agent harness（含 `run-agent-team.ps1`、`run-todoist-agent-team.ps1`、`tools/autonomous_harness.py`）  
研究範圍：現有 harness 架構、效能、可擴展性、錯誤恢復、資源管理、測試、部署、觀測、安全、演進路線  
研究方法：依 `skills/web-research/SKILL.md` 與 `skills/knowledge-query/SKILL.md` 執行 KB 檢索、本地文件/程式碼蒐證、外部官方文件交叉比對  
外部來源狀態：已取得外部網路來源  
KB 狀態：health check 成功；已檢索既有 `agent harness` 與研究方法論筆記  

---

## 子議題 1：現有 harness 架構與任務管線

### 核心論點
- 本專案的 harness 不是單一 agent，而是「文件驅動配置層 + PowerShell 編排層 + Skills 行為層 + state/context 持久化層 + hooks 防護層」的複合式 orchestrator。
- 主要執行面分成兩條：`run-agent-team.ps1` 處理每日摘要的 `Phase 1 並行擷取 -> Phase 2 組裝`；`run-todoist-agent-team.ps1` 處理 Todoist 的 `Phase 1 規劃 -> Phase 2 N 平行執行 -> Phase 3 組裝`。
- 2026-03-20 新增的 `tools/autonomous_harness.py` 已形成控制平面雛形，負責彙整 `scheduler-state`、`run-fsm`、`failure-stats`、`failed-auto-tasks`、資源快照與 runtime policy。

### 主要論據與證據
- [docs/ARCHITECTURE.md](/D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md) 將系統拆成 prompt、config、templates、scripts、hooks、prompts/team、state、memory、skills、docs 共 10+ 層，並明列 `run-agent-team.ps1`、`run-todoist-agent-team.ps1`、`setup-scheduler.ps1` 為核心執行腳本。
- [docs/ARCHITECTURE.md](/D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md) 指出排程至少 6 條：`system-audit`、`daily-digest-am`、`daily-digest-mid`、`daily-digest-pm`、`todoist-single`、`todoist-team`。
- [run-agent-team.ps1](/D:/Source/daily-digest-prompt/run-agent-team.ps1) 開頭直接把架構定義為 `Phase 1: 5 parallel fetch agents` 與 `Phase 2: 1 assembly agent`。
- [run-todoist-agent-team.ps1](/D:/Source/daily-digest-prompt/run-todoist-agent-team.ps1) 開頭直接定義 `Phase 1: 1 query agent`、`Phase 2: N parallel agents`、`Phase 3: 1 assembly agent`。
- [tools/autonomous_harness.py](/D:/Source/daily-digest-prompt/tools/autonomous_harness.py) 說明此 supervisor 會把 `scheduler-state`、`run-fsm`、`failure-stats`、`failed-auto-tasks`、`api-health` 收斂成單一控制面。
- [docs/plans/agent-harness-autonomous-optimization-plan_20260320.md](/D:/Source/daily-digest-prompt/docs/plans/agent-harness-autonomous-optimization-plan_20260320.md) 把改善目標定為「單一控制平面整合狀態與調度判斷」與「將自治決策從腳本內聯判斷提升為獨立、可測、可排程模組」。
- Anthropic 2024 對 agent 的定義是「LLMs using tools based on environmental feedback in a loop」；這與本專案目前由腳本驅動、工具回圈與檔案狀態交接的設計相符，但本專案更偏工程編排而非單純模型回圈。
- Microsoft 2025/2026 將 production agent runtime 描述為連接 model、tool、workflow、observability、trust 的單一 runtime。這與本專案新引入的 `autonomous_harness.py` 控制平面方向一致，但本專案仍屬自管腳本型而非平台型。

### 具體數據
- `docs/ARCHITECTURE.md` 記載 30 個 Skills、20 個自動任務、6 條主要排程。
- `context/adr-registry.json` 摘要顯示截至 2026-03-20 共 31 筆 ADR，其中 23 筆 accepted、20 筆 implementation done。

### 不同實作派別
- 腳本編排派：PowerShell/JSON/state files 驅動，可讀性高、容易熱修，但跨檔耦合與維護成本高。
- 框架 runtime 派：如 LangGraph/Harness/OpenAI SDK，偏向將 loop、checkpoint、tool orchestration 內建化，降低手寫 orchestration 成本。
- 平台服務派：如 Azure AI Foundry Agent Service，把 state、retry、observability、RBAC、network isolation 收入平台能力。

### 爭議點
- 爭議 1：是否應繼續維持 PowerShell 為主的 orchestration。  
  支持維持者認為現行腳本已深度整合 Windows Task Scheduler、現有 state 與 hooks。  
  支持遷移者認為 phase、retry、snapshot、trace 的複雜度已逼近應由專用 runtime 承擔。
- 爭議 2：控制平面應是輕量 supervisor 還是完整 durable runtime。  
  現況僅到「runtime policy + recovery queue」；尚未到「可恢復任意 step 的 durable execution」。

### 來源
- 專案架構文件，作者：專案文件/Claude Code，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md)
- Agent Harness 優化方案，作者：專案計畫文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/plans/agent-harness-autonomous-optimization-plan_20260320.md)
- Autonomous harness supervisor，作者：專案程式碼，2026，[URL](file:///D:/Source/daily-digest-prompt/tools/autonomous_harness.py)
- Building effective agents，作者：Anthropic，2024，<https://www.anthropic.com/research/building-effective-agents/>
- What is Foundry Agent Service?，作者：Microsoft Learn，2026，<https://learn.microsoft.com/en-us/azure/foundry/agents/overview>

---

## 子議題 2：效能瓶頸與延遲來源

### 核心論點
- 目前最大的效能瓶頸不是單一程式語言執行速度，而是 phase 超時、快取命中率偏低、平均 I/O 異常高、以及重型研究型 task 的 timeout 配置保守不足。
- 已知數據顯示本系統的成本熱點集中在 `Phase 2` 長任務與大型輸出，而非 `Phase 1` 的短查詢。
- timeout 已從硬編碼逐步外部化到 `config/timeouts.yaml`，但只是把瓶頸暴露出來，尚未根治上下文膨脹與任務粒度問題。

### 主要論據與證據
- [context/system-insight.json](/D:/Source/daily-digest-prompt/context/system-insight.json) 7 日統計顯示：
  - `daily_success_rate = 0.846`
  - `cache_hit_ratio = 0.207`
  - `avg_io_per_call = 24315`
  - `failure_class_distribution.phase_failure = 31`
  - `failure_class_distribution.timeout = 11`
- 同檔指出 78 次 run 中 12 次失敗，`failure_rate_percent = 15.4%`，且快取僅 `310 hits / 1498 total`。
- [context/continuity/auto-task-system_insight.json](/D:/Source/daily-digest-prompt/context/continuity/auto-task-system_insight.json) 記錄 2026-03-19 一度出現 `auto_task_fairness 1.993`、29 任務僅 6 任務有執行，說明調度不均衡會放大慢任務與重試成本。
- [run-todoist-agent-team.ps1](/D:/Source/daily-digest-prompt/run-todoist-agent-team.ps1) 為研究型任務配置長 timeout：`tech_research = 2600s`、`podcast_create = 2400s`、`shurangama/jiaoguangzong = 1200s`。
- 同檔 `Get-TaskTimeout`、動態 Phase 2 timeout 與 `max timeout + buffer` 策略，證明目前系統已把慢任務視為主要瓶頸來源。
- [docs/audit-reports/系統審查報告_20260311_0900.md](/D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md) 給出「可觀測性 92 分、工作流 92.20 分」，但行覆蓋率僅 10.19%，表示已有監測能力卻還缺自動回歸驗證。
- OpenTelemetry GenAI metrics 對 token usage、duration、time to first token 有標準欄位，意味本專案目前 `avg_io_per_call` 仍屬自訂代理指標，尚未跟標準 token/latency 指標打通。

### 具體數據
- 成功率：84.6%，低於 90% 門檻。
- 快取命中率：20.7%，低於 40% 門檻。
- 平均輸出長度：24315 字元，超過 5000 門檻約 4.9 倍。
- 7 日內失敗類型：`phase_failure=31`、`timeout=11`。
- 典型長任務 timeout：600s、900s、1200s、2400s、2600s。

### 不同實作派別
- timeout 調參派：延長 timeout、加 buffer、加 retry，先求穩定。
- 任務切分派：減少單任務上下文與輸出體積，以更多子任務與中間產物換穩定性。
- 標準觀測派：導入 OTel/GenAI metrics，用 token、TTFT、request duration 取代自訂長度 proxy。

### 爭議點
- 爭議 1：平均輸出長度是否足以代表效能問題。  
  支持者認為它是最直接的 context 壓力代理指標。  
  反對者認為應改用 token usage、TTFT、tool duration、artifact size 分解。
- 爭議 2：快取 TTL 應積極拉長或保守控制。  
  `ADR-20260319-029` 支持提高 TTL；但 TTL 過長會提升資料過時風險。

### 來源
- system-insight 報告，作者：system-insight，2026，[URL](file:///D:/Source/daily-digest-prompt/context/system-insight.json)
- 自動任務 system insight 連續觀察，作者：system-insight，2026，[URL](file:///D:/Source/daily-digest-prompt/context/continuity/auto-task-system_insight.json)
- Todoist orchestrator 程式碼，作者：專案程式碼，2026，[URL](file:///D:/Source/daily-digest-prompt/run-todoist-agent-team.ps1)
- Semantic conventions for generative AI metrics，作者：OpenTelemetry，2025/2026 現行規格頁，[URL](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/)
- OpenTelemetry for Generative AI，作者：OpenTelemetry，2024，[URL](https://opentelemetry.io/blog/2024/otel-generative-ai/)

---

## 子議題 3：可擴展性與模組邊界

### 核心論點
- 專案已具備「加新 Skill、加新 auto-task、加新 prompt」的橫向擴展能力，但 orchestration 層仍高度集中在兩支大型 PowerShell 腳本，形成垂直擴展瓶頸。
- 目前擴展方式是文件驅動與 naming convention 驅動，而不是型別化 workflow graph；這使得新增能力快，但長期一致性依賴規範與審查。
- `autonomous_harness.py`、skill registry、execution trace schema 的引入，代表架構正在從「腳本擴展」向「可治理控制平面」轉型。

### 主要論據與證據
- [docs/ARCHITECTURE.md](/D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md) 明示 `new-auto-task.ps1` 與 `generate-arch-diagrams.ps1`，反映新能力是透過模板與配置擴增，而不是改核心 runtime。
- [docs/audit-reports/系統審查報告_20260311_0900.md](/D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md) 對 2.4 可擴展性給 86 分，但同時指出 prompts/team 與 templates 存在同步維護負擔。
- [context/adr-registry.json](/D:/Source/daily-digest-prompt/context/adr-registry.json) 內的 `ADR-20260320-033` 接受建立 machine-readable skill registry；`ADR-20260320-034` 接受 prompt/template 版本追蹤，這兩者都是為了降低擴展後的漂移。
- `run-todoist-agent-team.ps1` 中有大量 alias 與 task key 正規化邏輯，顯示系統已用映射表處理新任務接入，但也反映模組邊界尚未完全型別化。
- Anthropic 2024 主張最成功的 agent 系統常用「simple, composable patterns」而非複雜 framework；本專案採文件驅動與 Skill 組合，屬此派。
- Microsoft Foundry 2026 與 LangGraph 1.0 則代表另一派：把 orchestration、tool lifecycle、retry、visibility 內建到框架/平台中，以治理換取擴展一致性。

### 具體數據
- `context/system-insight.json` 顯示總 Skills 48、實際使用 41、coverage 85.4%，代表能力面已相當大。
- `docs/ARCHITECTURE.md` 說明團隊模式 prompt 至少 36 個、核心+工具 Skill 約 30+，屬大規模 prompt/skill 生態。

### 不同實作派別
- 文件驅動擴展派：易上手、可快速增量。
- workflow graph 派：明確節點/邊界/狀態遷移，適合大型生態。
- managed runtime 派：將可擴展性問題轉成平台配置問題。

### 爭議點
- 爭議 1：是否要把 prompt/template 包裝層進一步合併。  
  贊成者認為可減少重複。  
  反對者擔心會降低 task-specific prompt 的可觀察性與獨立優化能力。
- 爭議 2：Skill 應保持人類可讀 frontmatter 還是轉成 registry-first。  
  前者利於編輯，後者利於 tooling 與驗證。

### 來源
- 架構文件，作者：專案文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md)
- ADR registry，作者：專案架構治理，2026，[URL](file:///D:/Source/daily-digest-prompt/context/adr-registry.json)
- 系統審查報告，作者：system-audit，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md)
- Building effective agents，作者：Anthropic，2024，<https://www.anthropic.com/research/building-effective-agents/>
- LangGraph 1.0 is now generally available，作者：LangChain Team，2025，<https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available>

---

## 子議題 4：錯誤恢復機制與故障隔離

### 核心論點
- 本專案已經不是「失敗即整批報錯」的簡單腳本，而是有 Circuit Breaker、FSM、retry、fallback、failed-auto-task registry、recovery queue 的多層韌性設計。
- 但現況仍偏「腳本級補救」而非真正 durable execution；尤其 Phase 2 snapshot 恢復與獨立 recovery worker 仍在 proposal/partial 階段。
- 主要故障隔離策略是把 Phase 失敗、API 失敗、timeout、circuit open 分類記錄，再對 timeout 做有限度重試，避免整批重跑。

### 主要論據與證據
- [run-agent-team.ps1](/D:/Source/daily-digest-prompt/run-agent-team.ps1) 與 [run-todoist-agent-team.ps1](/D:/Source/daily-digest-prompt/run-todoist-agent-team.ps1) 均有：
  - `Update-FailureStats`
  - `Set-FsmState`
  - stale `running > 2h -> timeout`
  - scheduler-state 損毀時自動備份重建
- `run-todoist-agent-team.ps1` 明列 `Phase 2 retry — 僅對 timeout 重試 1 次，30s backoff`，並可將 Codex/OpenRouter/Claude timeout 切換到 `cursor_cli` 或備援 backend。
- 同檔有 `quota-fallback`、`sandbox-fallback`、`result_file_missing` 自動補記與 `failed-auto-tasks.json`。
- [docs/agent-harness-autonomy-troubleshooting_20260320.md](/D:/Source/daily-digest-prompt/docs/agent-harness-autonomy-troubleshooting_20260320.md) 已把失敗情境明文化為：
  - runtime policy 未生成
  - CPU/memory 指標為 null
  - auto-task 未被 supervisor 偵測
  - pytest 因 ACL 失敗
  - recovery queue 持續堆積
- `ADR-20260318-028` 提案「Phase 2 快照恢復與故障續跑」，目標是讓成功率從 85.1% 提高到 95%+，證明目前 durability 仍是明確缺口。
- LangGraph durable execution 要求 persistence、thread id、deterministic/idempotent task 封裝；其三種 durability mode（exit/async/sync）正好對應本專案未來可選的恢復語義。
- Microsoft Agent Framework durable agent 文件明確把「persist state automatically」與「resume after failures」列為 durable agent 核心能力，本專案目前尚未達到這種保證等級。

### 具體數據
- 失敗分類：7 日內 `phase_failure = 31`、`timeout = 11`。
- stale FSM 逾時清理門檻：2 小時。
- `scheduler-state.json` 保留最近 200 筆 run。
- Phase 2 timeout 只重試 1 次，backoff 30 秒。

### 不同實作派別
- 腳本補償派：retry + fallback + 補寫 result file。
- checkpoint/durable 派：每個 step checkpoint，允許 resume。
- queue/worker 派：獨立 consumer 消費 recovery queue，避免主流程扛太多修復責任。

### 爭議點
- 爭議 1：重試應只針對 timeout，還是擴展到 parse error / transient API error。  
  現行設計保守，避免重試放大錯誤；但也可能漏掉可恢復失敗。
- 爭議 2：補寫 `partial_success` result file 是否會掩蓋真實失敗。  
  支持者認為能避免 Phase 3 組裝中斷。  
  反對者擔心會稀釋 incident 診斷訊號。

### 來源
- run-agent-team.ps1，作者：專案程式碼，2026，[URL](file:///D:/Source/daily-digest-prompt/run-agent-team.ps1)
- run-todoist-agent-team.ps1，作者：專案程式碼，2026，[URL](file:///D:/Source/daily-digest-prompt/run-todoist-agent-team.ps1)
- 故障排除指南，作者：專案文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/agent-harness-autonomy-troubleshooting_20260320.md)
- ADR registry，作者：專案架構治理，2026，[URL](file:///D:/Source/daily-digest-prompt/context/adr-registry.json)
- Durable execution，作者：LangChain Docs，2025/2026，[URL](https://docs.langchain.com/oss/javascript/langgraph/durable-execution)
- Azure Functions (Durable) for agents，作者：Microsoft Learn，2026，[URL](https://learn.microsoft.com/en-us/agent-framework/tutorials/agents/orchestrate-durable-agents)

---

## 子議題 5：資源管理與成本控制

### 核心論點
- 本專案已開始把資源管理從隱性成本轉成顯性治理：包括 timeout budget、auto-task 降載、CPU/memory/GPU 快照、快取 TTL、自動化 runtime policy。
- 成本壓力主要來自長任務 token、重型 auto-task 並行度、重複 WebSearch/WebFetch、以及高 I/O 導致的 context 膨脹。
- `autonomous_harness.py` 已具備依資源快照和 gate 輸出 `normal / degraded / recovery` 的能力，但尚未做細粒度 token-based admission control。

### 主要論據與證據
- [tools/autonomous_harness.py](/D:/Source/daily-digest-prompt/tools/autonomous_harness.py) 會蒐集 CPU、memory、GPU 資訊並生成 runtime policy。
- [run-todoist-agent-team.ps1](/D:/Source/daily-digest-prompt/run-todoist-agent-team.ps1) 在 runtime policy 生效時會調整 auto-tasks，並過濾 heavy/research tasks。
- [docs/plans/agent-harness-autonomous-optimization-plan_20260320.md](/D:/Source/daily-digest-prompt/docs/plans/agent-harness-autonomous-optimization-plan_20260320.md) 明確把「資源自調整」列為驗收條件之一。
- [context/system-insight.json](/D:/Source/daily-digest-prompt/context/system-insight.json) 顯示 `cache_hit_ratio = 20.7%`，說明目前大量請求沒有被 cache 吸收。
- `ADR-20260319-029` 接受調整 TTL：`pingtung-news 360→720`、`hackernews 180→360`、`knowledge 60→120`，代表成本治理已採自適應 TTL 路線。
- OpenTelemetry GenAI metrics 建議用 `gen_ai.client.token.usage`、`gen_ai.client.operation.duration` 等標準指標；本專案目前尚未直接記錄 billable token，因此成本可視性仍不完整。
- Microsoft Foundry 把 observability、RBAC、network isolation、tool orchestration 納入同一 runtime，顯示資源管理若提升到平台層，可與安全、可觀測性共同治理。

### 具體數據
- 高 I/O：平均 24315 字元/次。
- 快取命中率：20.7%，距 40% 目標仍有 19.3 個百分點落差。
- 長任務 timeout：最高 2600 秒。
- `autonomous_harness.py` 外部檢測 timeout 常見值：5 秒、10 秒、30 秒，代表 supervisor 本身設計成短檢查路徑。

### 不同實作派別
- timeout-budget 派：用秒數與並行度治理。
- token-budget 派：直接以 token usage、billable token、context window 比例治理。
- resource-adaptive 派：結合 CPU/memory/GPU、queue length、task class 動態降載。

### 爭議點
- 爭議 1：應優先治理 token 還是系統資源。  
  本專案目前偏系統資源與 timeout；但對 LLM 成本來說 token 才是直接成本。
- 爭議 2：runtime policy 是否應由 supervisor 強制，還是由 phase 腳本可選套用。  
  強制可提高穩定性；可選則保留任務完成率。

### 來源
- autonomous_harness.py，作者：專案程式碼，2026，[URL](file:///D:/Source/daily-digest-prompt/tools/autonomous_harness.py)
- Agent Harness 優化方案，作者：專案計畫文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/plans/agent-harness-autonomous-optimization-plan_20260320.md)
- system-insight 報告，作者：system-insight，2026，[URL](file:///D:/Source/daily-digest-prompt/context/system-insight.json)
- ADR registry，作者：專案架構治理，2026，[URL](file:///D:/Source/daily-digest-prompt/context/adr-registry.json)
- Semantic conventions for generative AI metrics，作者：OpenTelemetry，2025/2026，[URL](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/)

---

## 子議題 6：測試覆蓋與驗證策略

### 核心論點
- 專案的測試成熟度呈現「數量夠多、分布不均」：已有 682 個測試，但核心 PowerShell orchestrator 與部分 JS 模組仍缺自動化測試。
- 目前驗證策略大量依賴 system-audit、quality gate、schema validation、手動運維檢查，屬於「多層驗證但不完全單元化」。
- 下一階段重點不是盲目增加測試數，而是把高風險 orchestration 與 hooks 的分支行為補成可回歸驗證。

### 主要論據與證據
- [docs/audit-reports/系統審查報告_20260311_0900.md](/D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md) 記錄 682 個測試、模組覆蓋率 100%，但行覆蓋率僅 10.19%。
- 同報告指出「為核心 PS1 腳本建立 Pester 測試」是明確改善建議。
- `ADR-20260318-026` 已接受 results/*.json schema 驗證 warning-only；說明目前驗證策略重心在輸出契約而不是流程模擬。
- `ADR-20260224-003`、`ADR-20260224-002` 分別把 results schema 與 done-cert schema 視為 Handoff 與 Guardrails 的核心。
- [docs/agent-harness-autonomy-troubleshooting_20260320.md](/D:/Source/daily-digest-prompt/docs/agent-harness-autonomy-troubleshooting_20260320.md) 已記錄 `pytest` 可能因 temp 目錄 ACL 失敗，表示 CI/本機驗證環境一致性仍有缺口。
- `uv run python tools/autonomous_harness.py --format json` 在本機本次實測失敗於 `uv` cache 權限，證明執行環境本身也是驗證策略的一部分，不能只看測試碼存在與否。
- pytest 官方 good practices 建議使用 `pyproject.toml`、虛擬環境、editable install、`src` layout 與 strict mode；本專案已有 `pyproject.toml`，但測試策略仍偏混合式。

### 具體數據
- 測試數：682。
- 行覆蓋率：10.19%。
- 高風險缺口：PowerShell orchestrator、JS 模組、環境 ACL/uv cache 問題。

### 不同實作派別
- 契約驗證派：schema、done-cert、quality gate。
- 單元測試派：對 hooks、Python utility、state transform 做可重複測試。
- orchestration/integration 派：用 Pester、端到端排程模擬驗證 phase 串接與 timeout 行為。

### 爭議點
- 爭議 1：應先補 PowerShell Pester 還是先補 Python hooks 覆蓋率。  
  hooks 易測且回報快；但真正高風險在 orchestrator。
- 爭議 2：warning-only schema 驗證是否過鬆。  
  對生產不中斷友善，但可能延後發現格式回歸。

### 來源
- 系統審查報告，作者：system-audit，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md)
- ADR registry，作者：專案架構治理，2026，[URL](file:///D:/Source/daily-digest-prompt/context/adr-registry.json)
- 故障排除指南，作者：專案文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/agent-harness-autonomy-troubleshooting_20260320.md)
- Good Integration Practices，作者：pytest documentation，現行版，[URL](https://docs.pytest.org/en/stable/explanation/goodpractices.html)

---

## 子議題 7：部署自動化與環境一致性

### 核心論點
- 本專案目前部署能力在「單機 Windows 自動化」上成熟，在「跨平台/容器/多環境」上刻意保守。
- `setup-scheduler.ps1` + `HEARTBEAT.md` 提供了穩定的本機排程部署模式，但這是一種環境特化而非普適 deployment model。
- 未來若 harness 從個人助理升級成團隊或服務化系統，現行 Windows-only 假設會變成主要約束。

### 主要論據與證據
- [docs/ARCHITECTURE.md](/D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md) 記錄 6 條排程全依賴 Windows Task Scheduler 與 PowerShell 腳本。
- [docs/audit-reports/系統審查報告_20260311_0900.md](/D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md) 對部署就緒給 88 分，但技術棧跨平台相容性只給 60 分。
- `ADR-20260311-014` 明確把跨平台排程抽象層標記為 `Wontfix`，理由是系統設計為 Windows-only 個人助理。
- `ADR-20260311-013` 與 `ADR-20260314-016` 接受 GitHub Actions 最小 CI 與 ruff lint，代表非排程型部署自動化正在補齊。
- OpenHarness 研究筆記指出其官方目前沒有成熟的 Dockerfile/Compose/Helm/K8s 標準交付，說明即使外部 agent runtime 也不一定天然具備企業部署路徑。
- GitHub Docs 官方推薦 `actions/setup-python`、依賴安裝、`pytest` 與 artifact 上傳，適合補足本專案目前偏手動的 CI 缺口。

### 具體數據
- 排程 6 條。
- 部署就緒得分：88。
- 跨平台相容性：60。

### 不同實作派別
- 單機排程派：最貼近日常實用，維運成本低。
- CI runner 派：把任務改為 GitHub Actions/CI job 執行。
- 平台/容器派：Kubernetes Job、Durable Functions、平台 agent service。

### 爭議點
- 爭議 1：Windows-only 是合理邊界還是技術債。  
  目前作為個人系統合理；若要服務化則會升格為技術債。
- 爭議 2：應否先做容器化。  
  支持者認為能提升一致性；反對者指出此專案綁定本機 CLI、Scheduler、Windows counter，容器收益未必高。

### 來源
- 架構文件，作者：專案文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md)
- 系統審查報告，作者：system-audit，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md)
- ADR registry，作者：專案架構治理，2026，[URL](file:///D:/Source/daily-digest-prompt/context/adr-registry.json)
- Harness Agent 深度研究報告，作者：專案研究文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/research/harness-agent-architecture-workflow_20260320.md)
- Building and testing Python，作者：GitHub Docs，現行版，[URL](https://docs.github.com/actions/language-and-framework-guides/using-python-with-github-actions)

---

## 子議題 8：監控、可觀測性與告警

### 核心論點
- 本專案已建立比一般腳本系統更成熟的可觀測性：`scheduler-state`、`run-fsm`、`failure-stats`、`structured jsonl logs`、`system-insight`、`health report`、`ntfy` 告警、`execution trace schema` 規劃。
- 真正缺口不在「有沒有資料」，而在「是否已與統一 trace schema、標準 GenAI telemetry、跨 phase 因果關聯」打通。
- 目前的觀測層是自建輕量框架，策略是先可用再逐步向 OTel 語義相容靠攏。

### 主要論據與證據
- [docs/audit-reports/系統審查報告_20260311_0900.md](/D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md) 給 `可觀測性 92 分`，並提到三層日誌體系、56 個 state JSON 與 Hook 自動記錄。
- [context/system-insight.json](/D:/Source/daily-digest-prompt/context/system-insight.json) 已提供成功率、快取、block rate、fairness、I/O、behavior patterns、skill heatmap。
- `ADR-20260304-009` 決定採用「自建輕量級指標聚合 + Span 記錄（OTel 語義相容）」。
- `ADR-20260319-030` 提案統一 execution trace schema，目標是把 `task_key`、`skill chain`、`cache 狀態`、`耗時`、`失敗點`、`artifact` 串到單一 trace。
- OpenTelemetry GenAI 規格現已覆蓋 model spans、agent spans、events、metrics 與 MCP semantic conventions；本專案若要標準化，已有明確對齊目標。
- Microsoft Foundry 把 observability 定義為 full conversation-level visibility；本專案目前已有 thread/run 層資料，但 agent-to-agent message 還未完全結構化。

### 具體數據
- tool calls：14301。
- blocked count：9，block rate 0.06%。
- behavior patterns：200，高信心 151。
- skill reads：1016，前 2 名是 `ntfy-notify=158`、`knowledge-query=157`。

### 不同實作派別
- 自建輕量派：最快貼合現場需求。
- OTel 標準派：利於跨系統工具整合。
- 平台可觀測派：用 Foundry/Application Insights/Langfuse 等整合後端。

### 爭議點
- 爭議 1：現在就全面 OTel 化，還是先把自建 trace schema 定穩。  
  全面 OTel 有互通性；先內部 schema 可降低改造風險。
- 爭議 2：是否要將 prompt/template/version 也視為 telemetry 主鍵。  
  若不做，回歸分析會缺乏版本因果。

### 來源
- system-insight 報告，作者：system-insight，2026，[URL](file:///D:/Source/daily-digest-prompt/context/system-insight.json)
- 系統審查報告，作者：system-audit，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md)
- ADR registry，作者：專案架構治理，2026，[URL](file:///D:/Source/daily-digest-prompt/context/adr-registry.json)
- Semantic conventions for generative AI systems，作者：OpenTelemetry，2025/2026，[URL](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- Semantic conventions for GenAI agent and framework spans，作者：OpenTelemetry，2025/2026，[URL](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- What is Foundry Agent Service?，作者：Microsoft Learn，2026，[URL](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)

---

## 子議題 9：安全性、權限與資料保護

### 核心論點
- 本專案安全架構以 hooks 與權限預檢為核心，採「本機 agent 高權限，但用 pre/post tool guard 做防線」的模式。
- 這種模型在本機單機場景實用，但隨著 agent 自主性增強，風險會從傳統 secrets 外洩擴展到 tool misuse、goal hijacking、privilege abuse、cross-prompt injection。
- 因此未來安全重點會從靜態 secrets/路徑保護，轉向「agent intent 對齊 + tool call governance + auditability」。

### 主要論據與證據
- [docs/ARCHITECTURE.md](/D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md) 記載 hooks 至少包含 `pre_bash_guard.py`、`pre_write_guard.py`、`pre_read_guard.py`、`post_tool_logger.py`、`on_stop_alert.py`、`cjk_guard.py` 等多層守護。
- [docs/audit-reports/系統審查報告_20260311_0900.md](/D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md) 給資安 82 分，證據包括 11 個 Hook、零硬編碼密碼、HTTPS 外部 API，但指出依賴安全與日誌脫敏仍待補強。
- `context/system-insight.json` 的 `block_rate = 0.0006`，表示 hook 防護實際在攔截操作。
- OWASP 2025 Agentic AI Top 10 指出 agentic 風險已擴展到 `Agent Behavior Hijacking`、`Tool Misuse and Exploitation`、`Identity and Privilege Abuse`。
- Microsoft Task Adherence 2025/2026 明確把「planned tool invocations 是否符合 user intent」作為 agent workflow safety 能力，這是本專案目前尚未系統化的能力。
- Foundry 2026 把 trust 定義為 Entra/RBAC、content filters、encryption、network isolation。相比之下，本專案目前更像單機防護而非企業零信任治理。

### 具體數據
- 資安總分：82。
- Hook 數量：11。
- block rate：0.06%。

### 不同實作派別
- hook guard 派：在 tool 執行點做細粒度本機攔截。
- policy engine 派：以 RBAC、intent verification、task adherence 為主。
- platform trust 派：把 identity、network、encryption、content filter 交給平台。

### 爭議點
- 爭議 1：對單機專案而言，hook guard 是否已足夠。  
  在個人環境通常足夠；但一旦引入更多外部工具或自動化交易，風險模型會改變。
- 爭議 2：warning-only 還是 fail-fast。  
  安全風險高時應 fail-fast；但過多阻擋會降低自動化效益。

### 來源
- 架構文件，作者：專案文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/ARCHITECTURE.md)
- 系統審查報告，作者：system-audit，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/audit-reports/系統審查報告_20260311_0900.md)
- system-insight 報告，作者：system-insight，2026，[URL](file:///D:/Source/daily-digest-prompt/context/system-insight.json)
- OWASP GenAI Security Project Releases Top 10 Risks and Mitigations for Agentic AI Security，作者：Scott Clinton，2025，<https://genai.owasp.org/2025/12/09/owasp-genai-security-project-releases-top-10-risks-and-mitigations-for-agentic-ai-security/>
- Quickstart: Use Task Adherence for your Agent Workflows，作者：Microsoft Learn，2025/2026，[URL](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/quickstart-task-adherence)
- What is Foundry Agent Service?，作者：Microsoft Learn，2026，[URL](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)

---

## 子議題 10：未來演進路線與技術債治理

### 核心論點
- 本專案的下一階段演進主軸已相當明確：把現有大量「局部優化」整合成控制平面、trace schema、registry、durable recovery 與自治 gate 的連續治理體系。
- 技術債不在基本功能缺失，而在 orchestration 複雜度、治理訊號分散、流程版本追溯不足，以及 durability 尚未完整。
- ADR 已構成有效的治理骨架，未來應從單點改善提案，升級為以 SLO、trace completeness、fairness、cache efficiency、success rate 驅動的 roadmap。

### 主要論據與證據
- [context/adr-registry.json](/D:/Source/daily-digest-prompt/context/adr-registry.json) 摘要顯示：
  - 總 ADR：31
  - accepted：23
  - done：20
  - immediate_fix：4
- 當前最直接相關的 accepted/proposed 項目包括：
  - `ADR-20260319-029`：快取命中率調優與自適應 TTL
  - `ADR-20260320-032`：SLO/Error Budget 治理
  - `ADR-20260320-033`：Machine-readable Skill Registry
  - `ADR-20260320-034`：Prompt/模板版本追蹤
  - `ADR-20260318-028`：Phase 2 快照恢復與故障續跑
  - `ADR-20260319-030`：統一 execution trace schema 與因果追蹤
- [docs/plans/agent-harness-autonomous-optimization-plan_20260320.md](/D:/Source/daily-digest-prompt/docs/plans/agent-harness-autonomous-optimization-plan_20260320.md) 的後續待做已指向：
  - 將更多風險判斷改由 supervisor 提供
  - 納入更多 guard
  - 建立 scheduler/heartbeat 接入
- `context/system-insight.json` 的核心痛點也已量化：成功率 84.6%、快取 20.7%、avg I/O 24.3KB，這三者可作為 roadmap 的北極星指標。
- Anthropic 2024 強調應以簡單可組合模式構建 agent；這提醒未來演進不應只追求更多功能，而要避免把 harness 變成無法維護的大框架。

### 建議的三階段路線
- 第 1 階段，穩定性治理：
  - 完成 `Phase 2 snapshot/resume`
  - 完成 `failure taxonomy + SLO/error budget`
  - 把 `autonomous_harness.py` 接入正式排程
- 第 2 階段，可觀測與治理統一：
  - 落地 execution trace schema
  - 補齊 prompt/template/version mapping
  - 將 token/cost 與 trace 結合
- 第 3 階段，架構收斂：
  - 重新評估是否保留 PowerShell 為主 orchestrator
  - 規劃 registry-first skill/tool/workflow model
  - 視需求決定導入 durable graph/runtime 或維持輕量 supervisor

### 不同實作派別
- 漸進治理派：保留現有腳本，逐步補控制平面與治理訊號。
- 架構重整派：把 orchestration 遷到 Python/runtime graph。
- 平台化派：以 Foundry/LangGraph/其他 agent runtime 重構執行層。

### 爭議點
- 爭議 1：現在應先修成功率還是先修架構。  
  短期必須先修成功率與 timeout；但若不處理 trace/durability，成功率很難持續提升。
- 爭議 2：是否要從自建 runtime 演化到外部 agent 平台。  
  自建保有控制力；平台化可快速取得 durability、RBAC、observability，但也引入遷移成本與供應商耦合。

### 來源
- ADR registry，作者：專案架構治理，2026，[URL](file:///D:/Source/daily-digest-prompt/context/adr-registry.json)
- Agent Harness 優化方案，作者：專案計畫文件，2026，[URL](file:///D:/Source/daily-digest-prompt/docs/plans/agent-harness-autonomous-optimization-plan_20260320.md)
- system-insight 報告，作者：system-insight，2026，[URL](file:///D:/Source/daily-digest-prompt/context/system-insight.json)
- Building effective agents，作者：Anthropic，2024，<https://www.anthropic.com/research/building-effective-agents/>

---

## 總結觀察

- 現有 agent harness 已具備 production-oriented 雛形：phase orchestration、state persistence、retry/fallback、hook guard、system insight、runtime policy 都已存在。
- 最大缺口不是功能缺，而是「治理層尚未完全統一」：trace schema、snapshot recovery、registry、版本追溯、token/cost telemetry 都還在分散演進。
- 若以 2026-03-20 為時間點判斷，最合理路線不是全面推翻現有 PowerShell harness，而是先把 `autonomous_harness.py + trace schema + snapshot recovery + SLO治理` 做完，再決定是否升級為框架型或平台型 runtime。
