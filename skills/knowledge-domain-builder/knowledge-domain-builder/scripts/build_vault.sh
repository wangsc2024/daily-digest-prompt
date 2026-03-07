#!/usr/bin/env bash
# ============================================================
# build_vault.sh — Obsidian Vault 自動建置腳本 v2
# 
# 用法：bash build_vault.sh <outline.md> <domain_profile.json> <output_dir>
#
# 進階特色：Callout / 階層化Tag / Canvas / Homepage / Dataview進階 / QuickAdd
# ============================================================

set -euo pipefail

OUTLINE="${1:?用法: build_vault.sh <outline.md> <domain_profile.json> <output_dir>}"
PROFILE="${2:?缺少 domain_profile.json}"
OUTPUT_DIR="${3:?缺少輸出目錄}"

DOMAIN=$(python3 -c "import json; print(json.load(open('$PROFILE'))['domain'])")
DOMAIN_EN=$(python3 -c "import json; print(json.load(open('$PROFILE')).get('domain_en',''))")
SYNC_METHOD=$(python3 -c "import json; print(json.load(open('$PROFILE')).get('technical',{}).get('sync_method','none'))")
TODAY=$(date +%Y-%m-%d)
VAULT_ROOT="${OUTPUT_DIR}/${DOMAIN}"

echo "🏗️  開始建置 Obsidian Vault v2: ${DOMAIN}"
echo "📁 輸出路徑: ${VAULT_ROOT}"
echo ""

mkdir -p "${VAULT_ROOT}/.obsidian/plugins/homepage"
mkdir -p "${VAULT_ROOT}/_Templates"
mkdir -p "${VAULT_ROOT}/_Assets"
mkdir -p "${VAULT_ROOT}/_Inbox"
mkdir -p "${VAULT_ROOT}/_Canvas"
cp "$OUTLINE" "${VAULT_ROOT}/outline.md"
cp "$PROFILE" "${VAULT_ROOT}/domain_profile.json"

# ── .obsidian configs ──
cat > "${VAULT_ROOT}/.obsidian/app.json" << 'EOF'
{"attachmentFolderPath":"_Assets","newFileLocation":"_Inbox","showLineNumber":true,"strictLineBreaks":false,"readableLineLength":true,"defaultViewMode":"source"}
EOF

cat > "${VAULT_ROOT}/.obsidian/appearance.json" << 'EOF'
{"baseFontSize":16}
EOF

cat > "${VAULT_ROOT}/.obsidian/graph.json" << 'EOF'
{"collapse-filter":false,"search":"-path:_Templates -path:_Assets -path:_Canvas","showTags":false,"showAttachments":false,"hideUnresolved":false,"showOrphans":true,"collapse-color-groups":false,"colorGroups":[{"query":"tag:#type/overview","color":{"a":1,"rgb":16753920}},{"query":"tag:#type/moc","color":{"a":1,"rgb":5025616}},{"query":"tag:#type/atomic","color":{"a":1,"rgb":8900346}}],"collapse-display":false,"showArrow":true,"textFadeMultiplier":0,"nodeSizeMultiplier":1.1,"lineSizeMultiplier":1,"collapse-forces":true,"centerStrength":0.5,"repelStrength":10,"linkStrength":1,"linkDistance":250}
EOF

cat > "${VAULT_ROOT}/.obsidian/templates.json" << 'EOF'
{"folder":"_Templates","dateFormat":"YYYY-MM-DD","timeFormat":"HH:mm"}
EOF

cat > "${VAULT_ROOT}/.obsidian/community-plugins.json" << 'EOF'
["dataview","templater-obsidian","quickadd","homepage"]
EOF

cat > "${VAULT_ROOT}/.obsidian/plugins/homepage/data.json" << 'EOF'
{"version":3,"defaultNote":"_Homepage","openMode":"Replace all open notes","manualOpenMode":"Keep open notes","view":"Default view","refreshDataview":true,"autoCreate":false,"autoScroll":true,"pin":false}
EOF

echo "✅ .obsidian 配置完成（含 Graph、Homepage 外掛）"

# ── Templates with Callouts ──
cat > "${VAULT_ROOT}/_Templates/tpl-atomic-note.md" << 'EOF'
---
title: "{{title}}"
aliases: []
tags:
  - type/atomic
