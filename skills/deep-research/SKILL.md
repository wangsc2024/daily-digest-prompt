---
name: "deep-research"
version: "2.3.1"
description: |
  企業級深度研究框架（源自 199-biotechnologies/claude-deep-research-skill）。8 相位管線：Scope→Plan→Retrieve→Triangulate→Outline→Synthesize→Critique→Package。強制三角佐證（每個核心主張需 3+ 獨立來源）、批判循環、引用追蹤、防幻覺規則。
  Use when: 需要多來源交叉驗證的研究型任務（技術趨勢報告、AI 產業分析、GitHub 開源專案研究、學術等級調研、需要引用追蹤的綜合報告），或當任務要求「深度研究」「三角佐證」「多來源驗證」時。
allowed-tools:
  - WebSearch
  - WebFetch
  - Read
  - Write
  - Bash
cache-ttl: 0min
triggers:
  - "深度研究"
  - "綜合研究"
  - "多來源驗證"
  - "研究報告"
  - "引用追蹤"
  - "triangulate"
  - "deep research"
  - "citation tracking"
  - "三角佐證"
  - "品質報告"
---

# Deep Research Skill

> **來源**：199-biotechnologies/claude-deep-research-skill v2.3.1
> **適用範圍**：需要多來源交叉驗證的研究型任務（技術研究、AI 趨勢、GitHub 開源分析等）

---

## 研究層級（依任務時間預算選擇）

| 層級 | 執行相位 | 預估時間 | 來源最低要求 | 本專案對應任務 |
|------|---------|---------|------------|--------------|
| Quick | P1→P3→P8 | 2-5 分鐘 | 5+ 來源、不強制三角佐證（跳過 Phase 4） | 快速技術概覽 |
| Standard | P1→P3→P4→P6→P7→P8 | 5-10 分鐘 | 8+ 來源、主張 3+ 佐證 | **tech_research**、**ai_github_research** |
| Deep | P1→P2→P3→P4→P5→P6→P7→P8 | 10-20 分鐘 | 12+ 來源、主張 3+ 佐證 | **ai_deep_research**（4 階段合計） |
| UltraDeep | Full + 多輪 Critique | 20-45 分鐘 | 20+ 來源 | 學術等級、按需觸發 |

---

## 8 相位管線

### Phase 1：SCOPE（界定範疇）
- 分解研究問題為 3-5 個子問題
- 確認成功標準（What does "done" look like?）
- 識別潛在偏見與假設

### Phase 2：PLAN（制定計畫）
- 列出 5-10 個獨立搜尋角度（不同關鍵字組合）
- 識別必查的權威來源（官方文件、學術論文、技術部落格）
- 建立品質閘門清單（research_questions 列表）

### Phase 3：RETRIEVE（並行蒐集）⚡ 關鍵
```
【強制規則】並行執行所有搜尋查詢，不可串行等待。
```

**依層級的蒐集目標：**
| 層級 | WebSearch | WebFetch |
|------|-----------|---------|
| Quick | 2-3 組 | 2-3 篇 |
| Standard | 3-5 組 | 4+ 篇 |
| Deep | 5+ 組 | 5+ 篇 |

- 每個子問題至少 2 組不同關鍵字搜尋（角度不重複）
- WebFetch 優先：官方文件 > 技術部落格 > 新聞報導
- 記錄每個來源：title、url、credibility（high/medium/low）、key_points[]

### Phase 4：TRIANGULATE（三角佐證）🔺 核心品質閘
```
【強制規則】每個核心主張（factual claim）必須有 3+ 獨立來源佐證。
單一來源的結論只能標記為「待驗證」，不可作為報告主張。
```
**執行步驟：**
1. 列出所有核心主張（預期 3-8 條）
2. 對每個主張標記支持來源數量
3. 來源數 < 3（Standard/Deep 層級）→ 補充搜尋或降為「觀點（待驗證⚠️）」
4. 來源數 ≥ 3 且互相獨立 → 標記為「已驗證✅」
5. 識別分歧點：不同來源見解不同時，呈現多方觀點（不強行統一）

### Phase 5：OUTLINE REFINEMENT（大綱修正）
- 根據實際蒐集到的證據調整報告大綱
- 確認 research_questions 已被回答（未回答的需補充搜尋）
- 識別知識缺口（knowledge gaps）

### Phase 6：SYNTHESIZE（綜合撰寫）
- 整合多來源洞見，產出超越單一來源的新理解
- **每個事實性主張必須立即內嵌引用**，格式：`主張內容 [來源：標題, 年份]`
- 80% 流暢散文，< 20% 條列式
- 量化數據（"效能提升 23%"，非"顯著提升"）
- 禁止：添加無法從來源驗證的推斷

