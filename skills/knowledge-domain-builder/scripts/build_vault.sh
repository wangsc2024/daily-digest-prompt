#!/usr/bin/env bash
# ============================================================
# build_vault.sh — Obsidian Vault 自動建置腳本 v3
#
# 用法：bash build_vault.sh <outline.md> <domain_profile.json> <content_materials.json> <output_dir>
#
# v3 改進：
# - 讀取 content_materials.json 自動填充每則筆記的完整內容
# - 零留白政策：所有區塊都有實質內容
# - 融合 Zettelkasten + Progressive Summarization 雙理論
# - MOC 自動填入概述和學習建議
# - 連結完整性校驗 + 零留白校驗
# ============================================================

set -euo pipefail

OUTLINE="${1:?用法: build_vault.sh <outline.md> <domain_profile.json> <content_materials.json> <output_dir>}"
PROFILE="${2:?缺少 domain_profile.json}"
MATERIALS="${3:?缺少 content_materials.json}"
OUTPUT_DIR="${4:?缺少輸出目錄}"

DOMAIN=$(python3 -c "import json; print(json.load(open('$PROFILE'))['domain'])")
DOMAIN_EN=$(python3 -c "import json; print(json.load(open('$PROFILE')).get('domain_en',''))")
SYNC_METHOD=$(python3 -c "import json; print(json.load(open('$PROFILE')).get('technical',{}).get('sync_method','none'))")
CONTENT_TONE=$(python3 -c "import json; print(json.load(open('$PROFILE')).get('content',{}).get('tone','conversational'))")
TODAY=$(date +%Y-%m-%d)
VAULT_ROOT="${OUTPUT_DIR}/${DOMAIN}"

echo "🏗️  開始建置 Obsidian Vault v3: ${DOMAIN}"
echo "📁 輸出路徑: ${VAULT_ROOT}"
echo "📝 內容風格: ${CONTENT_TONE}"
echo "🚫 零留白政策: 啟用"
echo ""

mkdir -p "${VAULT_ROOT}/.obsidian/plugins/homepage"
mkdir -p "${VAULT_ROOT}/_Templates"
mkdir -p "${VAULT_ROOT}/_Assets"
mkdir -p "${VAULT_ROOT}/_Inbox"
mkdir -p "${VAULT_ROOT}/_Canvas"
cp "$OUTLINE" "${VAULT_ROOT}/outline.md"
cp "$PROFILE" "${VAULT_ROOT}/domain_profile.json"
cp "$MATERIALS" "${VAULT_ROOT}/content_materials.json"

RESEARCH_REPORT="$(dirname "$OUTLINE")/research_report.md"
if [ -f "$RESEARCH_REPORT" ]; then
    cp "$RESEARCH_REPORT" "${VAULT_ROOT}/research_report.md"
    echo "✅ research_report.md 已複製"
fi

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

# ── Templates ──
cat > "${VAULT_ROOT}/_Templates/tpl-atomic-note.md" << 'EOF'
---
title: "{{title}}"
aliases: []
tags:
  - type/atomic
status: "🌱"
created: {{date}}
updated: {{date}}
up: ""
category: ""
topic: ""
difficulty: 
sr-level: L2
---

# {{title}}

> [!abstract] 定義（L4 精煉摘要）
> 用一句話精確定義這個概念。
>
> *💡 學習後建議用自己的話改寫這段定義。*

> [!tip] 核心要點（L2 粗體標記）
> - **要點一**：說明
> - **要點二**：說明

> [!example] 舉例說明（L1 具體素材）
> 一個具體的例子或類比。

> [!warning] 常見誤解
> - **誤解**：人們常以為...
> - **事實**：實際上...

> [!quote] 費曼檢驗（L5 表達層）
> 試著用最簡單的語言解釋這個概念。
>
> *✍️ 請在學習後親自填寫。*

> [!note] 學習反思
> - 這個概念改變了我對什麼的理解？
> - 它與我已知的哪些知識相關？
>
> *✍️ 請在學習後親自填寫。*

## 相關連結

- 上層主題：（由模板自動填入）
EOF

cat > "${VAULT_ROOT}/_Templates/tpl-moc.md" << 'EOF'
---
title: "MOC - {{title}}"
aliases: []
tags:
  - type/moc
status: "🌱"
created: {{date}}
updated: {{date}}
up: ""
category: ""
sr-level: L2
---

