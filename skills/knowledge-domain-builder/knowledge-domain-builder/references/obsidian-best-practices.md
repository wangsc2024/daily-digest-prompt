# Obsidian 知識庫最佳實踐

> 充分發揮 Obsidian 的獨特優勢：本地優先、雙向連結、圖譜視覺化、Dataview 動態查詢。

## 核心設計原則

### 1. 原子性（Atomicity）
每則筆記只處理一個概念。判斷標準：能否用一句話說明這則筆記在講什麼？如果需要兩句以上，就該拆分。

### 2. 連結優先於分類（Link over Folder）
資料夾提供「物理位置」，雙向連結提供「語義關係」。真正的知識網路靠的是連結，不是資料夾層級。資料夾最多兩層，深層關係用連結表達。

### 3. MOC 是活的索引（Living Index）
MOC 不是死的目錄，而是帶有使用者理解和總結的「策展筆記」。隨著學習深入，MOC 應該從「連結列表」進化為「概述文章」。

### 4. 漸進式成熟（Progressive Maturity）
用狀態標記追蹤每則筆記的成熟度：
- 🌱 種子（Seedling）：剛建立，只有標題或 AI 初始內容
- 🌿 成長（Growing）：已開始填入自己的理解
- 🌳 常青（Evergreen）：經過反覆修改，內容穩定且深入

## YAML Frontmatter 設計

每則筆記都應有 frontmatter，供 Dataview 查詢使用：

### 原子筆記 Frontmatter

```yaml
---
title: 知識點名稱
aliases: [別名1, 英文名]
tags:
  - domain/{domain_name}
  - topic/{topic_name}
  - type/atomic
status: 🌱
created: {{date}}
updated: {{date}}
up: "[[_MOC-所屬主題]]"
category: 所屬分類
topic: 所屬主題
difficulty: beginner | intermediate | advanced
---
```

### MOC Frontmatter

```yaml
---
title: MOC - 主題名稱
aliases: []
tags:
  - domain/{domain_name}
  - type/moc
status: 🌱
created: {{date}}
updated: {{date}}
up: "[[_MOC-上層分類]]"
category: 所屬分類
---
```

## 模板內容設計

### 原子筆記模板（費曼學習法）

```markdown
---
title: {{title}}
aliases: []
tags:
  - domain/{{domain}}
  - topic/{{topic}}
  - type/atomic
status: 🌱
created: {{date}}
updated: {{date}}
up: "[[{{moc}}]]"
category: {{category}}
topic: {{topic}}
difficulty: 
---

# {{title}}

## 定義
> 這個概念是什麼？（先用 AI 或資料查詢，再用自己的話改寫）


## 用自己的話解釋
> 想像你要向一個完全不懂的人解釋這個概念，你會怎麼說？


## 舉例說明
> 一個具體的例子或類比


## 核心要點
> 最重要的 2-3 個重點


## 常見誤解
> 人們容易搞混或誤解的地方


## 我的反思
> 學完之後的個人思考、與其他知識的連結、實際應用


## 相關連結
> 與此概念相關的其他筆記

- 

---
*最後更新：{{date}}*
```

### MOC 模板

```markdown
---
title: MOC - {{topic}}
aliases: []
tags:
  - domain/{{domain}}
  - type/moc
status: 🌱
created: {{date}}
updated: {{date}}
up: "[[{{parent_moc}}]]"
category: {{category}}
---

# {{topic}}

## 概述
> （學習後填寫：用 3-5 句話總結這個主題的核心概念）


## 知識地圖

{{dataview_query}}

## 學習進度

```dataview
TABLE status AS "狀態", difficulty AS "難度"
FROM "{{folder_path}}"
WHERE type = "atomic" OR contains(tags, "type/atomic")
SORT file.name ASC
```

### 進度統計

```dataview
LIST length(rows) + " 則"
FROM "{{folder_path}}"
WHERE contains(tags, "type/atomic")
GROUP BY status
```

## 筆記連結

{{links_section}}

## 主題反思
> （定期回來更新：這個主題的整體理解、與其他主題的關聯）


---
*返回上層：{{parent_link}}*
```

### 總覽 MOC 模板

```markdown
---
title: {{domain}} - 知識總覽
aliases: [{{domain}} Overview]
tags:
  - domain/{{domain}}
  - type/overview
status: 🌱
created: {{date}}
---

# {{domain}} — 知識總覽

## 領域簡介
> （學習後填寫：用一段話描述這個領域的全貌）


## 學習路線圖

```mermaid
graph TD
    A[{{domain}}] --> B[分類1]
    A --> C[分類2]
    A --> D[分類3]
    B --> B1[主題1-1]
    B --> B2[主題1-2]
    C --> C1[主題2-1]
    D --> D1[主題3-1]
