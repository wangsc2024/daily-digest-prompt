---
name: knowledge-domain-builder
version: "1.0.0"
description: |
  一鍵搭建 Obsidian 知識領域庫。輸入知識領域名稱，自動完成：對話釐清需求 → 深度研究 → 結構化大綱 → 批量生成 Obsidian Vault。
  Use when: 建立知識庫、搭建知識領域、Obsidian vault、知識體系、knowledge domain、build vault、知識架構、一鍵建庫。
allowed-tools: Bash, Read, Write, WebSearch, WebFetch
cache-ttl: N/A
triggers:
  - "建立知識庫"
  - "搭建知識領域"
  - "Obsidian vault"
  - "知識體系"
  - "knowledge domain"
  - "build vault"
  - "知識架構"
  - "一鍵建庫"
---

# Knowledge Domain Builder

從零搭建 Obsidian 知識領域庫的全自動化工作流。

> AI 一站式完成調研、架構、建庫。每則筆記都是一篇完整的知識文章，打開即可查閱，不須使用者填寫任何內容。

## 方法論基礎

本工具採用兩套互補的知識組織方法（詳見 `references/note-taking-theories.md`）：

| 方法 | 提供的能力 | 在本系統中的角色 |
|------|-----------|----------------|
| **知識百科筆記法** | 每則筆記是一篇自足完整的知識文章（1500 字以上） | 定義筆記內容標準與結構 |
| **概念圖組織法** | 概念間的階層、橫向、跨域關係網路 | 定義筆記間的連結策略與 MOC 組織 |

### 核心原則

**本工具是用來建立知識參考庫，不是學習工具。**

- 每則筆記是一篇**完整的知識文章**，不是待填寫的學習卡片
- 使用者是**查閱者與策展者**，不是從零撰寫者
- 所有內容由 AI 基於深度研究自動生成，使用者可以修改但不需要填寫
- 每則筆記實質內容 **1500 字以上**，確保概念闡述的深度和完整性
- **嚴禁任何形式的留白**：不得出現空白區塊、待填寫提示、佔位符

## 工作流總覽

```
Phase 0  需求對話        →  釐清領域、範圍、深度、風格
Phase 1  深度研究        →  全面調研該領域，收集完整知識素材
Phase 2  結構化大綱      →  生成 Markdown 知識架構
Phase 2.5 內容素材表     →  為每則筆記準備 1500 字以上的完整內容
Phase 3  搭建 Vault      →  自動建立資料夾、MOC、知識筆記、配置
Phase 4  同步與交付      →  跨設備同步建議 + 完成通知
```

---

## Phase 0：需求對話（必須執行，不可跳過）

用對話釐清使用者的真實需求。

### 執行方式

讀取 `references/socratic-questions.md` 取得完整問題框架，然後依序提問。

提問分為三個層次：

**第一層：目的與範圍（What & Why）**
- 你要建立什麼領域的知識庫？具體用途是什麼？
- 這個領域的哪些部分是核心？有沒有明確要排除的？
- 你對這個領域的現有了解程度？

**第二層：技術與偏好（How）**
- 預計筆記總數？（每則 1500 字以上，建議 15-30 則）
- 偏好的內容風格？（學術嚴謹 / 通俗易懂 / 實務導向）
- 設備需求和 Obsidian 使用狀況？

**第三層：內容深度（Depth）**
- 內容深度等級？（入門 / 中級 / 專家）
- 有無特別偏好的參考資料或作者風格？

### 輸出格式

將對話結果整理為 `domain_profile.json`，結構見 `references/socratic-questions.md` 底部。

---

## Phase 1：深度研究

根據 `domain_profile.json` 進行全面調研。

### 工具選擇策略

| 情境 | 工具 | 原因 |
|------|------|------|
| 使用者有上傳資料 | 先分析上傳資料，再 web search 補充 | 以使用者資料為主 |
| 完全陌生的領域 | web_search 多輪搜尋 | 廣泛涵蓋 |
| 需要快速摘要 | Groq API（llama-3.3-70b） | 速度快 |
| 需要深度長文分析 | Claude 自身能力 | 長上下文處理 |