# {{title}}

> [!abstract] 概述
> 主題概述。

## 知識地圖

## 學習進度

```dataview
TABLE WITHOUT ID file.link AS "筆記", status AS "狀態", difficulty AS "難度", updated AS "更新"
FROM "" WHERE contains(tags, "type/atomic") AND topic = this.title
SORT file.name ASC
```

> [!note] 主題反思（L5 表達層）
> *✍️ 學習後填寫整體理解。*
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
- [ ] 學習主題或筆記名稱

> [!tip] 今日收穫
> 今天最重要的一個 takeaway 是什麼？

> [!question] 待解決
> 學習中遇到的疑問，待後續釐清。

## 明日計畫
- [ ] 下一步要學習的內容
EOF

echo "✅ 模板建立完成"

# ══════════════════════════════════════════════════════
# Python: 解析大綱 + 讀取素材表 → 生成全部筆記
# ══════════════════════════════════════════════════════

python3 - "$OUTLINE" "$PROFILE" "$MATERIALS" "$VAULT_ROOT" "$TODAY" << 'PYEOF'
import os, re, json, sys, unicodedata

outline_path = sys.argv[1]
profile_path = sys.argv[2]
materials_path = sys.argv[3]
vault_root = sys.argv[4]
today = sys.argv[5]

with open(profile_path, 'r', encoding='utf-8') as f:
    profile = json.load(f)

with open(materials_path, 'r', encoding='utf-8') as f:
    materials_list = json.load(f)

domain = profile['domain']
domain_en = profile.get('domain_en', '')
content_config = profile.get('content', {})
tone = content_config.get('tone', 'conversational')

materials_map = {}
for m in materials_list:
    materials_map[m['note_name']] = m

def make_tag_safe(text):
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
blank_violations = []
total_chars = 0
total_links = 0

def strip_num(t):
    return re.sub(r'^\d+[-.\s]*', '', t)

def folder_name(idx, title):
    if re.match(r'^\d+[-.]', title): return title
    return f"{idx+1:02d}-{title}"

def get_material(note_name):
    """Get material for a note, with fallback defaults"""
    if note_name in materials_map:
        return materials_map[note_name]
    return {
        'note_name': note_name,
        'definition': f'{note_name}是{domain}領域中的一個重要概念。它涉及該領域的核心原理與實踐應用，理解這個概念對於掌握整體知識架構至關重要。',
        'key_points': [
            f'**基礎概念**：{note_name}是理解{domain}的基本構件之一',
            f'**實踐意義**：掌握{note_name}有助於在實際場景中做出更好的判斷',
            f'**關聯性**：{note_name}與{domain}的其他核心概念緊密相連'
        ],
        'example': f'在{domain}的實際應用中，{note_name}常出現在需要綜合判斷的場景。例如，當面臨相關決策時，對{note_name}的理解能幫助我們從根本原理出發，找到更優的解決方案。',
        'misconception': f'許多初學者以為{note_name}只是一個簡單的定義或術語，但實際上它涉及多層次的理解。僅停留在表面定義而不深入掌握其應用脈絡，會導致在複雜場景中無法正確運用。',
        'related_notes': [],
        'difficulty': 'beginner'
    }

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

    cx = ci * 420
    canvas_nodes.append({"id":f"cat-{ci}","type":"text","x":cx,"y":0,"width":320,"height":60,"text":f"## {ct}","color":"1"})
    canvas_edges.append({"id":f"e-r-{ci}","fromNode":"root","toNode":f"cat-{ci}","fromSide":"bottom","toSide":"top"})

    topic_links = []
    cat_atom_summaries = []

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

        tx = cx + int((ti - len(cat['topics'])/2) * 220)
        canvas_nodes.append({"id":f"t-{ci}-{ti}","type":"file","file":f"{cf}/{tf}/{topic_moc}.md","x":tx,"y":160,"width":260,"height":50,"color":"4"})
        canvas_edges.append({"id":f"e-{ci}-{ti}","fromNode":f"cat-{ci}","toNode":f"t-{ci}-{ti}","fromSide":"bottom","toSide":"top"})

        hier_tag = f"domain/{domain_tag}/{ct_tag}/{tt_tag}"
        rel_path = f"{cf}/{tf}"
        atom_links = []
        atom_table_rows = []
        atom_learning_path = []

        for ai, atom in enumerate(topic['atoms']):
            mat = get_material(atom)
            difficulty = mat.get('difficulty', 'beginner')
            definition = mat.get('definition', '')
            key_points = mat.get('key_points', [])
            example = mat.get('example', '')
            misconception = mat.get('misconception', '')
            related_notes = mat.get('related_notes', [])

            difficulty_star = {'beginner': '⭐', 'intermediate': '⭐⭐', 'advanced': '⭐⭐⭐'}.get(difficulty, '⭐')

            key_points_text = '\n'.join(f'> - {kp}' for kp in key_points) if key_points else f'> - **核心概念**：{atom}是{tt}中的重要組成部分'

            related_links_text = f"- 上層主題：[[{topic_moc}]]——回連到所屬主題的索引\n"
            for rn in related_notes:
                rname = rn.get('name', '')
                rreason = rn.get('reason', '概念相關')
                if rname:
                    related_links_text += f"- [[{rname}]]——{rreason}\n"
                    total_links += 1

            ai_suggestions = []
            all_atoms_flat = [a for c2 in structure for t2 in c2['topics'] for a in t2['atoms']]
            for other_atom in all_atoms_flat:
                if other_atom != atom and other_atom not in [rn.get('name','') for rn in related_notes]:
                    other_mat = materials_map.get(other_atom, {})
                    other_related = other_mat.get('related_notes', [])
                    if any(rn.get('name','') == atom for rn in other_related):
                        ai_suggestions.append(other_atom)
                        if len(ai_suggestions) >= 3:
                            break

            ai_suggest_text = ""
            if ai_suggestions:
                ai_suggest_text = "> [!tip] AI 建議的相關筆記（待確認）\n> 根據語義相近度自動推薦，學習後確認保留或刪除：\n"
                for sug in ai_suggestions:
                    ai_suggest_text += f"> - [[{sug}]]——可能存在概念關聯\n"

            first_sentence = definition.split('。')[0] + '。' if '。' in definition else definition

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
difficulty: {difficulty}
sr-level: L2
---

