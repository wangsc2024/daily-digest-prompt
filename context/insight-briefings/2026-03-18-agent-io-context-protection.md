# Agent I/O 預算超標與 Context 保護機制失效 — 根因分析框架與診斷清單

> **研究日期**: 2026-03-18
> **研究類型**: 深度研究洞察簡報
> **來源品質**: 13 個來源（A 級 6 個、B 級 7 個）
> **信心度**: High

---

## 摘要

本報告針對 Daily-Digest-Prompt 系統當前面臨的 P0 問題（Agent I/O 達 24875 chars，超標近 5 倍；preamble.md Context 保護規則執行率低）進行根因分析。透過整合學術研究（BudgetThinker, NoLiMa）、業界最佳實踐（Anthropic, LangChain, VS Code）與最新研究（JetBrains 2025），建立系統化的診斷框架與改進清單。

**核心發現**：Context 保護機制失效的根本原因並非缺乏規則定義，而是缺乏**預算監控層**、**強制執行機制**與**簡單有效的保護模式**。業界共識指向「Context 最小化原則」與「Sub-agent delegation」，而非填滿 context window。

---

## 關鍵洞見

### 1. Context 最小化原則：「最少必要資訊」勝過「填滿 window」

**證據來源**: [Anthropic 官方文件](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | [Getmaxim.ai](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/)

Andrej Karpathy（前 OpenAI 研究員）稱之為「填充 context window 的精緻藝術與科學」。核心原則：**給 LLM 完成任務所需的最少資訊**。

- **反模式**：「盡可能多地填充 context」實際上是壞實踐，會導致 context bloat、效能下降與成本暴增
- **正確做法**：主動篩選與壓縮，只保留任務必要資訊
- **量化證據**：JetBrains 研究發現，即使是簡單的 observation masking（遮罩非必要輸出），也能**減少 50% 成本**，且不影響功能

**對本系統的啟示**：
- 當前 24875 chars I/O 中，有多少比例是「非必要資訊」？
- preamble.md 規則未執行的根因可能是：規則過於「建議性」，缺乏量化閾值與強制機制

---

### 2. Sub-agent Delegation：業界標準的 Context 保護模式

**證據來源**: [Claude Code 官方文件](https://code.claude.com/docs/en/sub-agents) | [LangChain 文件](https://docs.langchain.com/oss/python/deepagents/subagents) | [VS Code Copilot](https://code.visualstudio.com/docs/copilot/agents/subagents)

Sub-agent delegation 已成為跨平台共識（LangChain, Vectara, VS Code, Claude Code 均採用），核心價值：

1. **Context 隔離**：子 Agent 維護獨立對話歷史，父 Agent 只看最終摘要，從不看中間推理或工具結果
2. **專業化**：每個子 Agent 可有獨特指令、工具配置與行為模式
3. **並行執行**：父 Agent 可並行調用多個子 Agent，減少端到端時間
4. **可重用性**：一旦建立穩固的子 Agent，任何父 Agent 都可調用

**量化效益**：
- **Context 壓縮比**：當工具輸出龐大時（web search, file reads, database queries），子 Agent 可將數千 tokens 的中間結果壓縮為 ≤ 200 tokens 的摘要
- **防止 context pollution**：避免多任務資訊交叉污染導致模型混淆

**對本系統的啟示**：
- preamble.md 已定義「Context 保護：重量操作委派子 Agent」規則
- 執行率低可能原因：(1) 缺乏自動觸發條件（如「讀取 5+ 檔案」時強制委派）；(2) 主 Agent 不清楚何時該委派；(3) 缺乏委派成本/收益的即時反饋

---

### 3. Progressive Disclosure：讓 Agent 自主導航，而非一次性載入

**證據來源**: [Anthropic 官方文件](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

Progressive disclosure（漸進式揭露）允許 Agent 透過探索**逐步發現相關 context**：
- 每次互動產生的 context 為下一次決策提供資訊
- 檔案大小暗示複雜度；命名慣例暗示目的；時間戳可作為相關性代理
- Agent 一層層組裝理解，只在工作記憶中保留必要內容，並善用筆記策略提供額外持久性

**對比傳統做法**：
- ❌ 傳統：一次性載入整個專案目錄 → context 爆滿
- ✅ Progressive：Agent 先列目錄 → 選擇相關檔案 → 再讀取內容 → context 精簡

**對本系統的啟示**：
- 檢查 Agent 是否有「先 Glob 再 Read」的習慣，還是直接 Read 大量檔案
- 是否提供導航工具（如 Grep 搜尋關鍵字後再 Read）

---

### 4. BudgetThinker：首創「週期性 Control Tokens」告知模型剩餘預算

**證據來源**: [BudgetThinker 論文](https://openreview.net/forum?id=ahatk5qrmB) (OpenReview, A 級學術論文)

BudgetThinker 是一種新穎框架，讓 LLM 具備預算感知推理能力：
- **機制**：在推理過程中**週期性插入特殊 control tokens**，持續告知模型剩餘 token 預算
- **效果**：模型能精確控制思考過程長度，在預算內完成任務
- **創新點**：首次將預算控制從外部約束轉為模型內部感知

**對本系統的啟示**：
- 可借鑑「預算可見化」概念：讓 Agent 在每次工具調用後看到 I/O 累積值與剩餘預算
- 可在 Prompt 中注入動態預算提示（如「當前 I/O 已用 15K/20K chars，請謹慎選擇工具」）

---

### 5. Observation Masking > LLM 摘要：簡單策略勝過複雜方案

**證據來源**: [JetBrains Research 2025](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)

JetBrains 比較兩種 context 管理策略：
- **Observation Masking（觀察遮罩）**：簡單遮蔽非必要工具輸出
- **LLM Summarization（LLM 摘要）**：用 LLM 將長輸出壓縮為摘要

**實證結果**：
- 兩種策略都能**減少 50% 成本**（相對於無管理）
- **但 Masking 更優**：成本更低（不需額外 LLM 調用）、可靠性更高（摘要可能遺漏關鍵資訊）

**對本系統的啟示**：
- **優先採用簡單策略**：與其讓 Agent 自己摘要，不如在 Hook 層直接截斷/遮罩過長輸出
- **範例**：`pre_bash_guard.py` 可限制 `cat` 輸出長度，超過 5K chars 時強制截斷或改用 `head`

---

### 6. Context Bloat 導致非線性效能下降

**證據來源**: [NoLiMa 研究](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/)

長 context 評估研究 NoLiMa 發現：**對多數流行 LLM，效能隨 context 長度增加而顯著下降**。

- **非線性惡化**：不是線性的 10% context → 10% 效能下降，而是指數級劣化
- **根本原因**：LLM 的注意力機制在超長 context 中會「迷失」關鍵資訊（needle in haystack 問題）

**對本系統的啟示**：
- 超標 5 倍的 I/O 不僅是成本問題，更是**效能與準確度問題**
- 24875 chars 可能已進入效能劣化區（需實測驗證）

---

### 7. 分層預算管理：從組織到用戶的多層控制

**證據來源**: [LLMOps Cost Management](https://oneuptime.com/blog/post/2026-01-30-llmops-cost-management/view)

業界推薦實施**組織/團隊/專案/用戶**多層級預算：
- **組織層**：總預算上限
- **團隊層**：按團隊分配 quota
- **專案層**：按專案限制
- **用戶層**：防止單一用戶消耗過多資源

**對本系統的啟示**：
- 可實施 **Agent 層級預算**：每個自動任務（todoist-auto-*, daily-digest-*）設定 I/O 上限
- 超限時自動觸發降級策略（如強制委派子 Agent、停止執行並告警）

---

## 根因分析框架（5 Whys）

針對「I/O 超標 5 倍」與「Context 保護規則執行率低」：

### Why 1: 為何 I/O 超標 5 倍？
**答**：Agent 在執行過程中讀取了大量檔案/日誌，未經篩選或壓縮。

### Why 2: 為何 Agent 會讀取大量檔案？
**答**：Prompt 中可能有「審查所有日誌」「分析整個專案」等寬泛指令，未指定範圍。

### Why 3: 為何 Prompt 缺乏範圍限制？
**答**：Prompt 設計時未考慮 I/O 預算，假設「越多資訊越好」。

### Why 4: 為何 preamble.md 規則未被執行？
**答**：規則是「建議性」的（should, consider），缺乏強制觸發條件與量化閾值。

### Why 5: 為何缺乏強制機制？
**答**：系統架構中**缺少預算監控層**與**自動降級層**。

---

## 診斷清單（Checklist）

### 即時診斷
- [ ] 查詢最近 24 小時內 I/O > 20K chars 的 Agent 執行記錄（`logs/structured/*.jsonl`）
- [ ] 分析這些執行中哪些工具調用佔比最高（Read, Grep, Bash）
- [ ] 統計「讀取 5+ 檔案」的執行中，有多少實際委派了子 Agent

### 架構缺口
- [ ] 系統是否有即時 I/O 計數器？（每次工具調用後累積）
- [ ] Prompt 中是否有動態預算提示？（如「剩餘 5K/20K chars」）
- [ ] Hook 層是否有 I/O 截斷機制？（如 `pre_bash_guard.py` 限制 `cat` 輸出）
- [ ] 是否有 Agent 層級預算配置？（`config/agent-budget.yaml`）

### Prompt 設計
- [ ] 是否有「先 Glob/Grep 後 Read」的指引？
- [ ] 是否有「超過 3 個檔案必須委派子 Agent」的強制規則？
- [ ] 是否有「優先使用 Grep 而非 Read 大檔」的優先級指引？

---

## 建議行動

### 短期（P0，1-2 天）
1. **新增 I/O 預算監控 Hook** (`hooks/io_budget_monitor.py`)
   - 每次 Read/Bash 調用後累積 I/O 計數
   - 超過 15K chars 時記錄 warning
   - 超過 20K chars 時發送 ntfy 告警

2. **強化 preamble.md 規則**
   - 將「should consider」改為「must delegate when reading 5+ files」
   - 加入量化閾值（如「單次 Read > 2K chars 時考慮 Grep 篩選」）

3. **分析歷史日誌**
   - 運行 `uv run python hooks/query_logs.py --days 7 --filter io_intensive` 找出高 I/O Agent
   - 針對性優化這些 Agent 的 Prompt

### 中期（P1，1 週）
1. **實施 Agent 層級預算配置**
   - 建立 `config/agent-budget.yaml`
   - 為每個自動任務設定 I/O 上限（如 `todoist-auto-*: 10K`, `daily-digest-*: 15K`）

2. **優化 Prompt 設計**
   - 加入「Progressive Disclosure」指引
   - 範例：「先 Glob 列出檔案 → 選擇最相關 3 個 → 再 Read」

3. **建立子 Agent 委派範本**
   - 標準化子 Agent Prompt 格式
   - 提供委派成本/收益的即時反饋（如「委派子 Agent 可節省 8K chars」）

### 長期（P2，2-4 週）
1. **引入 BudgetThinker 概念**
   - 在 Prompt 中注入動態預算提示
   - 範例：`[BUDGET] 已用 15K/20K chars (75%), 請謹慎選擇工具`

2. **實施 Observation Masking**
   - 在 Hook 層自動截斷過長工具輸出
   - 範例：`cat large_file.log` 自動改為 `head -n 100 large_file.log`

3. **建立效能基準測試**
   - 測試不同 context 長度下的 Agent 效能（準確度、成本、延遲）
   - 找出本系統的「效能劣化臨界點」

---

## 參考來源

### A 級來源（學術論文 / 官方文件）
1. [BudgetThinker: Empowering Budget-aware LLM Reasoning with Control Tokens](https://openreview.net/forum?id=ahatk5qrmB) — OpenReview 學術論文
2. [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Anthropic 官方工程文件
3. [Create custom subagents - Claude Code Docs](https://code.claude.com/docs/en/sub-agents) — Claude Code 官方文件
4. [Subagents - LangChain Docs](https://docs.langchain.com/oss/python/deepagents/subagents) — LangChain 官方文件
5. [Subagents in Visual Studio Code](https://code.visualstudio.com/docs/copilot/agents/subagents) — VS Code 官方文件
6. [Context windows - Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/context-windows) — Claude API 官方文件

### B 級來源（知名技術部落格 / 研究機構）
1. [Context Window Management Strategies](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/) — Getmaxim.ai（含 NoLiMa 研究引用）
2. [Efficient Context Management (JetBrains Research)](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) — JetBrains Research 2025
3. [LLM Context Management Guide](https://eval.16x.engineer/blog/llm-context-management-guide) — 16x.engineer
4. [LLM Token Optimization](https://redis.io/blog/llm-token-optimization-speed-up-apps/) — Redis 官方部落格
5. [Introducing Sub-agents](https://www.vectara.com/blog/introducing-sub-agents) — Vectara 技術部落格
6. [How to Build Cost Management for LLM Operations](https://oneuptime.com/blog/post/2026-01-30-llmops-cost-management/view) — OneUptime LLMOps 指南
7. [Enhancing Spec Kit with Subagent Delegation](https://github.com/github/spec-kit/discussions/912) — GitHub Spec-kit 討論

---

## 研究方法論

- **搜尋策略**: 3 組多角度查詢（預算管理、保護模式、最佳實踐）
- **來源篩選**: 優先 A/B 級（官方文件、學術論文、知名技術部落格）
- **交叉驗證**: 至少 2 個來源確認同一事實才視為可靠
- **研究深度**: Thorough（13 個來源，6 個 A 級，7 個 B 級，8 個交叉驗證事實）
- **信心等級**: High

---

**研究者**: insight_briefing Agent
**研究系列**: Agent I/O Budget & Context Protection（foundation 階段）
**下一階段建議**: 進入 mechanism 階段 — I/O 預算計算演算法、Context 保護機制實作細節
