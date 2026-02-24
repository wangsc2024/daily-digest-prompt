# learn-claude-code 深度研究報告

> **研究對象**：https://github.com/shareAI-lab/learn-claude-code
> **研究日期**：2026-02-24
> **研究目的**：提取可應用於 daily-digest-prompt 系統架構優化的創新洞察

---

## 一、專案概覽

| 指標 | 數值 |
|------|------|
| GitHub Stars | 17,502 |
| Forks | 3,700 |
| 主要語言 | Python（Agent）+ TypeScript（Web） |
| 課程階段 | 12 個（s01–s12） |
| 文件語言 | 英文、中文、日文 |
| 開源許可 | MIT |

**核心定位**：「從 0 到 1 建構 nano Claude Code 代理」——透過 12 個漸進式階段，用最小代碼揭示代理系統的本質原理。標語致敬 Karpathy 的「Bash is all you need」，表達極簡哲學。

---

## 二、7 大創新特色與對本系統的啟示

### 創新 1：+1 原則（Progressive Layering）

**learn-claude-code 的做法**

12 個 session，每次只新增「一個機制」，核心迴圈永不重寫：

```
s01：基礎 while 迴圈（84 行）
s02：+工具分發
s03：+規劃（Plan before you act）
s04：+子代理
s05：+技能注入
...
s12：+多代理協調
```

**對本系統的啟示**

每次 system-audit 產出 5–10 條改進建議，但目前缺乏機制決定「本次執行哪 1 條」。技術債和改進建議堆積卻難以逐步消化。

→ **落地建議**：arch-evolution Skill 的 OODA 模組 D 採用 +1 原則——每次調度選出 1 條 `effort=low/medium` 的 ADR 執行，確保改進有序推進。

---

### 創新 2：OODA 閉環（Observe→Orient→Decide→Act）

**learn-claude-code 的做法**

s11（自主代理）明確實作 OODA 閉環：感測環境 → 分析狀態 → 規劃行動 → 執行 → 回到感測，持續迭代。

**對本系統的啟示**

本系統已有三個自省 auto-task，但各自獨立：

```
system-insight（執行品質感測）  → execution_order=16
system-audit（維度評分診斷）    → 每日 00:40
self-heal（異常修復執行）        → execution_order=17
```

三者缺乏統一的「Decide」層，無法形成明確的 OODA 閉環。

→ **落地建議**：arch-evolution Skill 的模組 D 充當「Decide」層——整合前兩者輸出，明確決定本輪行動優先級。

---

### 創新 3：ADR 精神（Architecture Decision Records）

**learn-claude-code 的做法**

每個 session 都有明確的問題陳述、解決方案、設計決策說明。為什麼 s09 用 JSONL 而非 Redis？文件裡都有解釋。

**對本系統的啟示**

system-audit 每次產出建議（`improvement-backlog.json`），但：
- 不知道哪條被採納、哪條被拒絕
- 不知道為什麼被拒絕
- 下次 audit 重複提出相同建議（因為不知道已被決策）

→ **落地建議**：arch-evolution Skill 的模組 A 將 improvement-backlog 的 P0/P1 建議轉化為持久化 ADR，追蹤決策狀態（Proposed/Accepted/Rejected/Superseded）。

---

### 創新 4：顯式依賴聲明

**learn-claude-code 的做法**

每個 session 的 README 明確列出「本 session 需要哪個前置 session」，無隱式依賴。

**對本系統的啟示**

21 個 Skills 中只有 4 個宣告 `depends-on`，但實際隱式依賴更多：
- `github-scout` 隱式依賴 `web-research`（使用 research-registry）
- `system-audit` 隱式依賴 `knowledge-query`（寫入 RAG）
- `kb-curator` 隱式依賴 `knowledge-query`（讀取 KB）

→ **落地建議**：arch-evolution Skill 的模組 C 掃描所有 SKILL.md 推斷隱式依賴，產出補強建議。

---

### 創新 5：心智模型優先（Mental-Model-First）

**learn-claude-code 的做法**

所有文件遵循固定結構：
1. What are we solving?（問題）
2. Core pattern（解法）
3. ASCII 圖示（視覺化）
4. Runnable example（最小代碼）

結合線上視覺化平台（https://learn-claude-agents.vercel.app/），進一步降低認知負擔。

**對本系統的啟示**

