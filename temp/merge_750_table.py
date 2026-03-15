# -*- coding: utf-8 -*-
"""Replace 300-episode table in 淨土教觀學苑podcast專輯.md with 750-episode table."""
import re

md_path = "d:/Source/daily-digest-prompt/docs/plans/淨土教觀學苑podcast專輯.md"
table_path = "d:/Source/daily-digest-prompt/temp/episodes_full.md"

with open(md_path, "r", encoding="utf-8") as f:
    md = f.read()
with open(table_path, "r", encoding="utf-8") as f:
    table_block = f.read().strip()

# Replace from "## 750 集題目列表" through the table (until "---" and "## 使用說明")
pattern = r"(## 750 集題目列表\n\n)\| 集數.*?(\n\n---\n\n## 使用說明)"
m = re.search(pattern, md, flags=re.DOTALL)
if not m:
    raise SystemExit("Pattern did not match - check doc structure")
new_md = md[: m.start()] + m.group(1) + table_block + "\n" + m.group(2) + md[m.end() :]
with open(md_path, "w", encoding="utf-8") as f:
    f.write(new_md)
print("Replaced table with 750 episodes.")