status: 🌱
created: {{date}}
updated: {{date}}
up: ""
category: ""
topic: ""
difficulty: 
---

# {{title}}

> [!abstract] 定義
> 這個概念是什麼？（先查資料，再用自己的話改寫）

> [!tip] 核心要點
> 最重要的 2-3 個重點：
> - 

> [!example] 舉例說明
> 一個具體的例子或類比

> [!warning] 常見誤解
> 人們容易搞混或誤解的地方

> [!quote] 用自己的話解釋
> 想像你要向一個完全不懂的人解釋這個概念

> [!note] 我的反思
> 學完之後的個人思考、與其他知識的連結

## 相關連結

- 
EOF

cat > "${VAULT_ROOT}/_Templates/tpl-moc.md" << 'EOF'
---
title: "MOC - {{title}}"
aliases: []
tags:
  - type/moc
status: 🌱
created: {{date}}
updated: {{date}}
up: ""
category: ""
---

# {{title}}

> [!abstract] 概述
> （學習後填寫）

## 知識地圖

## 學習進度

```dataview
TABLE WITHOUT ID file.link AS "筆記", status AS "狀態", difficulty AS "難度", updated AS "更新"
FROM "" WHERE contains(tags, "type/atomic") AND topic = this.title
SORT file.name ASC
```

> [!note] 主題反思
> （定期回來更新）
EOF

cat > "${VAULT_ROOT}/_Templates/tpl-daily-learning.md" << 'EOF'
---
title: "學習日誌 {{date}}"
tags:
  - type/journal
created: {{date}}
---

# 學習日誌 {{date}}

## 今日學習
- [ ] 

> [!tip] 今日收穫
> 

> [!question] 待解決
> 

## 明日計畫
- [ ] 
EOF

echo "✅ 模板建立完成（含 Callout 區塊）"

# ══════════════════════════════════════════════════════
# Python: 解析大綱 → 生成全部筆記 + Canvas + Homepage
# ══════════════════════════════════════════════════════

python3 - "$OUTLINE" "$PROFILE" "$VAULT_ROOT" "$TODAY" << 'PYEOF'
import os, re, json, sys, unicodedata

outline_path, profile_path, vault_root, today = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

with open(profile_path, 'r', encoding='utf-8') as f:
    profile = json.load(f)

domain = profile['domain']
domain_en = profile.get('domain_en', '')

def make_tag_safe(text):
    """保留中文、英文、數字，去掉其他字元"""
    return ''.join(c for c in text if c.isalnum() or '\u4e00' <= c <= '\u9fff' or c == '_')

domain_tag = make_tag_safe(domain)

with open(outline_path, 'r', encoding='utf-8') as f:
    outline_text = f.read()

# ── Parse outline ──
structure = []
h2_idx, h3_idx = -1, -1

for line in outline_text.split('\n'):
    line = line.rstrip()
    m2 = re.match(r'^##\s+(.+)$', line)
    if m2 and not line.startswith('###'):
        h2_idx = len(structure)
        h3_idx = -1
        structure.append({'title': m2.group(1).strip(), 'topics': []})
        continue
    m3 = re.match(r'^###\s+(.+)$', line)
    if m3 and h2_idx >= 0:
        structure[h2_idx]['topics'].append({'title': m3.group(1).strip(), 'atoms': []})
        h3_idx = len(structure[h2_idx]['topics']) - 1
        continue
    ma = re.match(r'^[-*]\s+(.+)$', line)
    if ma and h2_idx >= 0 and h3_idx >= 0:
        name = re.sub(r'[*_`\[\]]', '', ma.group(1)).strip()
        if name:
            structure[h2_idx]['topics'][h3_idx]['atoms'].append(name)

total_cats = len(structure)
total_topics = sum(len(c['topics']) for c in structure)
total_atoms = sum(len(t['atoms']) for c in structure for t in c['topics'])
print(f"📊 解析結果：{total_cats} 個分類、{total_topics} 個主題、{total_atoms} 則原子筆記")

# ── Build everything ──
overview_links, mermaid_lines = [], []
mermaid_lines.append(f'    A["{domain}"]')
canvas_nodes, canvas_edges = [], []