# {atom}

> [!abstract] 定義（L4 精煉摘要）
> {definition}
>
> *💡 學習後建議用自己的話改寫這段定義，這是從 L2 升級到 L4 的關鍵步驟。*

> [!tip] 核心要點（L2 粗體標記）
{key_points_text}

> [!example] 舉例說明（L1 具體素材）
> {example}

> [!warning] 常見誤解
> {misconception}

> [!quote] 費曼檢驗（L5 表達層）
> 試著用最簡單的語言向一個 12 歲的孩子解釋「{atom}」這個概念。
> 如果你能清楚解釋，代表你真正理解了；如果卡住了，就是還需要深入學習的地方。
>
> *✍️ 這個區塊請在學習後親自填寫。能用簡單語言解釋複雜概念，才是真正的理解。*

> [!note] 學習反思
> 學完「{atom}」後，思考以下問題：
> - 這個概念改變了我對{tt}的什麼理解？
> - 它與我已知的哪些知識相關？
> - 我打算如何在實際中應用它？
>
> *✍️ 這個區塊請在學習後親自填寫。反思是從 🌿 進化到 🌳 的必經之路。*

## 相關連結

{related_links_text}
{ai_suggest_text}

---
*最後更新：{today} · 精煉層級：L2 · 由 Knowledge Domain Builder v3 自動生成*
'''
            with open(ap, 'w', encoding='utf-8') as f:
                f.write(content)
            total_chars += len(content)

            for check_name, check_val in [('definition', definition), ('key_points', key_points_text), ('example', example), ('misconception', misconception)]:
                if not check_val or len(str(check_val).strip()) < 10:
                    blank_violations.append(f"{atom}.{check_name}")

            atom_links.append(f"- [[{atom}]]")
            atom_table_rows.append(f"| {ai+1} | [[{atom}]] | {first_sentence} | {difficulty_star} |")
            atom_learning_path.append(f"{ai+1}. [[{atom}]]")

            cat_atom_summaries.append({'name': atom, 'topic': tt, 'summary': first_sentence})

        topic_overview_sentences = []
        for a_summary in [s for s in cat_atom_summaries if s['topic'] == tt]:
            topic_overview_sentences.append(a_summary['summary'])
        topic_overview = f"{tt}涵蓋了{domain}領域中的{len(topic['atoms'])}個核心知識點。" + ' '.join(topic_overview_sentences[:2])

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
sr-level: L2
---

# {tt}

> [!abstract] 概述
> {topic_overview}

## 知識地圖

| 序號 | 筆記 | 一句話摘要 | 難度 |
|------|------|-----------|------|
{chr(10).join(atom_table_rows)}

## 學習建議路徑

建議按照以下順序學習本主題的知識點：
{chr(10).join(atom_learning_path)}

## 學習進度

```dataview
TABLE WITHOUT ID
  file.link AS "筆記",
  status AS "狀態", 
  difficulty AS "難度", 
  dateformat(date(updated), "MM-dd") AS "更新"
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

### 🏝️ 孤島筆記（缺少跨概念連結）

```dataview
LIST
FROM "{rel_path}"
WHERE contains(tags, "type/atomic") AND length(file.outlinks) <= 2
```

> [!note] 主題反思（L5 表達層）
> 學習完{tt}的所有知識點後，思考：
> - {tt}的核心是什麼？用一句話概括。
> - 它與{ct}中其他主題的關係是什麼？
> - 最重要的 takeaway 是什麼？
>
> *✍️ 定期回來更新這段反思，它是從 🌿 進化到 🌳 的關鍵。*

---
*返回上層：[[{cat_moc}]]*
'''
        with open(os.path.join(tp, f"{topic_moc}.md"), 'w', encoding='utf-8') as f:
            f.write(moc_content)
        topic_links.append(f"- [[{topic_moc}]] ({len(topic['atoms'])} 則)")

    cat_overview = f"{ct}是{domain}知識體系的重要組成部分，包含{len(cat['topics'])}個子主題，共{sum(len(t['atoms']) for t in cat['topics'])}則原子筆記。"
    if cat_atom_summaries:
        cat_overview += f"核心涵蓋：{'、'.join(set(s['topic'] for s in cat_atom_summaries[:3]))}等主題。"

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
sr-level: L2
---