### WebSearch 具體範例

**第一輪：領域全景搜尋**
```bash
# 使用 WebSearch 工具搜尋領域概述
WebSearch: "{領域名稱} 核心概念 定義 體系"
WebSearch: "{領域名稱} history development evolution"
WebSearch: "{領域名稱} 主要分支 分類 taxonomy"
```

**第二輪：深度概念搜尋**
```bash
# 針對每個核心概念進行深度搜尋
WebSearch: "{概念名稱} 詳細說明 原理 mechanism"
WebSearch: "{概念名稱} 實例 案例 example application"
WebSearch: "{概念名稱} vs {相近概念} 比較 差異"
```

**第三輪：權威來源**
```bash
WebSearch: "{領域名稱} 經典書籍 推薦 必讀"
WebSearch: "{領域名稱} 權威論文 seminal papers"
```

### WebFetch 使用時機

當 WebSearch 返回優質來源時，使用 WebFetch 取得完整內容：
```bash
# 範例
WebFetch: "https://example.com/comprehensive-guide"
```

### 研究維度

1. **領域全景**：核心定義、主要分支、歷史脈絡
2. **知識地圖**：概念之間的依賴關係和層次結構
3. **每個概念的深度素材**：定義、原理、分類、實例、常見誤解、與相鄰概念的比較
4. **權威來源**：推薦書籍、經典文獻、權威論述

### 研究深度要求

**因為每則筆記需要 1500 字以上的完整內容**，Phase 1 的研究必須足夠深入——不是只收集概念名稱和一句話定義，而是要為每個概念收集足以撰寫一篇完整知識文章的素材。

### 輸出物

`research_report.md` — 結構化的領域調研報告

---

## Phase 2：結構化大綱

將研究報告轉化為嚴格的 Markdown 知識架構。

### 大綱結構規範

```markdown
## [序號]-[宏觀知識分類]（二級標題 → 一級資料夾）

### [序號]-[知識主題]（三級標題 → 二級資料夾 + MOC）
- [知識筆記名稱]（無序列表 → 知識筆記 .md）
```

### 命名規則

- 資料夾與筆記名稱使用**中文**
- 序號格式：兩位數字（01、02、03...）
- 筆記名稱要求：**明確、可獨立理解、不超過 15 字**
- **全域唯一性**：每個筆記名稱在整個 Vault 中必須唯一
- 禁止四級以上巢狀

### 品質檢查

1. **MECE 原則**：分類之間互不重疊、合在一起涵蓋完整
2. **粒度一致**：同一層級的知識點粒度相近
3. **數量合理**：每個主題下 3-8 則筆記；總量不超過 50 則
4. **名稱唯一性**：掃描所有筆記名稱，確保無重複

### 輸出物

`outline.md` — 結構化知識架構大綱

---

## Phase 2.5：內容素材表（零留白關鍵步驟）

**這是確保每則筆記 1500 字以上、零留白的核心階段。**

### 素材表結構

為每個知識筆記生成一個 JSON 條目，最終輸出為 **JSON 陣列**：

```json
{
  "note_name": "知識筆記名稱",
  "category": "所屬分類",
  "topic": "所屬主題",
  "difficulty": "beginner | intermediate | advanced",
  "overview": "200-300 字完整概述，涵蓋定義、重要性、在體系中的位置",
  "detailed_explanation": "800-1000 字的詳細說明，包含核心原理、歷史背景、分類層次、運作機制",
  "key_points": [
    "要點一：完整說明（30-50 字）",
    "要點二：完整說明（30-50 字）",
    "要點三：完整說明（30-50 字）"
  ],
  "example": "200-300 字的詳細實例，含場景描述、概念運作方式、結果",
  "misconception": "100-150 字的誤解辨析，含誤解內容、正確理解、混淆原因",
  "comparison": "與相近概念的比較說明或比較表格（100-200 字）",
  "related_notes": [
    {"name": "相關筆記A", "reason": "連結理由"},
    {"name": "相關筆記B", "reason": "連結理由"}
  ]
}
```

### 字數要求