def strip_num(t):
    return re.sub(r'^\d+[-.\s]*', '', t)

def folder_name(idx, title):
    if re.match(r'^\d+[-.]', title): return title
    return f"{idx+1:02d}-{title}"

for ci, cat in enumerate(structure):
    ct = cat['title']
    ct_clean = strip_num(ct)
    ct_tag = make_tag_safe(ct_clean)
    cf = folder_name(ci, ct)
    cp = os.path.join(vault_root, cf)
    os.makedirs(cp, exist_ok=True)

    cat_moc = f"_MOC-{ct}"
    mermaid_lines.append(f'    C{ci}["{ct}"]')
    mermaid_lines.append(f'    A --> C{ci}')
    mermaid_lines.append(f'    style C{ci} fill:#4CAF50,color:#fff,stroke:#333')

    # Canvas: category node
    cx = ci * 420
    canvas_nodes.append({"id":f"cat-{ci}","type":"text","x":cx,"y":0,"width":320,"height":60,"text":f"## {ct}","color":"1"})
    canvas_edges.append({"id":f"e-r-{ci}","fromNode":"root","toNode":f"cat-{ci}","fromSide":"bottom","toSide":"top"})

    topic_links = []
    for ti, topic in enumerate(cat['topics']):
        tt = topic['title']
        tt_clean = strip_num(tt)
        tt_tag = make_tag_safe(tt_clean)
        tf = folder_name(ti, tt)
        tp = os.path.join(cp, tf)
        os.makedirs(tp, exist_ok=True)

        topic_moc = f"_MOC-{tt}"
        mermaid_lines.append(f'    T{ci}_{ti}["{tt}"]')
        mermaid_lines.append(f'    C{ci} --> T{ci}_{ti}')

        # Canvas: topic node (file link to MOC)
        tx = cx + int((ti - len(cat['topics'])/2) * 220)
        canvas_nodes.append({"id":f"t-{ci}-{ti}","type":"file","file":f"{cf}/{topic_moc}.md" if '/' not in tf else f"{cf}/{tf}/{topic_moc}.md","x":tx,"y":160,"width":260,"height":50,"color":"4"})
        canvas_edges.append({"id":f"e-{ci}-{ti}","fromNode":f"cat-{ci}","toNode":f"t-{ci}-{ti}","fromSide":"bottom","toSide":"top"})

        # Hierarchical tag for this topic
        hier_tag = f"domain/{domain_tag}/{ct_tag}/{tt_tag}"
        rel_path = f"{cf}/{tf}"
        atom_links = []

        for atom in topic['atoms']:
            ap = os.path.join(tp, f"{atom}.md")
            content = f'''---
title: "{atom}"
aliases: []
tags:
  - {hier_tag}
  - type/atomic
status: "🌱"
created: {today}
updated: {today}
up: "[[{topic_moc}]]"
category: "{ct}"
topic: "{tt}"
difficulty: 
---

# {atom}

> [!abstract] 定義
> 這個概念是什麼？

> [!tip] 核心要點
> 最重要的 2-3 個重點：
> - 

> [!example] 舉例說明
> 一個具體的例子或類比

> [!warning] 常見誤解
> 人們容易搞混或誤解的地方

> [!quote] 用自己的話解釋
> 想像你要向一個完全不懂的人解釋這個概念

> [!note] 我的反思
> 學完之後的個人思考、與其他知識的連結

## 相關連結

- 

---
*最後更新：{today}*
'''
            with open(ap, 'w', encoding='utf-8') as f: f.write(content)
            atom_links.append(f"- [[{atom}]]")

        # Topic MOC with advanced Dataview
        moc_content = f'''---
title: "MOC - {tt}"
aliases: []
tags:
  - domain/{domain_tag}/{ct_tag}
  - type/moc
status: "🌱"
created: {today}
updated: {today}
up: "[[{cat_moc}]]"
category: "{ct}"
---

# {tt}

> [!abstract] 概述
> （學習後填寫：用 3-5 句話總結這個主題的核心概念）

## 知識地圖

{chr(10).join(atom_links)}

## 學習進度

```dataview
TABLE WITHOUT ID
  file.link AS "筆記",
  status AS "狀態", 
  difficulty AS "難度", 
  updated AS "更新日期"
FROM "{rel_path}"
WHERE contains(tags, "type/atomic")
SORT file.name ASC
```

### 進度統計

```dataview
LIST length(rows) + " 則"
FROM "{rel_path}"
WHERE contains(tags, "type/atomic")
GROUP BY status
```

### 🏝️ 孤島筆記（缺少相關連結）

```dataview
LIST
FROM "{rel_path}"
WHERE contains(tags, "type/atomic") AND length(file.outlinks) <= 2
```

> [!note] 主題反思
> （定期回來更新：整體理解、與其他主題的關聯）

---
*返回上層：[[{cat_moc}]]*
'''
        with open(os.path.join(tp, f"{topic_moc}.md"), 'w', encoding='utf-8') as f: f.write(moc_content)
        topic_links.append(f"- [[{topic_moc}]] ({len(topic['atoms'])} 則)")

    # Category MOC
    cat_moc_content = f'''---
title: "MOC - {ct}"
aliases: []
tags:
  - domain/{domain_tag}
  - type/moc
status: "🌱"
created: {today}
updated: {today}
up: "[[_Overview-MOC]]"
category: "{ct}"
---

# {ct}

> [!abstract] 概述
> （學習後填寫）

## 子主題

{chr(10).join(topic_links)}

## 學習進度

```dataview
TABLE WITHOUT ID file.link AS "筆記", status AS "狀態", difficulty AS "難度"
FROM "{cf}"
WHERE contains(tags, "type/atomic")
SORT file.name ASC
```

### 進度統計

```dataview
LIST length(rows) + " 則"
FROM "{cf}"
WHERE contains(tags, "type/atomic")
GROUP BY status
```

### 🏝️ 孤島筆記

```dataview
LIST FROM "{cf}" WHERE contains(tags, "type/atomic") AND length(file.outlinks) <= 2
```

### 💤 最久未更新（前 5 則）

```dataview
TABLE updated AS "上次更新" FROM "{cf}" WHERE contains(tags, "type/atomic") SORT updated ASC LIMIT 5
```

> [!note] 分類反思
> （定期回來更新）

---
*返回總覽：[[_Overview-MOC]]*
'''
    with open(os.path.join(cp, f"{cat_moc}.md"), 'w', encoding='utf-8') as f: f.write(cat_moc_content)
    overview_links.append(f"### [[{cat_moc}|{ct}]]")
    for tl in topic_links:
        overview_links.append(f"  {tl}")

