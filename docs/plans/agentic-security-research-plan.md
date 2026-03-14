# 實作計畫：Agentic Security for Browser/Coding Agents 研究

## 概要
- **目標**：系統性探討 2026 年 Browser Agent 與 Coding Agent 所面臨的安全風險（Prompt Injection、權限升級、沙箱逃逸），並歸納業界防禦模式與可落地的安全基線，形成一份 12,000–18,000 字的完整研究文件
- **預估任務數**：12 個（10 核心議題 + 導論 + 結論）
- **相關文件**：`context/ai-research-plan.json`（研究計畫初始定義）

## 架構說明

本研究採**威脅模型導向章節制**，以 Browser Agent 與 Coding Agent 為兩條主線，依「威脅辨識 → 防禦機制 → 實務落地 → 展望」的邏輯遞進排列。每一核心議題對應獨立章節，可分工撰寫與獨立驗收。

引用格式統一採用 **APA 第 7 版**，技術文獻以官方文件 URL 輔助標註。

## 技術棧
- 語言：正體中文
- 格式：Markdown（最終可轉 Word/PDF）
- 引用格式：APA 7th Edition
- 工具：知識庫查詢（localhost:3000）、WebSearch、學術資料庫、官方安全文件

## 執行方式
使用 `executing-plans` skill 逐章執行此計畫

---

## 研究目標與範圍（一句話）

探討 2026 年 Browser Agent 與 Coding Agent 在 Prompt Injection 防禦、最小權限設計、沙箱隔離及持續紅隊測試等面向的安全威脅模型與業界最佳實踐，並產出可直接落地至 daily-digest-prompt 等個人 Agent 專案的安全基線建議。

---

## 核心議題清單

| # | 核心議題 | 簡述 |
|---|---------|------|
| 1 | Agent 威脅全景 | 2026 年 Browser/Coding Agent 面臨的攻擊面分類與風險等級評估 |
| 2 | Prompt Injection 攻擊與防禦 | Direct/Indirect Prompt Injection 的攻擊向量、最新防禦技術（instruction hierarchy、input/output filtering） |
| 3 | 權限分層與最小權限設計 | Agent 權限模型、capability-based access control、動態權限升降機制 |
| 4 | 沙箱隔離架構 | 瀏覽器沙箱、程式碼執行沙箱（gVisor/Firecracker/WASM）、檔案系統隔離 |
| 5 | 審批流程與 Human-in-the-Loop | 關鍵操作確認機制、風險等級自動分類、用戶同意模型設計 |
| 6 | 持續紅隊測試 | 自動化紅隊框架（PyRIT/Garak）、Agent-specific 測試案例、CI/CD 整合 |
| 7 | 可觀測性與審計追蹤 | Agent 行為日誌、鏈式 hash 完整性驗證、異常偵測與告警 |
| 8 | Browser Agent 專題 | 瀏覽器自動化特有風險（DOM 注入、Cookie 竊取、跨站請求）、MCP 安全 |
| 9 | Coding Agent 專題 | 程式碼生成安全（供應鏈攻擊、後門植入、敏感資料洩漏）、Hook 防護機制 |
| 10 | 安全基線落地指南 | 將前述研究成果轉化為 daily-digest-prompt 可實作的安全 checklist 與優先級排序 |

---

## 資料來源策略

| # | 來源類別 | 具體來源 | 搜尋方式 |
|---|---------|---------|---------|
| 1 | 學術資料庫 | IEEE Xplore、ACM Digital Library、arXiv（cs.CR / cs.AI）、USENIX Security | 關鍵字：「agentic AI security」「prompt injection defense」「LLM agent sandboxing」「red teaming LLM agents」 |
| 2 | 官方安全文件 | OWASP Top 10 for LLM Applications、NIST AI RMF、Anthropic Model Spec、OpenAI Safety Best Practices、Google DeepMind Agent Safety | 直接查閱官方頁面，追蹤 2025-2026 最新版本 |
| 3 | 知識庫（KB） | localhost:3000（個人知識庫，含先前 taiwan-cybersecurity、hook 設計筆記） | POST /api/search/hybrid，關鍵字：「agent security」「prompt injection」「沙箱」「紅隊」 |
| 4 | 技術部落格與報告 | Simon Willison's blog、Trail of Bits、NCC Group、Microsoft Security Response Center、Anthropic Research Blog | RSS 追蹤 + 搜尋引擎定向搜尋 |
| 5 | 開源專案與工具 | PyRIT（Microsoft）、Garak（NVIDIA）、Guardrails AI、LlamaGuard、Rebuff | GitHub README + Issue tracker + 安全 advisory |
| 6 | 產業報告 | Gartner AI Security、MITRE ATLAS、AI Incident Database | 報告全文或摘要下載 |

**篩選條件**：優先選用 2024-2026 年發表的文獻；2023 年以前僅用於歷史脈絡說明。

---

## 各議題驗收條件

