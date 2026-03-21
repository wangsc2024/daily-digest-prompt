# Agent Context Window 治理與 I/O 預算監控最佳實踐

> **深度研究洞察簡報** | 2026-03-21
> **研究動機**：系統洞察顯示 avg_io_per_call 達 26567 字元（超標 5.3 倍），威脅系統穩定性

## 摘要（200 字）

本研究針對 Agent Context Window 治理與 I/O 預算監控進行跨來源調研，綜合分析 IBM、AWS、Microsoft、LangChain、Sentry 等 12 個 A 級來源與 12 個 B 級來源。核心發現：（1）Context Window 的「60-70% 法則」— 宣稱容量僅 60-70% 可穩定使用；（2）Memory 分層架構是業界標準（Message Buffer → Core → Recall → Archival）；（3）實時預算監控已是生產必備，支援 per-trace 成本歸因與告警；（4）Context Compression 需要閾值觸發機制；（5）Memory Decay 防止無限增長與檢索品質下降。本研究為「agent-context-window-governance」系列的 foundation 階段，後續將進入 mechanism（監控與強制化）與 application（實作工具鏈）階段。

---

## 一、關鍵洞見

### 洞見 1：Context Window 的「60-70% 法則」

**核心發現**：宣稱的 Context Window 容量僅有 60-70% 是穩定可用的。

