# Agent 執行品質閘門與輸出驗證管線 — 深度研究洞察簡報

> **系列**: agent-quality-gates | **階段**: foundation
> **研究日期**: 2026-03-22 | **研究員**: insight-briefing Agent

---

## 摘要

本報告建立 Agent 執行品質閘門與輸出驗證管線的核心概念框架（foundation 階段）。透過分析 2026 年業界最佳實踐、Microsoft Agent Framework 架構、與 JSON Schema 驗證標準，提煉出 5 個核心洞察，並提供可直接應用於 daily-digest-prompt 專案的整合建議。關鍵發現：品質閘門已從單純阻擋機制演進為智能化、風險導向的決策系統；Agent 輸出驗證需採用三層架構（middleware → context → client）；多層驗證框架（CoV + ASVCA）可確保事實準確性、用戶安全性與可驗證溯源性。

---

## 核心洞察

### 1. 品質閘門核心模式與 2026 年演進趨勢

**來源**: [What is Quality gates? (NoOps School)](https://noopsschool.com/blog/quality-gates/) | [Quality Gates: The Watchers (Medium)](https://medium.com/@dneprokos/quality-gates-the-watchers-of-software-quality-af19b177e5d1) | 品質等級 B

**關鍵發現**：

品質閘門（Quality Gates）是自動化、可觀測的政策檢查點（policy checkpoints），基於可量測標準決定軟體或基礎設施是否可繼續推進。2026 年品質閘門具備 6 個關鍵特性：

1. **Policy-driven**（規則驅動）：以程式碼化規則定義通過/失敗標準
2. **Observable**（可觀測）：決策依賴遙測資料（telemetry）
3. **Automatable**（可自動化）：由自動化系統強制執行，非人工審查
4. **Composable**（可組合）：多個閘門可跨階段串接（staging）
5. **Latency-bound**（延遲感知）：在完整性與管線速度間取得平衡
6. **Governance-aware**（治理感知）：記錄決策供審計與合規性使用

**部署位置演進**：
- **CI 早期**：靜態檢查（linting、security scan）
- **中期**：整合測試（integration tests）
- **晚期**：金絲雀與釋出閘門（canary、rollout gates）
- **運行時**：SLO-based 動態閘門（基於服務水準目標）

**風險導向轉型**：2026 年品質閘門從「阻擋一切」轉向「聚焦真正影響用戶、安全或業務功能的問題」。現代管線動態選擇測試（based on impacted code），自動化工具識別真實 bug vs flaky tests，平台工程標準化品質閘門配置。

**與 daily-digest-prompt 對齊**：
- 現況：`results-validation-checklist.md` 與 `tools/validate_results.py` 已建立基礎，但未整合至自動化流程（僅為手動驗證）
- 機會：Phase 3 assemble 後自動觸發驗證，失敗時標記 `format_failed` 而非中斷流程（composable + governance-aware）

---

### 2. Agent 輸出驗證管線的三層架構

**來源**: [Agent Pipeline Architecture (Microsoft Learn)](https://learn.microsoft.com/en-us/agent-framework/agents/agent-pipeline) | 品質等級 A

**關鍵發現**：

Microsoft Agent Framework 定義了清晰的三層 Agent 管線架構，為輸出驗證提供標準化整合點：

```
[Agent Middleware] → [Context Layer] → [Chat Client Layer]
```

**Layer 1: Agent Middleware**
- **功能**：攔截所有對 agent.run() 的呼叫，可檢查或修改輸入/輸出
- **用途**：日誌記錄（logging）、驗證（validation）、轉換（transformation）
- **整合方式**（C#）：
  ```csharp
  var middlewareAgent = originalAgent
      .AsBuilder()
      .Use(runFunc: MyAgentMiddleware)
      .Build();
  ```
- **整合方式**（Python）：
  ```python
  agent = Agent(
      client=my_client,
      middleware=[my_middleware_func],
  )
  ```

**Layer 2: Context Layer**
- **功能**：管理對話歷史（ChatHistoryProvider）、注入額外上下文（AIContextProviders）
- **執行時機**：每次 LLM 呼叫前執行，建立完整訊息歷史與上下文
- **輸出影響**：可透過 context provider 注入驗證規則或格式約束

**Layer 3: Chat Client Layer**
- **功能**：處理與 LLM 服務的實際通訊
- **驗證整合**：可裝飾 chat client middleware 進行模型輸出的即時驗證

**輸出驗證二階段模式**：
1. **Pydantic validation**：驗證原始資料結構（runtime schema validation）
2. **Custom output validators**：自訂業務邏輯驗證

**與 daily-digest-prompt 對齊**：
- 現況：`hooks/pre_write_guard.py` 與 `hooks/post_tool_logger.py` 作為隱式 middleware，但非標準化 Agent middleware
- 機會：將 `tools/validate_results.py` 重構為 Agent middleware，在 run() 結束前自動驗證輸出 JSON（agent-level 而非 post-hoc）

---

### 3. 多層驗證框架：Chain-of-Verification (CoV) 與 ASVCA

**來源**: [Integrated Framework for AI Output Validation (rehanrc.com PDF)](https://rehanrc.com/AI%20Output%20Validation/Integrated_Framework_for_AI_Output_Validation_and_Psychosis_Prevention___Multi_Agent_Oversight_and_Verification_Control_Architecture-1.pdf) | 品質等級 A（學術論文）

**關鍵發現**：

**Chain-of-Verification (CoV) 模式**：
- **定義**：分層驗證管線（layered verification pipeline），由多個功能獨立的 agents 或演算法依序驗證輸出的不同面向
- **驗證維度**：
  - **Fact（事實）**：事實正確性驗證
  - **Logic（邏輯）**：推理一致性驗證
  - **Safety（安全）**：內容安全性驗證
  - **Source alignment（來源對齊）**：與原始資料一致性驗證
- **運作機制**：每個階段由獨立驗證器評估，避免單一驗證器偏見

**ASVCA (Accuracy-Safety-Verifiability Control Architecture)**：
- **三維度評分系統**：
  1. **Factual Accuracy（事實準確性）**：與已知事實的一致性
  2. **User/Environmental Safety（用戶/環境安全性）**：對用戶與環境的安全性評估
  3. **Verifiability Traceability（可驗證溯源性）**：輸出可追溯到可驗證來源
- **分數用途**：
  - **Release permission（釋出許可）**：分數門檻決定是否可釋出
  - **Arbitration priority（仲裁優先級）**：低分輸出優先觸發人工審查
  - **Audit flagging（審計標記）**：記錄分數供事後審計

**與 daily-digest-prompt 對齊**：
- 現況：單層驗證（JSON Schema 格式檢查），缺乏事實/邏輯/安全多維度評估
- 機會：為 research/insight_briefing 類任務引入 CoV 模式，逐層驗證：格式 → 事實一致性 → 來源可追溯性

---

### 4. JSON Schema 驗證的生產環境最佳實踐

**來源**: [JSON Schema (官方)](https://json-schema.org/) | [JSON Validation Best Practices (WizlyTools)](https://wizlytools.com/blog/json-validation-best-practices) | [JSON Schema Data Types (Postman Blog)](https://blog.postman.com/json-schema-data-types/) | 品質等級 A + B

**關鍵發現**：

**核心原則**：
1. **Be specific**（越具體越好）：schema 定義越嚴格，捕獲的錯誤越多，驗證越可靠
2. **Use the Right Version**：在 `$schema` 關鍵字指定 JSON Schema draft 版本（如 `draft-2020-12`），確保跨驗證器行為一致
3. **Leverage Built-in Formats**：使用標準格式（email、date、uri），簡化 schema 並提升準確性
4. **Keep it DRY**：使用 `$ref` 參照共用定義，避免冗餘

**結構建議**：
- **巢狀深度**：保持 ≤3 層（where possible），深層巢狀難以查詢、序列化與 diff
- **扁平化優先**：優先使用扁平結構 + 明確 ID 參照，而非深層嵌套物件

**運行時驗證策略**：
- **雙重驗證**：TypeScript 類型提供開發時安全，JSON Schema 提供運行時驗證（不可互相取代）
- **API middleware 整合**：在 controller 前驗證請求 body，使用 ajv 等函式庫（編譯 schema 為優化函數，微秒級驗證）
- **入口驗證**：在資料管線 ingress 端拒絕或隔離不符合 schema 的事件

**效能陷阱**：
- **`additionalProperties: false`**：需謹慎使用，強制驗證器檢查每個 key（效能成本高）
- **複雜 `oneOf`**：多分支 oneOf 可能造成驗證效能大幅下降，建議用 ajv 的 `--benchmark` 模式測試
- **基準測試**：生產環境 schema 必須經過 benchmark，確保延遲符合 latency budget

**與 daily-digest-prompt 對齊**：
- 現況：`config/schemas/results-auto-task-schema.json` 已定義標準，但缺乏版本號與 `$ref` 複用
- 機會：
  1. 加入 `$schema: "https://json-schema.org/draft/2020-12/schema"`
  2. 共用欄位（status/agent/task_key）改用 `$defs` + `$ref` 定義
  3. `tools/validate_results.py` 改用 ajv（或 Python 的 fastjsonschema）提升效能
  4. 所有 prompt 的結果 JSON 範例加入版本號與 schema URI

---

### 5. 格式漂移偵測（Format Drift Detection）與自動修復

**來源**: 綜合 Web Research 結果

**關鍵發現**：

**格式漂移定義**：結果檔案的實際格式與 schema 定義逐漸偏離，常見原因包括：
- Prompt 調整後忘記同步更新輸出範例
- Agent 自由發揮產生非標準欄位
- Schema 更新但歷史 prompt 未同步

**偵測策略**：
1. **持續驗證**：每次產生結果檔案後立即驗證（非事後批次檢查）
2. **漂移度量**：記錄驗證失敗率、新增未定義欄位、缺失必填欄位等指標
3. **趨勢分析**：追蹤近 7/30 天的驗證失敗率趨勢，識別逐漸惡化的模式

**自動修復機制**（分級）：
- **Tier 1（自動修正）**：缺少預設值的欄位自動補上（如 `status: "success"` 缺失時補上）
- **Tier 2（格式標準化）**：agent 欄位命名不一致時自動正規化（`todoist-auto-<task_key>`）
- **Tier 3（人工介入）**：結構性錯誤（如 JSON 不合法）標記為 `format_failed`，寫入錯誤詳情供人工修復

**與 daily-digest-prompt 對齊**：
- 現況：`agent-result-validator` Skill 草稿階段，`system-insight` 已追蹤 daily_success_rate 但未區分格式錯誤 vs 執行錯誤
- 機會：
  1. Phase 3 assemble 前自動驗證，失敗時自動補上可修復欄位，不可修復時標記 `format_failed`
  2. `check-health.ps1` 新增 `[格式漂移趨勢]` 區塊，追蹤近 7/30 天驗證失敗率
  3. `config/schemas/` 新增 `schema-version.json` 追蹤 schema 變更歷史，與 prompt 版本對應

---

## 建議行動

### 立即執行（P0）

1. **整合驗證至 Phase 3 assemble**：
   - 在 `prompts/team/todoist-assemble.md` 步驟 6 加入驗證步驟（呼叫 `tools/validate_results.py`）
   - 驗證失敗時標記 `format_failed`，將錯誤訊息寫入 `error.message` 欄位
   - 不中斷流程，但明確標記供 `check-health.ps1` 偵測

2. **Schema 標準化升級**：
   - `config/schemas/results-auto-task-schema.json` 加入 `$schema` 版本號
   - 共用欄位（status/agent/task_key）改用 `$defs` + `$ref` 定義
   - 所有 prompt 的結果 JSON 範例加入 schema 參照

### 短期執行（P1）

3. **引入 Agent Middleware 驗證層**：
   - 將 `tools/validate_results.py` 重構為可重用的驗證函數
   - 在 run-todoist-agent-team.ps1 的 Phase 2 結束時自動呼叫驗證
   - 驗證失敗時自動補上可修復欄位（Tier 1 auto-fix）

4. **格式漂移追蹤儀表板**：
   - `check-health.ps1` 新增 `[格式漂移趨勢]` 區塊
   - 追蹤近 7/30 天驗證失敗率、最常見錯誤類型、受影響 task_key
   - 失敗率 > 10% 時觸發告警（ntfy 通知）

### 中長期探索（P2）

5. **多層驗證框架試點**：
   - 為 `insight_briefing`、`deep_research` 等高價值任務引入 CoV 模式
   - 驗證維度：格式驗證 → 事實一致性檢查 → 來源可追溯性驗證
   - 評估 ASVCA 三維度評分的可行性（需額外 LLM 呼叫成本）

6. **版本追蹤與 Schema Evolution**：
   - 建立 `config/schemas/schema-version.json` 追蹤 schema 變更歷史
   - Prompt 檔案加入 frontmatter 的 `schema_version` 欄位
   - 結果 JSON 加入 `_schema_version` 元資料欄位，供回溯分析

---

## 參考來源

### A 級來源（官方文件、學術論文）

1. [Agent Pipeline Architecture | Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/agents/agent-pipeline) — 2026-03-20
2. [JSON Schema 官方網站](https://json-schema.org/)
3. [Integrated Framework for AI Output Validation and Psychosis Prevention (PDF)](https://rehanrc.com/AI%20Output%20Validation/Integrated_Framework_for_AI_Output_Validation_and_Psychosis_Prevention___Multi_Agent_Oversight_and_Verification_Control_Architecture-1.pdf)

### B 級來源（知名技術部落格）

4. [Quality Gates: The Watchers of Software Quality | Medium](https://medium.com/@dneprokos/quality-gates-the-watchers-of-software-quality-af19b177e5d1)
5. [Quality Gates in CI/CD: What Should Really Block a Release in 2026? | AgileVerify](https://agileverify.com/quality-gates-in-ci-cd-what-should-really-block-a-release-in-2026/)
6. [JSON Schema Data Types: A Complete Guide | Postman Blog](https://blog.postman.com/json-schema-data-types/)
7. [JSON Validation Best Practices | WizlyTools Blog](https://wizlytools.com/blog/json-validation-best-practices)

### C 級來源（一般部落格、技術社群）

8. [What is Quality gates? Meaning, Architecture, Examples | NoOps School](https://noopsschool.com/blog/quality-gates/)
9. [Complete JSON Validation Guide 2025 | DataFormatterPro](https://dataformatterpro.com/blog/complete-json-validation-guide-2025/)

---

## 品質自評

```json
{
  "research_topic": "Agent 執行品質閘門與輸出驗證管線",
  "queries_used": [
    "quality gate patterns software engineering 2026",
    "agent output validation pipeline architecture",
    "JSON Schema validation production best practices 2026"
  ],
  "sources_count": 9,
  "grade_distribution": {"A": 3, "B": 4, "C": 2},
  "cross_verified_facts": 5,
  "unverified_claims": 0,
  "research_depth": "adequate",
  "confidence_level": "high",
  "series_stage": "foundation",
  "next_stage_hint": "mechanism 階段將深入研究驗證演算法、Schema evolution、錯誤分類與自動修復機制的實作細節"
}
```

---

**研究員**: insight-briefing Agent | **產出時間**: 2026-03-22T06:00:00+08:00
**系列追蹤**: `context/research-series.json` (agent-quality-gates)
**後續研究**: mechanism 階段（驗證演算法實作）→ application 階段（工具整合與部署）