| # | 核心議題 | 驗收條件：具體引用 | 驗收條件：數據/證據 | 驗收條件：對比分析 |
|---|---------|-------------------|-------------------|-------------------|
| 1 | Agent 威脅全景 | ≥3 篇文獻引用（含 OWASP LLM Top 10 + MITRE ATLAS） | 提供攻擊面分類表與風險等級矩陣（≥5 類攻擊向量） | Browser Agent vs Coding Agent 威脅差異對比 |
| 2 | Prompt Injection | ≥4 篇文獻引用（含 Direct/Indirect 各至少 1 篇學術論文） | 提供已知攻擊案例 ≥3 則，含攻擊 payload 範例 | 比較 instruction hierarchy、input filtering、output filtering 三種防禦的效果與限制 |
| 3 | 權限分層 | ≥3 篇文獻引用（含 capability-based security 原始論文） | 提供權限模型設計圖（至少 3 層） | 比較 Anthropic Claude Code、OpenAI Codex、Cursor 的權限模型差異 |
| 4 | 沙箱隔離 | ≥3 篇文獻引用（含至少 1 篇沙箱逃逸案例研究） | 提供沙箱技術特性對照表（gVisor/Firecracker/WASM/Docker） | 比較不同沙箱技術的安全性、效能、易用性 trade-off |
| 5 | 審批流程 | ≥2 篇文獻引用（含 human-in-the-loop 設計模式） | 提供風險分級矩陣與審批決策樹 | 比較自動審批 vs 人工審批的適用場景 |
| 6 | 紅隊測試 | ≥3 篇文獻引用（含至少 1 個自動化框架論文） | 提供紅隊測試案例設計 ≥5 則（含預期結果） | 比較 PyRIT、Garak、手動紅隊的成本效益 |
| 7 | 可觀測性 | ≥2 篇文獻引用 | 提供日誌 schema 設計與異常偵測規則範例 | 比較結構化日誌 vs 鏈式 hash 審計的完整性保證 |
| 8 | Browser Agent | ≥3 篇文獻引用（含瀏覽器安全模型文獻） | 提供 Browser Agent 特有攻擊向量清單 ≥5 項 | 比較 Playwright/Puppeteer/Selenium 的安全隔離能力 |
| 9 | Coding Agent | ≥3 篇文獻引用（含供應鏈安全文獻） | 提供 Coding Agent 攻擊場景 ≥5 則（含程式碼範例） | 比較 pre-commit hook、runtime sandbox、靜態分析的防護效果 |
| 10 | 安全基線落地 | ≥2 篇文獻引用（含安全基線框架） | 提供可執行的安全 checklist（≥15 項）與優先級排序 | 比較「立即可做」vs「中期規劃」vs「長期願景」三階段 |

---

## 章節大綱草案

### 第一章：導論
- **預估字數**：800–1,200 字（±10%）
- **內容**：
  - 研究動機：AI Agent 從輔助工具演進為自主行動者的安全轉折點
  - 研究目標與範圍界定：聚焦 Browser Agent 與 Coding Agent
  - 三大研究問題回顧（源自 ai-research-plan.json）
  - 研究方法：威脅模型分析 + 文獻綜述 + 案例研究
  - 全文章節安排說明

---

### 第二章：Agent 威脅全景（議題 1）
- **預估字數**：1,200–1,800 字（±10%）
- **內容**：
  - Agentic AI 的攻擊面分類（OWASP LLM Top 10 + MITRE ATLAS 映射）
  - Browser Agent vs Coding Agent 威脅差異
  - 風險等級矩陣（影響 × 可能性）
  - 2024-2026 年重大 AI Agent 安全事件回顧

---

### 第三章：Prompt Injection 攻擊與防禦（議題 2）
- **預估字數**：1,500–2,000 字（±10%）
- **內容**：
  - Direct Prompt Injection：攻擊機制與案例
  - Indirect Prompt Injection：經由外部資料源的間接注入
  - 防禦技術一：Instruction Hierarchy（Anthropic/OpenAI 模型層級）
  - 防禦技術二：Input/Output Filtering（Guardrails AI、LlamaGuard）
  - 防禦技術三：Prompt Shielding 與隔離 prompt 設計
  - 各防禦方案效果與限制比較

---

### 第四章：權限分層與最小權限設計（議題 3）
- **預估字數**：1,200–1,500 字（±10%）
- **內容**：
  - 最小權限原則在 AI Agent 的應用
  - Capability-based access control 模型
  - 動態權限升降機制（用戶確認觸發）
  - 實務案例：Claude Code allowedTools、Cursor permissions、Codex sandbox

---

### 第五章：沙箱隔離架構（議題 4）
- **預估字數**：1,200–1,800 字（±10%）
- **內容**：
  - 沙箱技術概覽（OS-level / container / WASM / 瀏覽器）
  - gVisor vs Firecracker vs WASM vs Docker 特性對照
  - 沙箱逃逸案例與防禦加固
  - 檔案系統隔離與網路存取控制