| 區塊 | 最低字數 | 說明 |
|------|---------|------|
| overview | 200 字 | 自足的概述 |
| detailed_explanation | 800 字 | 概念的完整闡述 |
| key_points | 每點 30 字 | 3-5 個要點 |
| example | 200 字 | 詳細實例 |
| misconception | 100 字 | 誤解辨析 |
| comparison | 100 字 | 與相鄰概念比較 |
| **合計** | **≥ 1500 字** | 每則筆記的最低實質內容 |

### 輸出物

`content_materials.json` — 所有知識筆記的完整內容素材表

---

## Phase 3：搭建 Obsidian Vault

讀取 `references/obsidian-best-practices.md` 取得最佳實踐，然後執行建置。

### 3-1. 目錄結構

```
{domain_name}/
├── .obsidian/                    ← Vault 配置
├── _Templates/                   ← 筆記模板
├── _Assets/                      ← 附件存放
├── _Canvas/                      ← 知識地圖
├── _Overview-MOC.md              ← 最高級別總覽索引
├── _Homepage.md                  ← 儀表板
├── outline.md                    ← 原始大綱
├── research_report.md            ← 研究報告
├── domain_profile.json           ← 領域設定檔
├── 01-分類A/
│   ├── _MOC-分類A.md
│   ├── 01-主題A1/
│   │   ├── _MOC-主題A1.md
│   │   ├── 知識筆記1.md          ← 1500 字以上完整文章
│   │   ├── 知識筆記2.md
│   │   └── 知識筆記3.md
│   └── ...
└── ...
```

### 3-2. 知識筆記結構

每則知識筆記由 build script 讀取 `content_materials.json` 自動填充：

```markdown
---
title: "{note_name}"
aliases: []
tags:
  - domain/{domain_tag}/{category_tag}/{topic_tag}
  - type/knowledge
created: {date}
updated: {date}
category: "{category}"
topic: "{topic}"
difficulty: {difficulty}
---

# {note_name}

## 概述

{overview — 200-300 字完整概述}

## 詳細說明

{detailed_explanation — 800-1000 字完整闡述}

## 關鍵要點

{key_points — 3-5 個帶完整說明的要點}

## 具體實例

{example — 200-300 字詳細實例}

## 常見誤解辨析

{misconception — 100-150 字誤解辨析}

## 比較與辨析

{comparison — 100-200 字與相近概念的比較}

## 相關概念

{related_links — 帶連結理由的 wikilink 列表}
```

### 3-3. MOC 結構

MOC 是知識索引與導覽頁：

- **概述**：根據研究報告自動生成的主題概述（非空白）
- **知識地圖**：表格格式，每則筆記附一句話摘要
- **建議閱讀順序**：基於概念依賴關係
- **Dataview 查詢**：動態列出筆記清單

### 3-4. 雙向連結策略

> **所有雙向連結必須寫在 Markdown 正文中。**

| 來源 | 目標 | 寫入位置 |
|------|------|---------|
| Overview | 一級 MOC | 正文「分類索引」 |
| 一級 MOC | 二級 MOC | 正文「子主題」 |
| 二級 MOC | 知識筆記 | 正文「知識地圖」表格 |
| 知識筆記 | 所屬 MOC | 正文「相關概念」 |
| 知識筆記 | 其他筆記 | 正文「相關概念」+ 正文內文中 |

### 3-5. 執行方式

**優先方案**：使用 `scripts/build_vault.sh`（若存在）

```bash
bash scripts/build_vault.sh outline.md domain_profile.json content_materials.json output_dir
```

**降級方案**：若腳本不存在，使用內建建置邏輯

逐步執行以下操作：
1. 讀取 `outline.md` 解析目錄結構
2. 讀取 `content_materials.json` 載入筆記素材
3. 使用 Bash `mkdir -p` 建立所有目錄
4. 使用 Write 工具逐一生成：
   - 知識筆記（從 content_materials.json 填充）
   - MOC 檔案（從 outline.md 生成）
   - _Overview-MOC.md 和 _Homepage.md
   - .obsidian/workspace.json（基本配置）