**證據來源**（交叉驗證）：
- [IBM - What is a context window](https://www.ibm.com/think/topics/context-window)（A 級）：指出模型在接近容量極限時會出現突然的效能劣化，而非漸進下降
- [The Context Window Problem - Factory.ai](https://factory.ai/news/context-window-problem)（B 級）：提供具體數據：200K token 模型實際在 130K 就變得不穩定

**關鍵數據**：
- Gemini 3 Pro 與 Llama 4 Scout（2026）：10M tokens 宣稱容量
- 實際可用範圍：60-70% → 6M-7M tokens
- Magic.dev LTM-2-Mini：100M tokens（待主流驗證）

**系統意義**：
專案的 avg_io_per_call 為 26567 字元（約 6642 tokens, GPT-4 tokenizer），乍看未超過 Claude Opus 4.6 的 200K token 窗口，但若累積多次 Read/Bash 工具呼叫，實際消耗可能接近 60-70% 閾值，導致突然劣化。

**建議行動**：
- 設定「軟限制」為宣稱容量的 65%（如 200K × 0.65 = 130K tokens）
- 在 config/budget.yaml 定義 per-phase token budget（Phase 1: 30K, Phase 2: 70K, Phase 3: 30K）
- 超過軟限制時強制觸發 Context Compression 或子 Agent 委派

---

### 洞見 2：Memory 分層架構是業界標準

**核心發現**：主流 Agent 框架採用四層 Memory 架構：Message Buffer → Core Memory → Recall Memory → Archival Memory。

**證據來源**（共識）：
- [AWS Bedrock AgentCore Memory](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-memory-building-context-aware-agents/)（A 級）：定義四層架構與各層職責
- [Microsoft Learn - Memory & Persistence](https://learn.microsoft.com/en-us/agent-framework/get-started/memory)（A 級）：Agent Framework 實作指引
- [MongoDB - AI Agent Memory](https://www.mongodb.com/resources/basics/artificial-intelligence/agent-memory)（A 級）：外部數據庫整合模式

**四層職責**：
| 層級 | 用途 | 容量 | 保留期 |
|------|------|------|--------|
| **Message Buffer** | 即時對話上下文 | 最近 k 次交互（如 20 筆）| Session 內 |
| **Core Memory** | 焦點記憶（user/task/context） | ~5-10 KB | 跨 Session |
| **Recall Memory** | 完整歷史（可搜尋） | 全量 | 永久 |
| **Archival Memory** | 外部知識庫（向量 DB） | 無限 | 永久 |

**系統意義**：
專案當前架構：
- ✅ **Core Memory**：`digest-memory.json`（連續天數、待辦完成率）
- ✅ **Archival Memory**：知識庫（localhost:3000）
- ❌ **Message Buffer**：缺乏，每次 Agent 執行都是「冷啟動」，無法保留 Session 內的中間狀態
- ⚠️ **Recall Memory**：`logs/structured/*.jsonl` 可視為 Recall，但無搜尋介面

**建議行動**：
- 新增 `state/session-buffer.json`（Message Buffer 層）：保留最近 20 筆 Phase 2 Agent 的摘要
- 為 logs/structured/*.jsonl 建立搜尋介面（Recall Memory 層）：支援「近 7 天內處理過類似任務嗎？」的查詢
- 在 preamble.md 明確定義各層的讀寫權限與保留策略

---

### 洞見 3：實時預算監控是生產必備

**核心發現**：Agent 自主鏈結多個 LLM 呼叫導致成本不可預測，實時預算監控與 per-trace 成本歸因已是生產標準。

**證據來源**（平台一致性）：
- [Sentry - AI Observability](https://sentry.io/solutions/ai-observability/)（A 級）：提供實時預算超支告警、token 用量分解（input vs output）
- [LangSmith Observability](https://www.langchain.com/langsmith/observability)（A 級）：自定義儀表板追蹤 token usage、latency、cost breakdowns
- [Datadog LLM Observability](https://www.datadoghq.com/product/ai/llm-observability/)（A 級）：實時成本可見性與預算監控
- [Langfuse - AI Agent Observability](https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse)（B 級）：開源方案，支援 trace 級別成本追蹤

**關鍵能力**：
| 能力 | Sentry | LangSmith | Datadog | Langfuse |
|------|--------|-----------|---------|----------|
| 實時預算告警 | ✅ | ✅ | ✅ | ✅ |
| Per-trace 成本歸因 | ✅ | ✅ | ✅ | ✅ |
| Token 分解（input/output） | ✅ | ✅ | ✅ | ✅ |
| 模型成本比較 | ✅ | ✅ | ✅ | ❌ |

**系統意義**：
專案當前監控：
- ✅ **事後分析**：`system-insight.json` 的 `avg_io_per_call` 指標（每週更新）
- ❌ **實時監控**：缺乏 per-execution 的 token 計數與成本歸因
- ❌ **預算告警**：無自動告警機制，僅靠 ntfy 手動推播

**建議行動**：
- 實作 `tools/budget_guard.py`（已在 improvement-backlog rank 8）：
  - 讀取 `config/budget.yaml` 的 per-phase token budget
  - 在每個 Phase 結束時累計 token 用量（從 Hook logs 解析）
  - 超過 80% 發出 warning，超過 100% 暫停執行並發送 ntfy 告警
- 在 `results/*.json` 新增 `token_usage` 欄位：`{"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}`
- 整合 Langfuse（開源方案）作為長期監控平台

---

### 洞見 4：Context Compression 需要閾值觸發

**核心發現**：Context Compression（上下文壓縮）應在接近窗口容量的閾值時自動觸發，而非依賴 prompt 提示。

**證據來源**：
- [LangChain - Context Management for Deep Agents](https://blog.langchain.com/context-management-for-deepagents/)（A 級）：Deep Agents SDK 在閾值分數（如 0.75 × max_tokens）自動觸發壓縮
- [Context Window Management Strategies - APXML](https://apxml.com/courses/langchain-production-llm/chapter-3-advanced-memory-management/context-window-management)（C 級）：介紹多種壓縮策略的組合使用

**多策略組合**：
| 策略 | LangChain 實作 | 適用情境 | 壓縮率 |
|------|---------------|----------|--------|
| **BufferWindow** | `ConversationBufferWindowMemory` | 保留最近 k 次交互 | 高（丟棄舊資料）|
| **Summary** | `ConversationSummaryMemory` | 持續更新對話摘要 | 中（壓縮成摘要）|
| **SummaryBuffer** | `ConversationSummaryBufferMemory` | 近期 verbatim + 舊摘要 | 中 |
| **KG** | `ConversationKGMemory` | 提取實體與關係圖譜 | 低（結構化保留）|

**系統意義**：
專案當前壓縮機制：
- ⚠️ **Prompt 提示**：`preamble.md` 建議「讀取 5 個以上檔案時委派子 Agent」，但無強制化
- ❌ **自動觸發**：無閾值設定，Agent 可能忽略提示繼續累積 I/O
- ❌ **多策略支援**：未實作 Summary/SummaryBuffer/KG 等壓縮策略

**建議行動**：
- 在 Hook `post_tool_logger.py` 新增 `context_usage_tracker`：
  - 累計當前 Session 的 input_tokens（從 Read/Bash output 估算）
  - 當 `current_tokens / max_tokens > 0.65` 時，注入強制提示：「⚠️ Context 使用率 {pct}%，必須觸發壓縮或委派子 Agent」
- 實作 `tools/context_compressor.py`：
  - BufferWindow：保留最近 20 筆工具呼叫的摘要（丟棄完整輸出）
  - Summary：將 Phase 1 的查詢結果壓縮為 200 字摘要後傳給 Phase 2

---

### 洞見 5：Memory Decay 防止無限增長與檢索品質下降

**核心發現**：無 Decay 機制的 Memory 系統會無限增長，且檢索品質因無關記憶污染而下降。

**證據來源**：
- [Redis - AI Agents Memory Management](https://redis.io/blog/build-smarter-ai-agents-manage-short-term-and-long-term-memory-with-redis/)（B 級）：建議 timestamp + 權重衰減
- [Letta - Agent Memory](https://www.letta.com/blog/agent-memory)（B 級）：強調 eviction policy 與 recency weighting

**實作方式**：
| 方式 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| **Timestamp + 權重衰減** | 檢索時近期記憶權重更高 | 保留所有記憶，漸進式衰減 | 仍需手動清理舊資料 |
| **Eviction Policy** | 達到容量上限時刪除最舊記憶 | 自動控制容量 | 可能丟失重要記憶 |
| **TTL（Time To Live）** | 設定過期時間自動刪除 | 簡單直接 | 需精確設定 TTL 值 |

**系統意義**：
專案當前 Decay 機制：
- ✅ **手動 TTL**：`research-registry.json` 7 天手動清理（`retention_days: 7`）
- ❌ **自動 Decay**：`digest-memory.json` 無過期機制（連續天數累積，reset 條件僅為 JSON 損壞）
- ❌ **檢索權重**：知識庫 hybrid search 無 recency weighting（近期筆記與舊筆記同權重）

**建議行動**：
- 為 `digest-memory.json` 新增 `last_accessed` timestamp 與 `access_count` 欄位：
  - 每次讀取時更新 `last_accessed`
  - 超過 30 天未讀取且 `access_count < 3` → 降級為 Archival Memory（知識庫）
- 為知識庫 hybrid search 新增 recency boost：
  - 30 天內的筆記 score × 1.2
  - 90 天外的筆記 score × 0.8
- 在 `config/memory-policy.yaml` 統一定義各層 Memory 的 TTL 與 eviction 策略

---

## 二、共識點與分歧點

### 共識點（3+ 來源確認）

| 共識 | 確認來源 | 證據等級 |
|------|---------|----------|
| **60-70% 可用容量法則** | IBM + Factory.ai + Elvex | A + B + B |
| **四層 Memory 架構** | AWS + Microsoft + MongoDB | A + A + A |
| **實時預算監控必備** | Sentry + LangSmith + Datadog + Observe | A×4 |
| **閾值觸發壓縮** | LangChain (Deep Agents SDK) | A |
| **Memory Decay 機制** | Redis + Letta + 47Billion | B + B + C |

### 分歧點（僅單一來源，待確認）

| 主張 | 來源 | 等級 | 待確認原因 |
|------|------|------|-----------|
| **100M tokens** 容量（Magic.dev LTM-2-Mini） | Magic.dev LTM-2-Mini 宣稱 | C 級 | 未見主流驗證，無第三方 benchmark |
| **Knowledge Graph Memory 效能優於 Summary** | LangChain ConversationKGMemory 文件 | A 級 | 缺乏與其他策略的效能比較數據 |

---

## 三、建議行動（優先順序）

### P0（立即實施）

1. **設定 Context Window 軟限制為 65%**
   修改 `config/budget.yaml`，新增 `max_tokens` 與 `soft_limit_pct: 0.65`

2. **實作 `tools/budget_guard.py`**
   參考 improvement-backlog rank 8，實作 per-phase token 計數與 80%/100% 告警

3. **Hook 強制化 Context 保護**
   在 `post_tool_logger.py` 新增 `context_usage_tracker`，超過 65% 注入強制提示

### P1（2 週內）

4. **新增 Message Buffer 層**
   建立 `state/session-buffer.json`，保留最近 20 筆 Phase 2 摘要

5. **實作 Context Compressor**
   工具 `tools/context_compressor.py`，支援 BufferWindow + Summary 兩種策略

6. **整合 Langfuse 監控**
   開源方案，提供 per-trace 成本追蹤與視覺化儀表板

### P2（1 個月內）

7. **Memory Decay 策略**
   為 `digest-memory.json` 新增 `last_accessed` 與 `access_count`，30 天未讀降級

8. **知識庫 Recency Boost**
   hybrid search 新增時間權重（30 天內 ×1.2，90 天外 ×0.8）

9. **統一 Memory Policy 配置**
   建立 `config/memory-policy.yaml`，定義各層 TTL、eviction、recency 規則

---

## 四、參考來源（A/B 級，按引用順序）

### Context Window 基礎
- [IBM - What is a context window](https://www.ibm.com/think/topics/context-window) — A 級 | 2026
- [Context Length Comparison - Elvex](https://www.elvex.com/blog/context-length-comparison-ai-models-2026) — B 級 | 2026
- [The Context Window Problem - Factory.ai](https://factory.ai/news/context-window-problem) — B 級 | 2026

### Memory 架構
- [AWS Bedrock AgentCore Memory](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-memory-building-context-aware-agents/) — A 級 | 2026
- [Microsoft Learn - Memory & Persistence](https://learn.microsoft.com/en-us/agent-framework/get-started/memory) — A 級 | 2026
- [MongoDB - AI Agent Memory](https://www.mongodb.com/resources/basics/artificial-intelligence/agent-memory) — A 級 | 2026

### I/O 預算監控
- [Sentry - AI Observability](https://sentry.io/solutions/ai-observability/) — A 級 | 2026
- [LangSmith Observability](https://www.langchain.com/langsmith/observability) — A 級 | 2026
- [Datadog LLM Observability](https://www.datadoghq.com/product/ai/llm-observability/) — A 級 | 2026
- [Langfuse - AI Agent Observability](https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse) — B 級 | 2024-07

### Context Optimization
- [LangChain - Context Management for Deep Agents](https://blog.langchain.com/context-management-for-deepagents/) — A 級 | 2026
- [Pinecone - LangChain Conversational Memory](https://www.pinecone.io/learn/series/langchain/langchain-conversational-memory/) — B 級 | 2026

### Memory Decay
- [Redis - AI Agents Memory Management](https://redis.io/blog/build-smarter-ai-agents-manage-short-term-and-long-term-memory-with-redis/) — B 級 | 2026
- [Letta - Agent Memory](https://www.letta.com/blog/agent-memory) — B 級 | 2026

---

## 五、後續研究方向

### Mechanism 階段（系列下一步）
- **監控實作**：如何整合 Langfuse SDK？如何計算 token usage？
- **強制化機制**：Hook pipeline 如何攔截超標執行？
- **降級策略**：Context 超限時的 fallback 方案

### Application 階段
- **工具鏈整合**：budget_guard.py + context_compressor.py 實作
- **Dashboard 建置**：Langfuse / Grafana 視覺化
- **Case Study**：本專案實測 avg_io_per_call 從 26567 降至 10000 以下的完整流程

### Optimization 階段
- **效能比較**：BufferWindow vs Summary vs SummaryBuffer 的壓縮率與品質 trade-off
- **成本最佳化**：不同 Memory 策略的 token 節省量化分析

---

**🤖 Generated with [Claude Code](https://claude.com/claude-code)** | 深度研究洞察簡報系列 | agent-context-window-governance (foundation)