# ── Mermaid ──
mermaid = "```mermaid\ngraph TD\n" + '\n'.join(mermaid_lines) + f"\n    style A fill:#FF6B35,color:#fff,stroke:#333\n```"

# ── Overview MOC ──
ov = f'''---
title: "{domain} - 知識總覽"
aliases: ["{domain} Overview"]
tags:
  - domain/{domain_tag}
  - type/overview
status: "🌱"
created: {today}
---

# {domain} — 知識總覽

> [!abstract] 領域簡介
> （學習後填寫：用一段話描述這個領域的全貌）

## 學習路線圖

{mermaid}

> [!tip] 搭配 Canvas
> 打開 `_Canvas/knowledge-map.canvas` 可用拖拽方式瀏覽知識地圖

## 全局進度儀表板

```dataview
TABLE 
  length(filter(rows, (r) => r.status = "🌱")) AS "🌱 種子",
  length(filter(rows, (r) => r.status = "🌿")) AS "🌿 成長",
  length(filter(rows, (r) => r.status = "🌳")) AS "🌳 常青",
  length(rows) AS "合計"
FROM ""
WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}")
GROUP BY category
```

## 分類索引

{chr(10).join(overview_links)}

## 🏝️ 全局孤島筆記

```dataview
TABLE category AS "分類", topic AS "主題"
FROM "" WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}") AND length(file.outlinks) <= 2
SORT category ASC, file.name ASC
```

## 💤 最久未更新（全局前 10）

```dataview
TABLE category AS "分類", updated AS "上次更新", status AS "狀態"
FROM "" WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}")
SORT updated ASC LIMIT 10
```

## 🎉 最近修改

```dataview
TABLE category AS "分類", updated AS "更新日期", status AS "狀態"
FROM "" WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}")
SORT updated DESC LIMIT 10
```

## 學習資源
> （由研究階段產出的推薦資源）

## 統計資訊

| 項目 | 數量 |
|------|------|
| 知識分類 | {total_cats} |
| 知識主題 | {total_topics} |
| 原子筆記 | {total_atoms} |
| 建立日期 | {today} |

---
*由 Knowledge Domain Builder v2 自動生成*
'''
with open(os.path.join(vault_root, '_Overview-MOC.md'), 'w', encoding='utf-8') as f: f.write(ov)

