# Obsidian 知識庫最佳實踐

> 發揮 Obsidian 的獨特優勢：本地優先、雙向連結、圖譜視覺化、Dataview 動態查詢。
> 本文件配合「知識百科筆記法」——每則筆記是一篇完整的知識文章，而非學習卡片。

---

## 核心設計原則

### 1. 完整性優先（Completeness First）

每則筆記是一篇 1500 字以上的完整知識文章。讀者打開任何一則筆記，就能獲得該概念的全貌——定義、原理、實例、誤解辨析、相關比較，一應俱全。

### 2. 連結建構知識網路（Link over Folder）

資料夾提供物理位置，雙向連結提供語義關係。每則筆記的「相關概念」區塊和正文內文中的 wikilink 共同編織知識網路。

**連結品質標準：**
- 每個跨概念連結必須附帶連結理由
- 正文中首次提及其他概念時使用 wikilink
- 一則筆記至少 2 個出向連結：1 個回連 MOC，1 個跨概念連結

### 3. MOC 是知識索引（Knowledge Index）

MOC 是知識導覽頁，不是學習進度追蹤器：
- 包含該主題的完整概述（非空白）
- 提供所有條目的概覽表格（附一句話摘要）
- 提供建議的閱讀順序（基於概念依賴關係）
- Dataview 動態列出筆記清單

### 4. 零留白政策

嚴禁任何形式的空白：
- ❌ 待填寫提示、空白列表項、佔位符
- ✅ 所有區塊由 AI 自動填入完整內容

---

## YAML Frontmatter 設計

### 知識筆記 Frontmatter

```yaml
---
title: "概念名稱"
aliases: ["別名"]
tags:
  - domain/{domain_tag}/{category_tag}/{topic_tag}
  - type/knowledge
created: 2026-01-01
updated: 2026-01-01
category: "所屬分類"
topic: "所屬主題"
difficulty: beginner | intermediate | advanced
---
```

### MOC Frontmatter

```yaml
---
title: "MOC - 主題名稱"
aliases: []
tags:
  - domain/{domain_tag}/{category_tag}
  - type/moc
created: 2026-01-01
updated: 2026-01-01
category: "所屬分類"
---
```

---

## 知識筆記結構

每則筆記的標準結構（1500 字以上）：

| 區塊 | 最低字數 | 內容要求 |
|------|---------|---------|
| 概述 | 200 字 | 定義 + 重要性 + 在體系中的位置 |
| 詳細說明 | 800 字 | 核心原理、歷史、分類、機制 |
| 關鍵要點 | 每點 30 字 | 3-5 個要點帶說明 |
| 具體實例 | 200 字 | 場景 + 運作方式 + 結果 |
| 常見誤解辨析 | 100 字 | 誤解 → 正確 → 混淆原因 |
| 比較與辨析 | 100 字 | 與相鄰概念的對比 |
| 相關概念 | — | 帶理由的 wikilink |

---

## 雙向連結策略

### 核心原則

**所有雙向連結必須寫在 Markdown 正文中。** Obsidian 不解析 frontmatter 中的 wikilink。

### 連結矩陣

| 來源 | 目標 | 寫入位置 |
|------|------|---------|
| Overview | 一級 MOC | 正文「分類索引」 |
| 一級 MOC | 二級 MOC | 正文「子主題」 |
| 二級 MOC | 知識筆記 | 正文「知識地圖」表格 |
| 知識筆記 | 所屬 MOC | 正文「相關概念」 |
| 知識筆記 | 其他筆記 | 正文中 + 「相關概念」區塊 |

### 連結完整性校驗

1. 所有 wikilink 目標檔案是否存在
2. 是否有筆記未被任何 MOC 連結
3. 每個筆記是否包含至少一個 MOC 回連
4. Overview 是否連結了所有一級 MOC

---

## .obsidian 配置

### app.json

```json
{
  "attachmentFolderPath": "_Assets",
  "newFileLocation": "_Inbox",
  "showLineNumber": true,
  "strictLineBreaks": false,
  "readableLineLength": true,
  "defaultViewMode": "source"
}
```

### graph.json

```json
{
  "search": "-path:_Templates -path:_Assets -path:_Canvas",
  "colorGroups": [
    { "query": "tag:#type/overview", "color": { "a": 1, "rgb": 16753920 } },
    { "query": "tag:#type/moc", "color": { "a": 1, "rgb": 5025616 } },
    { "query": "tag:#type/knowledge", "color": { "a": 1, "rgb": 8900346 } }
  ],
  "showArrow": true,
  "nodeSizeMultiplier": 1.1,
  "linkDistance": 250
}
```