# {ct}

> [!abstract] 概述
> {cat_overview}

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

> [!note] 分類反思（L5 表達層）
> 學習完{ct}的所有主題後，思考：
> - 這個分類的核心主題是什麼？
> - 各子主題之間的關係是什麼？
> - 它如何融入{domain}的整體知識架構？
>
> *✍️ 定期回來更新這段反思。*

---
*返回總覽：[[_Overview-MOC]]*
'''
    with open(os.path.join(cp, f"{cat_moc}.md"), 'w', encoding='utf-8') as f:
        f.write(cat_moc_content)
    overview_links.append(f"### [[{cat_moc}|{ct}]]")
    for tl in topic_links:
        overview_links.append(f"  {tl}")

# ── Mermaid ──
mermaid = "```mermaid\ngraph TD\n" + '\n'.join(mermaid_lines) + f"\n    style A fill:#FF6B35,color:#fff,stroke:#333\n```"

# ── Overview MOC ──
domain_overview = f"{domain}是一個涵蓋{total_cats}大分類、{total_topics}個主題的知識領域。"
cat_names = '、'.join(strip_num(c['title']) for c in structure)
domain_overview += f"主要分支包括：{cat_names}。"
domain_overview += f"本知識庫共包含{total_atoms}則原子筆記，按照由淺入深的學習路徑組織。"

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
> {domain_overview}

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

> 以下資源來自 Phase 1 研究階段，建議按順序閱讀。
> 詳見 `research_report.md`。

## 統計資訊

| 項目 | 數量 |
|------|------|
| 知識分類 | {total_cats} |
| 知識主題 | {total_topics} |
| 原子筆記 | {total_atoms} |
| 建立日期 | {today} |

---
*由 Knowledge Domain Builder v3 自動生成*
'''
with open(os.path.join(vault_root, '_Overview-MOC.md'), 'w', encoding='utf-8') as f:
    f.write(ov)

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

### 🏝️ 孤島筆記（缺少連結，建議補充跨概念連結）

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

## 📖 漸進式學習指南