---

### 第六章：審批流程與 Human-in-the-Loop（議題 5）
- **預估字數**：1,000–1,500 字（±10%）
- **內容**：
  - 風險等級自動分類（低/中/高/關鍵）
  - 審批決策樹設計
  - 用戶疲勞問題與智慧審批策略
  - daily-digest-prompt Hook 機制的 HITL 實踐

---

### 第七章：持續紅隊測試（議題 6）
- **預估字數**：1,200–1,800 字（±10%）
- **內容**：
  - 紅隊測試在 AI Agent 安全中的角色
  - 自動化框架：PyRIT（Microsoft）、Garak（NVIDIA）
  - Agent-specific 測試案例設計（≥5 則）
  - CI/CD 整合與持續安全驗證

---

### 第八章：可觀測性與審計追蹤（議題 7）
- **預估字數**：1,000–1,500 字（±10%）
- **內容**：
  - 結構化日誌設計（JSONL schema）
  - 鏈式 hash 完整性驗證（daily-digest-prompt audit_verify.py 案例）
  - 異常偵測規則與告警機制
  - Agent 行為重播與事後分析

---

### 第九章：Browser Agent 安全專題（議題 8）
- **預估字數**：1,200–1,800 字（±10%）
- **內容**：
  - 瀏覽器自動化的特有攻擊面（DOM 注入、Cookie 竊取、跨站請求偽造）
  - MCP（Model Context Protocol）安全考量
  - Playwright/Puppeteer/Selenium 安全隔離比較
  - 安全瀏覽器 Agent 架構設計模式

---

### 第十章：Coding Agent 安全專題（議題 9）
- **預估字數**：1,200–1,800 字（±10%）
- **內容**：
  - 程式碼生成安全風險（惡意 import、後門植入、敏感資料洩漏）
  - 供應鏈攻擊向量（依賴注入、typosquatting）
  - Pre-commit hook 防護（daily-digest-prompt pre_bash_guard/pre_write_guard 案例）
  - Runtime sandbox vs 靜態分析 vs Hook 防護效果比較

---

### 第十一章：安全基線落地指南（議題 10）
- **預估字數**：1,500–2,000 字（±10%）
- **內容**：
  - 安全基線 checklist（≥15 項，含優先級 P0/P1/P2）
  - 三階段實施路線圖：
    - 立即可做（P0）：Hook 強化、權限收緊、日誌完善
    - 中期規劃（P1）：紅隊測試 CI 整合、沙箱升級
    - 長期願景（P2）：自動化異常偵測、Agent 行為基線學習
  - daily-digest-prompt 專案對照分析（現有 vs 建議）
  - 成本效益評估

---

### 第十二章：結論
- **預估字數**：800–1,200 字（±10%）
- **內容**：
  - 各章重點回顧
  - 研究核心發現（3–5 點）
  - 研究限制（無法涵蓋的面向）
  - 未來研究方向建議

---

### 參考文獻與附錄
- **預估字數**：800–1,200 字（±10%）
- **內容**：
  - 依 APA 7 格式統一排列所有引用文獻
  - 附錄 A：Agent 威脅分類完整對照表
  - 附錄 B：安全基線 Checklist 完整版（可列印）
  - 附錄 C：紅隊測試案例模板

---

## 字數預估總覽

| 章節 | 主題 | 預估字數 |
|------|------|---------|
| 第一章 | 導論 | 800–1,200 |
| 第二章 | Agent 威脅全景 | 1,200–1,800 |
| 第三章 | Prompt Injection 攻擊與防禦 | 1,500–2,000 |
| 第四章 | 權限分層與最小權限設計 | 1,200–1,500 |
| 第五章 | 沙箱隔離架構 | 1,200–1,800 |
| 第六章 | 審批流程與 HITL | 1,000–1,500 |
| 第七章 | 持續紅隊測試 | 1,200–1,800 |
| 第八章 | 可觀測性與審計追蹤 | 1,000–1,500 |
| 第九章 | Browser Agent 安全專題 | 1,200–1,800 |
| 第十章 | Coding Agent 安全專題 | 1,200–1,800 |
| 第十一章 | 安全基線落地指南 | 1,500–2,000 |
| 第十二章 | 結論 | 800–1,200 |
| 參考文獻+附錄 | — | 800–1,200 |
| **合計** | | **14,600–21,300** |

---

## Checklist

寫計畫前確認：

- [x] 目標明確：探討 Browser/Coding Agent 安全威脅與防禦最佳實踐
- [x] 架構決策已確定：威脅模型導向章節制，APA 7 引用格式
- [x] 任務粒度適當：每章獨立可驗證
- [x] 每個任務包含驗收條件（三項：引用/證據/對比）
- [x] 驗證步驟明確：每章附自我審查 checklist
- [x] 資料來源策略完整：六類來源皆有具體說明
- [x] 儲存到正確位置：`docs/plans/agentic-security-research-plan.md`