### Phase 7：CRITIQUE（批判審查）🛡️ 防幻覺閘
```
【強制規則】完成草稿後，以下檢查必須全部通過才能進入 Package：
```
**9 項結構檢查：**
1. ✅ 執行摘要 200-400 字
2. ✅ 必要章節齊全（摘要、背景、核心分析、應用建議、結論、參考來源）
3. ✅ 引用格式正確（不含 [URL] 佔位符）
4. ✅ 完整書目（每筆含：作者/機構、年份、標題、來源、URL）
5. ✅ 無佔位符文字（"[CITATION NEEDED]"、"TODO"、"..."）
6. ✅ 字數合理（500-10,000 字）
7. ✅ 來源數 ≥ 規定最低值
8. ✅ 無捏造來源（若查無資料，直接說「查無此資料」）
9. ✅ 每個主要章節 ≥ 3 段落

**批判角色模擬（Persona-Based Critique）：**
- 懷疑論者：「這個結論的證據夠強嗎？」
- 領域專家：「有沒有遺漏重要的技術細節？」
- 實務工程師：「這個研究對實際開發有什麼指導意義？」

**若批判發現問題 → 進入 REFINE（補充搜尋 → 修正）→ 再次 CRITIQUE（最多 3 次循環）**

### Phase 8：PACKAGE（交付）
- 最終報告格式：Markdown（必選）
- 結構：
  ```markdown
  # [研究主題]

  ## 執行摘要（200-400 字）

  ## 研究背景

  ## 核心發現（含三角佐證標記）

  ## 深度分析

  ## 實務應用建議

  ## 知識缺口與未來方向

  ## 參考來源（完整書目）
  ```

---

## 引用格式規範

```markdown
<!-- 內嵌引用（行內）-->
LLM 推理成本在 2025 年下降了約 10 倍 [OpenAI Blog, 2025]。

<!-- 書目條目 -->
- [1] OpenAI. (2025). GPT-4o System Card. OpenAI. https://openai.com/... (retrieved 2026-03-21)
```

---

## 防幻覺守則（Anti-Hallucination Rules）

| 禁止行為 | 正確做法 |
|---------|---------|
| 捏造不存在的論文或網址 | 若無法驗證，說「查無此資料」 |
| 用模糊語言掩蓋不確定性（"據報導..."） | 明確標記：「此資訊僅見於單一來源，待驗證」 |
| 合併不同事物（混淆兩個相似工具） | 明確區分，分段描述 |
| 過度推斷（資料說 A，報告說 A→B→C） | 只陳述資料直接支持的結論 |
| 無引用的統計數字 | 每個數字都必須有對應來源 |

---

## 本專案整合對應

各研究 Prompt 使用的層級與必守規則：

| Prompt | 層級 | 三角佐證閾值 | Phase 7 必過項 |
|--------|------|------------|--------------|
| `todoist-auto-tech_research` | Standard | 3+ 來源/主張 | 6 項（字數/書目/無佔位/無捏造/主張有源/章節完整） |
| `todoist-auto-ai_deep_research` | Deep（4 階段合計） | 3+ 來源/主張 | 6 項 |
| `todoist-auto-ai_github_research` | Standard | 3 類來源（README+部落格+社群） | 4 項（架構分析有源/無捏造/無佔位/字數） |

**各 Prompt 都必須：**
1. 在深入研究步驟前讀取本 SKILL.md
2. Phase 3 並行執行（不串行）
3. Phase 4 標記每條主張的佐證來源數
4. Phase 7 批判審查後才寫入 KB
5. `done_cert.quality_score` 依下方評分表填寫

---

## 品質評分（done_cert.quality_score）

| 分數 | Standard 層級標準 | Deep 層級標準 |
|------|-----------------|-------------|
| 5 | 12+ 來源、所有主張✅、Phase 7 全通過、完整書目 | 15+ 來源、所有主張✅、Phase 7 全通過 |
| 4 | 8+ 來源、主要主張✅、Phase 7 通過 6/9 | 12+ 來源、主要主張✅、Phase 7 通過 7/9 |
| 3 | 5+ 來源、部分主張✅ | 8+ 來源、部分主張✅ |
| 2 | < 5 來源或重要主張僅 1 個來源 | < 8 來源或多個主張未驗證 |
| 1 | 無引用或含捏造來源（自動降為 failed） | 同左 |

> **預設目標**：Standard → 4 分，Deep（ai_deep_research Stage 4）→ 4 分