# ── Homepage Dashboard ──
hp = f'''---
title: "{domain} 學習儀表板"
tags:
  - type/homepage
cssclass: dashboard
---

# 🏠 {domain} 學習儀表板

> [!tip] 快速導航
> 📋 [[_Overview-MOC|知識總覽]]　·　📥 [[_Inbox/|收件匣]]　·　🗺️ [知識地圖](_Canvas/knowledge-map.canvas)

---

## 📊 學習進度總覽

```dataview
TABLE WITHOUT ID
  category AS "📁 分類",
  length(filter(rows, (r) => r.status = "🌱")) AS "🌱",
  length(filter(rows, (r) => r.status = "🌿")) AS "🌿",
  length(filter(rows, (r) => r.status = "🌳")) AS "🌳",
  length(rows) AS "📝 合計",
  round(length(filter(rows, (r) => r.status = "🌳")) / length(rows) * 100) + "%" AS "✅ 完成率"
FROM ""
WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}")
GROUP BY category
SORT category ASC
```

---

## 📝 最近修改

```dataview
TABLE WITHOUT ID
  file.link AS "筆記", category AS "分類", status AS "狀態", updated AS "更新"
FROM "" WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}")
SORT updated DESC LIMIT 8
```

---

## ⚠️ 需要關注

### 🏝️ 孤島筆記（缺少連結，建議補充）

```dataview
LIST
FROM "" WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}") AND length(file.outlinks) <= 2
LIMIT 10
```

### 💤 最久未更新（可能需要回顧）

```dataview
TABLE WITHOUT ID file.link AS "筆記", category AS "分類", updated AS "上次更新"
FROM "" WHERE contains(tags, "type/atomic") AND contains(tags, "domain/{domain_tag}")
SORT updated ASC LIMIT 5
```

---

> [!example] 使用提示
> - 修改 frontmatter 的 `status`：`🌱` → `🌿` → `🌳` 追蹤學習進度
> - 用 `QuickAdd` 快速新增筆記（見 [[PLUGIN_GUIDE]]）
> - 定期回到 MOC 撰寫主題總結

---
*由 Knowledge Domain Builder v2 自動生成 · {today}*
'''
with open(os.path.join(vault_root, '_Homepage.md'), 'w', encoding='utf-8') as f: f.write(hp)

# ── Canvas (JSON Canvas format) ──
root_node = {"id":"root","type":"text","x":int((total_cats-1)*210),"y":-130,"width":360,"height":80,"text":f"# {domain}\n知識領域總覽","color":"6"}
canvas = {"nodes": [root_node] + canvas_nodes, "edges": canvas_edges}
with open(os.path.join(vault_root, '_Canvas', 'knowledge-map.canvas'), 'w', encoding='utf-8') as f:
    json.dump(canvas, f, ensure_ascii=False, indent=2)

# ── Stats ──
stats = {'domain':domain,'domain_en':domain_en,'categories':total_cats,'topics':total_topics,'atomic_notes':total_atoms,'mocs':total_cats+total_topics+1,'features':['callout_blocks','hierarchical_tags','canvas_knowledge_map','homepage_dashboard','dataview_advanced','quickadd_guide','mermaid_roadmap','graph_coloring'],'created_at':today}
with open(os.path.join(vault_root, '_build_stats.json'), 'w', encoding='utf-8') as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(f"✅ {total_cats} 分類、{total_topics} 主題、{total_atoms} 原子筆記（Callout + 階層Tag）")
print(f"✅ {total_cats+total_topics+1} 個 MOC（含進階 Dataview：孤島、最久未更新）")
print(f"✅ _Homepage.md 儀表板（含進度總覽、孤島警示）")
print(f"✅ Canvas 知識地圖（{len(canvas_nodes)+1} 節點）")
PYEOF

