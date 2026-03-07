#!/usr/bin/env python3
"""
build_runner.py — Obsidian Vault 知識庫建置腳本 v4

用法：python build_runner.py <outline.md> <domain_profile.json> <content_materials.json> <output_dir>

v4 改進：
- 知識百科筆記法：每則筆記 1500 字以上的完整知識文章
- 概念圖組織法：MOC 是知識索引與導覽頁
- 零留白：所有區塊由 AI 自動填入完整內容
"""

import json
import os
import re
import sys
from datetime import datetime

def main():
    if len(sys.argv) < 5:
        print("用法: python build_runner.py <outline.md> <domain_profile.json> <content_materials.json> <output_dir>")
        sys.exit(1)

    outline_path = sys.argv[1]
    profile_path = sys.argv[2]
    materials_path = sys.argv[3]
    output_dir = sys.argv[4]

    with open(outline_path, "r", encoding="utf-8") as f:
        outline_text = f.read()
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)
    with open(materials_path, "r", encoding="utf-8") as f:
        materials_list = json.load(f)

    domain = profile.get("domain", "未命名領域")
    domain_en = profile.get("domain_en", "unknown")
    domain_tag = re.sub(r"[^a-zA-Z0-9_]", "_", domain_en.lower().replace(" ", "_"))
    today = datetime.now().strftime("%Y-%m-%d")

    materials_map = {}
    for m in materials_list:
        materials_map[m["note_name"]] = m

    vault_root = os.path.join(output_dir, domain)
    os.makedirs(vault_root, exist_ok=True)

    # Parse outline
    categories = []
    current_cat = None
    current_topic = None
    for line in outline_text.splitlines():
        line = line.strip()
        if line.startswith("## ") and not line.startswith("### "):
            cat_name = line[3:].strip()
            current_cat = {"name": cat_name, "topics": []}
            categories.append(current_cat)
        elif line.startswith("### "):
            topic_name = line[4:].strip()
            current_topic = {"name": topic_name, "notes": []}
            if current_cat:
                current_cat["topics"].append(current_topic)
        elif line.startswith("- "):
            note_name = line[2:].strip()
            if current_topic:
                current_topic["notes"].append(note_name)

    # Create directories
    for d in ["_Templates", "_Assets", "_Canvas", ".obsidian"]:
        os.makedirs(os.path.join(vault_root, d), exist_ok=True)
    for cat in categories:
        cat_dir = os.path.join(vault_root, cat["name"])
        os.makedirs(cat_dir, exist_ok=True)
        for topic in cat["topics"]:
            topic_dir = os.path.join(cat_dir, topic["name"])
            os.makedirs(topic_dir, exist_ok=True)

    # .obsidian configs
    app_json = {
        "attachmentFolderPath": "_Assets",
        "showLineNumber": True,
        "strictLineBreaks": False,
        "readableLineLength": True,
        "defaultViewMode": "source"
    }
    graph_json = {
        "search": "-path:_Templates -path:_Assets -path:_Canvas",
        "colorGroups": [
            {"query": "tag:#type/overview", "color": {"a": 1, "rgb": 16753920}},
            {"query": "tag:#type/moc", "color": {"a": 1, "rgb": 5025616}},
            {"query": "tag:#type/knowledge", "color": {"a": 1, "rgb": 8900346}}
        ],
        "showArrow": True,
        "nodeSizeMultiplier": 1.1,
        "linkDistance": 250
    }
    with open(os.path.join(vault_root, ".obsidian", "app.json"), "w", encoding="utf-8") as f:
        json.dump(app_json, f, ensure_ascii=False, indent=2)
    with open(os.path.join(vault_root, ".obsidian", "graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph_json, f, ensure_ascii=False, indent=2)

    # Copy source files
    for src_name in ["outline.md", "domain_profile.json", "research_report.md"]:
        src_path = os.path.join(output_dir, src_name)
        if os.path.exists(src_path):
            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()
            with open(os.path.join(vault_root, src_name), "w", encoding="utf-8") as f:
                f.write(content)

    total_notes = 0
    total_chars = 0
    total_links = 0
    blank_violations = 0

    # Generate knowledge notes
    for cat in categories:
        cat_tag = re.sub(r"^\d+-", "", cat["name"]).strip()
        for topic in cat["topics"]:
            topic_tag = re.sub(r"^\d+-", "", topic["name"]).strip()
            for note_name in topic["notes"]:
                mat = materials_map.get(note_name)
                if not mat:
                    blank_violations += 1
                    continue

                overview = mat.get("overview", "")
                detailed = mat.get("detailed_explanation", "")
                key_points = mat.get("key_points", [])
                example = mat.get("example", "")
                misconception = mat.get("misconception", "")
                comparison = mat.get("comparison", "")
                related = mat.get("related_notes", [])
                difficulty = mat.get("difficulty", "intermediate")

                # Build key points section
                kp_lines = []
                for i, kp in enumerate(key_points, 1):
                    kp_lines.append(f"**{i}.** {kp}")
                kp_text = "\n\n".join(kp_lines) if kp_lines else ""

                # Build related notes section
                related_lines = []
                for r in related:
                    rn = r.get("name", "")
                    reason = r.get("reason", "")
                    related_lines.append(f"- [[{rn}]]：{reason}")
                related_lines.append(f"- [[_MOC-{topic['name']}]]：本筆記所屬主題索引")
                related_text = "\n".join(related_lines)
                total_links += len(related)

                # Assemble note content
                note_content = f"""---
title: "{note_name}"
aliases: []
tags:
  - domain/{domain_tag}/{cat_tag}/{topic_tag}
  - type/knowledge
created: {today}
updated: {today}
category: "{cat['name']}"
topic: "{topic['name']}"
difficulty: {difficulty}
---

# {note_name}

## 概述

{overview}

## 詳細說明

{detailed}

## 關鍵要點

{kp_text}

## 具體實例

{example}

## 常見誤解辨析

{misconception}

## 比較與辨析

{comparison}

## 相關概念

{related_text}
"""

                content_chars = len(overview) + len(detailed) + sum(len(k) for k in key_points) + len(example) + len(misconception) + len(comparison)
                total_chars += content_chars
                total_notes += 1

                if content_chars < 100:
                    blank_violations += 1

                note_path = os.path.join(vault_root, cat["name"], topic["name"], f"{note_name}.md")
                with open(note_path, "w", encoding="utf-8") as f:
                    f.write(note_content)

    # Generate topic MOCs
    for cat in categories:
        for topic in cat["topics"]:
            moc_name = f"_MOC-{topic['name']}"
            topic_tag = re.sub(r"^\d+-", "", topic["name"]).strip()
            cat_tag = re.sub(r"^\d+-", "", cat["name"]).strip()

            note_table_rows = []
            reading_order = []
            for i, nn in enumerate(topic["notes"], 1):
                mat = materials_map.get(nn, {})
                overview_line = mat.get("overview", "（無概述）")[:60] + "..."
                diff = mat.get("difficulty", "intermediate")
                note_table_rows.append(f"| {i} | [[{nn}]] | {overview_line} | {diff} |")
                reading_order.append(f"{i}. [[{nn}]]")

            table_text = "\n".join(note_table_rows)
            reading_text = "\n".join(reading_order)

            topic_overview = f"本主題「{topic['name']}」隸屬於「{cat['name']}」分類，共包含 {len(topic['notes'])} 則知識筆記。"

            moc_content = f"""---
title: "MOC - {topic['name']}"
aliases: []
tags:
  - domain/{domain_tag}/{cat_tag}
  - type/moc
created: {today}
updated: {today}
category: "{cat['name']}"
---

# {topic['name']} — 知識索引

## 概述

{topic_overview}

## 知識地圖

| # | 筆記 | 摘要 | 難度 |
|---|------|------|------|
{table_text}

## 建議閱讀順序

{reading_text}

## 上層索引

- [[_MOC-{cat['name']}]]：所屬分類索引
- [[_Overview-MOC]]：總覽索引

## Dataview 查詢

```dataview
TABLE difficulty AS "難度", updated AS "更新日期"
FROM "{cat['name']}/{topic['name']}"
WHERE contains(tags, "type/knowledge")
SORT file.name ASC
```
"""
            moc_path = os.path.join(vault_root, cat["name"], topic["name"], f"{moc_name}.md")
            with open(moc_path, "w", encoding="utf-8") as f:
                f.write(moc_content)

    # Generate category MOCs
    for cat in categories:
        cat_tag = re.sub(r"^\d+-", "", cat["name"]).strip()
        topic_links = []
        for topic in cat["topics"]:
            note_count = len(topic["notes"])
            topic_links.append(f"| [[_MOC-{topic['name']}]] | {note_count} 則筆記 |")
        topic_table = "\n".join(topic_links)

        cat_moc_content = f"""---
title: "MOC - {cat['name']}"
aliases: []
tags:
  - domain/{domain_tag}/{cat_tag}
  - type/moc
created: {today}
updated: {today}
---

# {cat['name']} — 分類索引

## 子主題

| 主題 | 筆記數 |
|------|--------|
{topic_table}

## 上層索引

- [[_Overview-MOC]]：總覽索引

## Dataview 查詢

```dataview
TABLE length(file.outlinks) AS "連結數"
FROM "{cat['name']}"
WHERE contains(tags, "type/moc")
SORT file.name ASC
```
"""
        cat_moc_path = os.path.join(vault_root, cat["name"], f"_MOC-{cat['name']}.md")
        with open(cat_moc_path, "w", encoding="utf-8") as f:
            f.write(cat_moc_content)

    # Generate Overview MOC
    cat_links = []
    total_topic_count = 0
    for cat in categories:
        total_topic_count += len(cat["topics"])
        note_count = sum(len(t["notes"]) for t in cat["topics"])
        cat_links.append(f"| [[_MOC-{cat['name']}]] | {len(cat['topics'])} 個主題 | {note_count} 則筆記 |")
    cat_table = "\n".join(cat_links)

    overview_content = f"""---
title: "Overview MOC - {domain}"
aliases: []
tags:
  - domain/{domain_tag}
  - type/overview
created: {today}
updated: {today}
---

# {domain} — 知識總覽

本知識庫涵蓋 {len(categories)} 大分類、{total_topic_count} 個主題、共 {total_notes} 則知識筆記。

## 分類索引

| 分類 | 主題數 | 筆記數 |
|------|--------|--------|
{cat_table}

## 全局查詢

### 所有知識筆記

```dataview
TABLE category AS "分類", topic AS "主題", difficulty AS "難度"
FROM ""
WHERE contains(tags, "type/knowledge")
SORT category ASC, topic ASC
```

### 進階難度筆記

```dataview
LIST
FROM ""
WHERE difficulty = "advanced"
SORT file.name ASC
```
"""
    with open(os.path.join(vault_root, "_Overview-MOC.md"), "w", encoding="utf-8") as f:
        f.write(overview_content)

    # Generate Homepage
    homepage_content = f"""---
title: "{domain} 知識庫"
tags:
  - type/homepage
---

# {domain} 知識庫

> 打開任何一則筆記，即可獲得該概念的完整知識文章。

## 快速導覽

- [[_Overview-MOC]] — 知識總覽（{total_notes} 則筆記）
- [[research_report]] — 領域調研報告
- [[outline]] — 知識架構大綱

## 統計

- 分類數：{len(categories)}
- 主題數：{total_topic_count}
- 知識筆記：{total_notes} 則
- 平均字數：{total_chars // max(total_notes, 1)} 字/則

## 同步說明

本 Vault 建議使用 Obsidian Git 插件進行桌機間同步，手機端使用 Obsidian Sync 或 iCloud。
"""
    with open(os.path.join(vault_root, "_Homepage.md"), "w", encoding="utf-8") as f:
        f.write(homepage_content)

    # Generate Canvas
    canvas_nodes = []
    canvas_edges = []
    x_base = 0
    overview_id = "overview"
    canvas_nodes.append({
        "id": overview_id,
        "type": "file",
        "file": "_Overview-MOC.md",
        "x": 400, "y": 0, "width": 300, "height": 80,
        "color": "1"
    })

    for ci, cat in enumerate(categories):
        cat_id = f"cat_{ci}"
        cy = (ci - len(categories) / 2) * 250
        canvas_nodes.append({
            "id": cat_id,
            "type": "file",
            "file": f"{cat['name']}/_MOC-{cat['name']}.md",
            "x": 800, "y": int(cy), "width": 280, "height": 70,
            "color": "4"
        })
        canvas_edges.append({
            "id": f"e_ov_{ci}",
            "fromNode": overview_id,
            "toNode": cat_id,
            "fromSide": "right",
            "toSide": "left"
        })
        for ti, topic in enumerate(cat["topics"]):
            topic_id = f"topic_{ci}_{ti}"
            ty = cy + (ti - len(cat["topics"]) / 2) * 120
            canvas_nodes.append({
                "id": topic_id,
                "type": "file",
                "file": f"{cat['name']}/{topic['name']}/_MOC-{topic['name']}.md",
                "x": 1200, "y": int(ty), "width": 260, "height": 60,
                "color": "5"
            })
            canvas_edges.append({
                "id": f"e_ct_{ci}_{ti}",
                "fromNode": cat_id,
                "toNode": topic_id,
                "fromSide": "right",
                "toSide": "left"
            })

    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    with open(os.path.join(vault_root, "_Canvas", f"{domain}-知識地圖.canvas"), "w", encoding="utf-8") as f:
        json.dump(canvas_data, f, ensure_ascii=False, indent=2)

    # Template
    template_content = f"""---
title: "{{{{title}}}}"
aliases: []
tags:
  - domain/{domain_tag}/
  - type/knowledge
created: {{{{date}}}}
updated: {{{{date}}}}
category: ""
topic: ""
difficulty: intermediate
---

# {{{{title}}}}

## 概述

（在此撰寫 200-300 字的完整概述）

## 詳細說明

（在此撰寫 800-1000 字的詳細闡述）

## 關鍵要點

**1.** （要點一）

**2.** （要點二）

**3.** （要點三）

## 具體實例

（在此撰寫 200-300 字的詳細實例）

## 常見誤解辨析

（在此撰寫 100-150 字的誤解辨析）

## 比較與辨析

（在此撰寫 100-200 字的概念比較）

## 相關概念

- [[相關筆記]]：連結理由
"""
    with open(os.path.join(vault_root, "_Templates", "tpl-knowledge-note.md"), "w", encoding="utf-8") as f:
        f.write(template_content)

    # Build stats
    avg_chars = total_chars // max(total_notes, 1)
    zero_blank_rate = ((total_notes - blank_violations) / max(total_notes, 1)) * 100

    stats = {
        "domain": domain,
        "built_at": datetime.now().isoformat(),
        "categories": len(categories),
        "topics": total_topic_count,
        "notes": total_notes,
        "total_chars": total_chars,
        "avg_chars_per_note": avg_chars,
        "total_cross_links": total_links,
        "blank_violations": blank_violations,
        "zero_blank_rate": f"{zero_blank_rate:.1f}%"
    }
    with open(os.path.join(vault_root, "_build_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  Vault 建置完成：{vault_root}")
    print(f"{'='*60}")
    print(f"  分類數：{len(categories)}")
    print(f"  主題數：{total_topic_count}")
    print(f"  知識筆記：{total_notes} 則")
    print(f"  總字數：{total_chars:,} 字")
    print(f"  平均字數：{avg_chars:,} 字/則")
    print(f"  跨概念連結：{total_links} 個")
    print(f"  零留白達成率：{zero_blank_rate:.1f}%")
    print(f"  留白違規：{blank_violations} 則")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