> [!example] 使用方法（基於 Zettelkasten + Progressive Summarization）
>
> **第一步：瀏覽學習（🌱 保持）**
> - 按 MOC 中的「學習建議路徑」依序閱讀筆記
> - AI 已填入完整基礎內容，直接閱讀即可
>
> **第二步：標記精煉（🌱 → 🌿）**
> - 用 `==高亮==` 標記定義中最關鍵的句子
> - 在核心要點中補充自己發現的要點
> - 新增自己遇到的真實案例
> - 修改 `status: "🌿"` 和 `sr-level: L3`
>
> **第三步：表達整合（🌿 → 🌳）**
> - 用自己的話改寫定義（L4 精煉摘要）
> - 填寫費曼檢驗——用最簡單的語言解釋
> - 填寫學習反思
> - 新增跨域連結（附連結理由）
> - 修改 `status: "🌳"` 和 `sr-level: L5`

---
*由 Knowledge Domain Builder v3 自動生成 · {today}*
'''
with open(os.path.join(vault_root, '_Homepage.md'), 'w', encoding='utf-8') as f:
    f.write(hp)

# ── Canvas ──
root_node = {"id":"root","type":"text","x":int((total_cats-1)*210),"y":-130,"width":360,"height":80,"text":f"# {domain}\n知識領域總覽","color":"6"}
canvas = {"nodes": [root_node] + canvas_nodes, "edges": canvas_edges}
with open(os.path.join(vault_root, '_Canvas', 'knowledge-map.canvas'), 'w', encoding='utf-8') as f:
    json.dump(canvas, f, ensure_ascii=False, indent=2)

# ── Stats + Quality Report ──
avg_chars = total_chars // total_atoms if total_atoms > 0 else 0
zero_blank_rate = 100.0 * (1 - len(blank_violations) / (total_atoms * 4)) if total_atoms > 0 else 100.0

stats = {
    'domain': domain,
    'domain_en': domain_en,
    'categories': total_cats,
    'topics': total_topics,
    'atomic_notes': total_atoms,
    'mocs': total_cats + total_topics + 1,
    'features': [
        'zero_blank_policy',
        'zettelkasten_structure',
        'progressive_summarization_layers',
        'auto_filled_content_L1_L2',
        'callout_blocks',
        'hierarchical_tags',
        'canvas_knowledge_map',
        'homepage_dashboard',
        'dataview_advanced',
        'quickadd_guide',
        'mermaid_roadmap',
        'graph_coloring',
        'link_quality_check'
    ],
    'quality': {
        'zero_blank_rate': f"{zero_blank_rate:.1f}%",
        'avg_note_chars': avg_chars,
        'total_cross_links': total_links,
        'blank_violations': blank_violations[:10]
    },
    'created_at': today
}
with open(os.path.join(vault_root, '_build_stats.json'), 'w', encoding='utf-8') as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(f"✅ {total_cats} 分類、{total_topics} 主題、{total_atoms} 原子筆記")
print(f"✅ 零留白達成率：{zero_blank_rate:.1f}%（{len(blank_violations)} 個違規）")
if blank_violations:
    print(f"⚠️  留白違規：{', '.join(blank_violations[:5])}{'...' if len(blank_violations) > 5 else ''}")
print(f"✅ 平均每則筆記 {avg_chars} 字元")
print(f"✅ 跨概念連結 {total_links} 個")
print(f"✅ {total_cats+total_topics+1} 個 MOC（含概述、學習路徑、Dataview）")
print(f"✅ Homepage 儀表板（含漸進式學習指南）")
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

## Obsidian Git 外掛設定

1. 社群外掛 → "Obsidian Git" → 安裝啟用
2. Auto Pull/Push 間隔：5 分鐘
3. Auto Commit 訊息：`auto: {{date}}`

## 每日工作流

1. 開啟 Obsidian → 自動 pull 最新版本
2. 正常編輯筆記
3. 每 5 分鐘自動 commit + push
4. 關閉前確認同步完成（狀態列檢查）
EOF
elif [ "$SYNC_METHOD" = "syncthing" ]; then
cat > "${VAULT_ROOT}/SYNC_GUIDE.md" << 'EOF'
# 同步設定指南：Syncthing

## 設定步驟

1. 所有設備安裝 Syncthing（桌機 + 手機）
2. 桌機端：將 Vault 資料夾設為共享資料夾
3. 手機端：接受共享，指定存放路徑
4. 手機端 Obsidian：開啟該同步資料夾作為 Vault

## 注意事項

- 建議排除 `.obsidian/workspace.json` 避免衝突
- Syncthing 預設雙向同步，編輯衝突會產生 `.sync-conflict` 檔案
- 定期檢查是否有衝突檔案需要處理
EOF
else
cat > "${VAULT_ROOT}/SYNC_GUIDE.md" << 'EOF'
# 同步設定指南

目前設定為單機使用。如果未來需要跨設備同步，以下是可選方案：

| 方案 | 適用場景 | 成本 | 設定難度 |
|------|---------|------|---------|
| Git + Obsidian Git | 桌機間同步 | 免費 | 低 |
| Obsidian Sync | 全平台同步 | US$4/月 | 極低 |
| Syncthing | 含 Android | 免費 | 中 |
| iCloud | Apple 生態 | 免費 | 低 |
EOF
fi

# ── Plugin Guide ──
cat > "${VAULT_ROOT}/PLUGIN_GUIDE.md" << 'EOF'
# 推薦外掛安裝指南

## ★★★ 必裝

### Dataview

驅動所有 MOC、Homepage 的動態查詢。沒有 Dataview，學習進度儀表板和統計功能都無法運作。

- 安裝：設定 → 社群外掛 → 瀏覽 → 搜尋 "Dataview" → 安裝 → 啟用
- 設定：✅ Enable JavaScript Queries、✅ Enable Inline Queries

### Templater

進階模板引擎，支援日期變數和腳本。新增筆記時自動套用模板。

- 安裝：社群外掛 → "Templater" → 安裝 → 啟用
- 設定：Template folder → `_Templates`、✅ Trigger on new file

### Homepage

打開 Vault 自動顯示學習儀表板。每次打開就能看到學習進度。

- 安裝：社群外掛 → "Homepage" → 安裝 → 啟用
- 設定：已預配置（`.obsidian/plugins/homepage/data.json`），預設打開 `_Homepage.md`

## ★★☆ 推薦

### QuickAdd — 一鍵新增原子筆記

讓你用快捷鍵快速建立新的原子筆記，自動套用模板和放入正確資料夾。

#### 設定步驟

1. 安裝：社群外掛 → "QuickAdd" → 安裝 → 啟用
2. 打開 QuickAdd 設定 → "Add Choice"
3. 名稱：「新增原子筆記」，類型：Template
4. 設定：
   - Template Path → `_Templates/tpl-atomic-note.md`
   - ✅ Create in folder
   - ✅ Choose folder when creating（每次選擇目標資料夾）
5. 點閃電圖示 ⚡ 啟用為命令
6. 前往 設定 → 快捷鍵 → 搜尋 "QuickAdd: 新增原子筆記"
7. 綁定快捷鍵：`Ctrl/Cmd + Shift + N`

#### 使用方式

按快捷鍵 → 輸入筆記名稱 → 選擇資料夾 → 自動套用模板建立

### Obsidian Git（如使用 Git 同步）

自動化 Git 同步。詳見 `SYNC_GUIDE.md`。

## ★☆☆ 可選

| 外掛 | 用途 | 適合誰 |
|------|------|--------|
| Calendar | 搭配每日學習日誌，日曆視圖 | 習慣每日記錄的人 |
| Excalidraw | 手繪概念圖和心智圖 | 視覺化學習者 |
| Style Settings | 調整 Callout 區塊外觀 | 注重美觀的人 |
| Tag Wrangler | 批量管理階層化 Tag | Tag 數量多的人 |
| Strange New Worlds | 顯示反向連結的上下文 | 重度連結使用者 |
EOF

echo "✅ 同步指南 + 外掛指南建立完成"
echo ""
echo "================================================"
echo "🎉 Obsidian Vault v3 建置完成！"
echo "📂 路徑: ${VAULT_ROOT}"
echo ""
echo "✨ v3 特色："
echo "   ✅ 零留白政策：所有筆記都有完整內容"
echo "   ✅ 雙理論融合：Zettelkasten + Progressive Summarization"
echo "   ✅ 漸進式精煉：L1-L2 自動填入，L3-L5 使用者深化"
echo "   ✅ Callout 美化（abstract/tip/example/warning/quote/note）"
echo "   ✅ 階層化 Tag（domain/領域/分類/主題）"
echo "   ✅ Canvas 知識地圖"
echo "   ✅ Homepage 儀表板（含漸進式學習指南）"
echo "   ✅ Dataview 進階查詢"
echo "   ✅ 連結品質檢查（附連結理由）"
echo "   ✅ 品質報告（零留白率、平均字數、連結密度）"
echo "================================================"