echo ""

# ── Sync Guide ──
if [ "$SYNC_METHOD" = "git" ]; then
cat > "${VAULT_ROOT}/SYNC_GUIDE.md" << 'EOF'
# 同步設定指南：Git + Obsidian Git

## 初始設定
```bash
cd "你的Vault路徑"
git init
git remote add origin <GitHub Private Repo URL>
```

## .gitignore
```
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/.obsidian-git-data
.trash/
```

## Obsidian Git 外掛
1. 社群外掛 → "Obsidian Git" → 安裝啟用
2. Auto Pull/Push 間隔：5 分鐘
3. Auto Commit 訊息：`auto: {{date}}`
EOF
elif [ "$SYNC_METHOD" = "syncthing" ]; then
cat > "${VAULT_ROOT}/SYNC_GUIDE.md" << 'EOF'
# 同步設定指南：Syncthing
1. 所有設備安裝 Syncthing
2. Vault 資料夾設為共享
3. 手機 Obsidian 開啟同步資料夾
EOF
else
cat > "${VAULT_ROOT}/SYNC_GUIDE.md" << 'EOF'
# 同步設定指南
目前為單機使用。可選方案：Git(免費桌機間)、Obsidian Sync(US$4全平台)、Syncthing(免費含Android)、iCloud(免費Apple)。
EOF
fi

# ── Plugin Guide with QuickAdd Macro ──
cat > "${VAULT_ROOT}/PLUGIN_GUIDE.md" << 'EOF'
# 推薦外掛安裝指南

## ★★★ 必裝

### Dataview
驅動所有 MOC、Homepage 的動態查詢。
- 安裝：社群外掛 → "Dataview"
- 設定：✅ Enable JavaScript Queries、✅ Enable Inline Queries

### Templater
進階模板，支援日期變數。
- 安裝：社群外掛 → "Templater"
- 設定：Template folder → `_Templates`、✅ Trigger on new file

### Homepage
打開 Vault 自動顯示儀表板。
- 安裝：社群外掛 → "Homepage"
- 設定：已預配置（`.obsidian/plugins/homepage/data.json`）

## ★★☆ 推薦

### QuickAdd — 一鍵新增原子筆記

#### 設定步驟

1. 安裝：社群外掛 → "QuickAdd"
2. 打開 QuickAdd 設定 → "Add Choice"
3. 名稱：「新增原子筆記」，類型：Template
4. 設定：
   - Template Path → `_Templates/tpl-atomic-note.md`
   - ✅ Create in folder
   - ✅ Choose folder when creating（每次選擇目標資料夾）
5. 點閃電圖示 ⚡ 啟用為命令
6. 前往 設定 → 快捷鍵 → 搜尋 "QuickAdd: 新增原子筆記"
7. 綁定：`Ctrl/Cmd + Shift + N`

#### 使用方式
按快捷鍵 → 輸入筆記名稱 → 選擇資料夾 → 自動套用模板建立

### Obsidian Git（如使用 Git 同步）
自動 Git 同步。見 `SYNC_GUIDE.md`。

## ★☆☆ 可選

| 外掛 | 用途 |
|------|------|
| Calendar | 搭配每日學習日誌 |
| Excalidraw | 手繪概念圖 |
| Style Settings | 調整 Callout 外觀 |
| Tag Wrangler | 批量管理階層化 Tag |
EOF

echo "✅ 同步指南 + 外掛指南建立完成"
echo ""
echo "================================================"
echo "🎉 Obsidian Vault v2 建置完成！"
echo "📂 路徑: ${VAULT_ROOT}"
echo ""
echo "✨ 進階特色："
echo "   ✅ Callout 美化（abstract/tip/example/warning/quote/note）"
echo "   ✅ 階層化 Tag（domain/領域/分類/主題）"
echo "   ✅ Canvas 知識地圖（.canvas JSON）"
echo "   ✅ Homepage 儀表板（進度、孤島、最久未更新）"
echo "   ✅ Dataview 進階查詢"
echo "   ✅ QuickAdd Macro 配置指南"
echo "================================================"