5. 驗證雙向連結完整性

**驗證步驟**：
```bash
# 確認所有檔案存在
find {output_dir} -name "*.md" | wc -l

# 驗證 frontmatter 格式
grep -r "^---$" {output_dir} | wc -l

# 檢查連結完整性（所有 [[wikilink]] 目標都存在）
```

---

## Phase 4：同步與交付

### 跨設備同步方案

| 需求 | 推薦方案 | 成本 |
|------|---------|------|
| 桌機 ↔ 筆電 | Git + Obsidian Git | 免費 |
| 含手機/平板 | Obsidian Sync | US$4/月 |
| 含手機 + 免費 | Syncthing / iCloud | 免費 |
| 僅單機 | 不需配置 | 免費 |

### 完成通知

Vault 建置完成後：
1. 輸出簡要統計：分類數、主題數、筆記數、總字數
2. 輸出品質報告：零留白達成率、平均字數、連結密度
3. 透過 ntfy 發送完成通知（topic: wangsc2025）

---

## 自動化串接邏輯

Phase 0 完成後，Phase 1-4 **完全自動串接，無需人工介入**：

```
[Phase 0 完成，取得 domain_profile.json]
    │
    ├─ Phase 1：多輪研究，產出 research_report.md
    │
    ├─ Phase 2：結構化大綱，產出 outline.md
    │
    ├─ Phase 2.5：為每則筆記生成 1500 字以上的完整內容
    │             → 產出 content_materials.json
    │             → 零留白校驗 + 字數校驗
    │
    ├─ Phase 3：建置 Vault
    │           → 每則筆記都是完整的知識文章
    │           → 所有連結寫入正文 + 附連結理由
    │           → 連結完整性校驗
    │
    └─ Phase 4：同步指南 + 品質報告 + 通知
```

---

## 錯誤處理與降級策略

| 錯誤情境 | 處理方式 | 降級策略 |
|----------|---------|---------|
| **WebSearch 失敗或無結果** | 記錄警告，改用 Claude 內建知識 | 基於訓練資料生成內容，標註「未經外部驗證」 |
| **WebFetch 超時或 404** | 跳過該來源，繼續其他來源 | 若所有來源都失敗，回退至 Claude 內建知識 |
| **Phase 2.5 素材不足 1500 字** | 自動補充「詳細說明」區塊 | 使用 Claude 深度推理補足缺失內容 |
| **build_vault.sh 腳本不存在** | 改用內建 Python 建置邏輯 | 逐一建立目錄和檔案，使用 Write 工具 |
| **Obsidian 配置檔案生成失敗** | 跳過 `.obsidian/` 配置，僅建立 Markdown | 使用者可手動設定 Obsidian |
| **筆記名稱重複** | 自動在重複名稱後加序號（如「概念-2」） | 記錄警告，建議使用者手動重新命名 |
| **JSON 解析失敗** | 清理 JSON 格式錯誤後重試 | 若仍失敗，回退至單筆手動建立 |
| **磁碟空間不足** | 中止建置，輸出已完成的部分清單 | 建議使用者清理空間後重新執行 |

### 品質閘門

在每個 Phase 結束時執行驗證：

**Phase 1 閘門**：
- 研究報告字數 ≥ 3000 字
- 至少涵蓋 10 個核心概念
- 包含至少 3 個權威來源

**Phase 2 閘門**：
- 大綱結構符合規範（最多 3 層巢狀）
- 筆記總數在 15-50 之間
- 所有筆記名稱唯一

**Phase 2.5 閘門**：
- 每則筆記素材 ≥ 1500 字
- 所有必填欄位完整
- related_notes 連結目標都存在

**Phase 3 閘門**：
- 所有目錄和檔案成功建立
- 雙向連結完整性驗證通過
- Dataview 查詢語法正確

若任何閘門失敗，自動觸發對應的降級策略。

---

## 快速啟動

使用者只需說出類似以下的話：

- 「幫我建立一個 _____ 的知識庫」
- 「建立知識領域：_____」

Claude 會自動進入 Phase 0 開始需求對話，完成後自動執行到底。