```

## 全局進度儀表板

```dataview
TABLE 
  length(filter(rows, (r) => r.status = "🌱")) AS "🌱 種子",
  length(filter(rows, (r) => r.status = "🌿")) AS "🌿 成長",
  length(filter(rows, (r) => r.status = "🌳")) AS "🌳 常青",
  length(rows) AS "合計"
FROM "{{vault_root}}"
WHERE contains(tags, "type/atomic")
GROUP BY category
```

### 總完成度

```dataview
LIST WITHOUT ID
  "🌱 種子：" + length(filter(this, (p) => p.status = "🌱")) + " 則" + " | " +
  "🌿 成長：" + length(filter(this, (p) => p.status = "🌿")) + " 則" + " | " +
  "🌳 常青：" + length(filter(this, (p) => p.status = "🌳")) + " 則"
FLATTEN list(rows) as this
FROM "{{vault_root}}"
WHERE contains(tags, "type/atomic")
GROUP BY true
```

## 分類索引

{{category_links}}

## 學習資源
> 推薦書籍、課程、網站等（由研究階段自動填入）


## 學習日誌
> 連結到每日學習筆記（使用 Daily Note 或手動記錄）


---
*建立日期：{{date}} | 工具：Knowledge Domain Builder*
```

## Dataview 查詢備忘

### 常用查詢

列出所有種子筆記（待學習）：
```dataview
LIST FROM #type/atomic WHERE status = "🌱" SORT file.name ASC
```

列出最近修改的筆記：
```dataview
TABLE updated AS "更新時間", status AS "狀態"
FROM #type/atomic
SORT updated DESC
LIMIT 10
```

統計各分類進度：
```dataview
TABLE 
  length(filter(rows, (r) => r.status = "🌳")) + "/" + length(rows) AS "進度"
FROM #type/atomic
GROUP BY category
```

## .obsidian 配置

### app.json（基礎設定）

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

### appearance.json

```json
{
  "baseFontSize": 16,
  "interfaceFontFamily": "",
  "textFontFamily": "",
  "monospaceFontFamily": ""
}
```

### graph.json（圖譜配置）

```json
{
  "collapse-filter": false,
  "search": "",
  "showTags": false,
  "showAttachments": false,
  "hideUnresolved": false,
  "showOrphans": true,
  "collapse-color-groups": false,
  "colorGroups": [
    { "query": "tag:#type/overview", "color": { "a": 1, "rgb": 16753920 } },
    { "query": "tag:#type/moc", "color": { "a": 1, "rgb": 5025616 } },
    { "query": "tag:#type/atomic", "color": { "a": 1, "rgb": 8900346 } }
  ],
  "collapse-display": false,
  "showArrow": true,
  "textFadeMultiplier": 0,
  "nodeSizeMultiplier": 1.1,
  "lineSizeMultiplier": 1,
  "collapse-forces": true,
  "centerStrength": 0.5,
  "repelStrength": 10,
  "linkStrength": 1,
  "linkDistance": 250
}
```

## 跨設備同步方案詳情

### 方案 A：Git + Obsidian Git 外掛（免費，桌機間）

適合：桌機 ↔ 筆電同步

設定步驟：
1. 在 Vault 根目錄 `git init`
2. 建立 `.gitignore`（排除 `.obsidian/workspace.json` 等）
3. 推送到 GitHub Private Repo
4. 安裝 Obsidian Git 社群外掛
5. 設定自動 pull/push 間隔（建議 5 分鐘）

`.gitignore` 建議：
```
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/.obsidian-git-data
.trash/
```

### 方案 B：Obsidian Sync（付費，全平台）

適合：需要手機/平板即時同步

優點：官方服務、端對端加密、版本歷史
缺點：US$4/月

### 方案 C：Syncthing（免費，含 Android）

適合：桌機 + Android 手機

設定步驟：
1. 桌機和手機都安裝 Syncthing
2. 將 Vault 資料夾設為共享資料夾
3. 手機安裝 Obsidian，指向 Syncthing 同步的資料夾

### 方案 D：iCloud（免費，Apple 生態）

適合：Mac + iPhone/iPad

設定步驟：
1. 將 Vault 放在 iCloud Drive 中
2. iOS Obsidian 會自動偵測 iCloud 中的 Vault