技術債的 FIXME/TODO 散落在代碼庫各處，缺乏可視化優先度呈現。使用者無法快速判斷「最值得修復的前 3 條是什麼」。

→ **落地建議**：arch-evolution Skill 的模組 B 按 P1/P2 優先級整理技術債，並在報告末尾突出顯示「長期未處理（age_days > 7）」。

---

### 創新 6：多語言文件同步

**learn-claude-code 的做法**

英文、中文、日文文件同步維護，3 語言完整度相同。

**對本系統的啟示**

SKILL.md 全為中文，但部分技術術語（如 circuit breaker、OODA、ADR）需要一致的中文化標準。

→ **落地建議**（低優先）：在 `config/` 建立術語標準化表，確保跨 Skill 術語一致。

---

### 創新 7：最小化實現揭示本質

**learn-claude-code 的做法**

s01 的基礎 Agent 只有 84 行 Python。這個刻意限制揭示了一個重要原則：**生產複雜性通常來自業務需求，而非技術必要性**。

**對本系統的啟示**

daily-digest-prompt 已有 20 個 Skills、18 個 auto-tasks、5 個 Hooks，複雜度已很高。在新增功能前，應問：「這是業務必要的複雜性，還是偶發性複雜性？」

→ **落地建議**：arch-evolution Skill 的每次 OODA 調度報告，加入一個「複雜度健康度」指標——SKILL.md 平均行數、auto-tasks 總執行次數趨勢，提醒避免過度工程化。

---

## 三、架構對比分析

| 面向 | learn-claude-code | daily-digest-prompt |
|------|-------------------|---------------------|
| **定位** | 教育型（揭示原理） | 生產型（業務自動化） |
| **Agent 架構** | 12 階段漸進式 | Skill 驅動 + 文件驅動 |
| **多代理模式** | JSONL 郵箱 + 輪詢 | 共享 JSON 檔案 + PS Job |
| **身份持久化** | Identity Re-injection | SKILL_INDEX 每次載入 |
| **優雅關閉** | UUID 追蹤協議 | shutdown_request 訊息 |
| **任務分配** | 聲明鎖（Claim Lock） | round-robin 輪轉 |
| **文件策略** | Markdown-First（教育） | YAML 配置 + Markdown 模板（生產） |
| **測試覆蓋** | 示範代碼，無測試 | 496 個測試（hooks + skills） |

**核心差異**：learn-claude-code 揭示「是什麼」，daily-digest-prompt 實踐「能做什麼」。兩者互補——前者提供心智模型，後者提供生產經驗。

---

## 四、本次研究的落地成果

基於以上 7 大創新洞察，本次研究產出 **`arch-evolution` Skill**（架構演化追蹤器），填補現有系統的 4 個核心缺口：

| 缺口 | 模組 | 輸出 |
|------|------|------|
| ADR 決策無持久化追蹤 | 模組 A：ADR 生成 | `context/adr-registry.json` |
| FIXME/TODO 掃描結果消失 | 模組 B：技術債追蹤 | `context/tech-debt-backlog.json` |
| Skill 隱式依賴未宣告 | 模組 C：依賴圖補強 | 建議清單（人工確認後修改） |
| 三個自省 auto-task 各自獨立 | 模組 D：OODA 調度 | `context/arch-evolution-report.json` |

---

## 五、未落地的建議（供未來參考）

| 建議 | 來源創新 | 優先級 | 阻礙 |
|------|---------|--------|------|
| 術語中文化標準表 | 創新 6（多語言） | 低 | 需要系統性梳理 21 個 SKILL.md |
| 複雜度健康度指標 | 創新 7（最小化） | 中 | 需定義「健康」的量化基準 |
| 聲明鎖機制（Claim Lock） | 創新 7（多代理） | 低 | 現有 round-robin 已足夠，引入收益有限 |
| 線上視覺化 Skill 依賴圖 | 創新 5（心智模型） | 低 | 需要前端開發，超出現有技術棧 |

---

## 六、參考資源

- 主要倉庫：https://github.com/shareAI-lab/learn-claude-code
- 線上學習平台：https://learn-claude-agents.vercel.app/
- 快速上手：`agents/s01_agent_loop.py`（基礎迴圈，84 行）
- 多代理範例：`agents/s11_autonomous_agents.py`（身份持久化 + 聲明鎖）
- 非同步通訊：`agents/s09_multi_agent.py`（JSONL 郵箱 + 5s 輪詢）
