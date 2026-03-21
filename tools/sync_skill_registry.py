#!/usr/bin/env python3
"""
Skill Registry 同步工具（ADR-033）
掃描 skills/**/SKILL.md frontmatter，產出 context/skill-registry.json 和 context/skill-registry-conflicts.md。
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent


def parse_frontmatter(text: str) -> dict:
    """解析 YAML frontmatter（--- 區段）。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end == -1:
        return {}
    fm_lines = lines[1:end]
    result: dict = {}
    current_list: list | None = None
    for line in fm_lines:
        # 跳過空行
        if not line.strip():
            continue
        # list item
        if line.startswith("  - ") or line.startswith("- "):
            val = line.strip().lstrip("- ").strip().strip('"').strip("'")
            if current_list is not None:
                current_list.append(val)
            continue
        # key: value
        m = re.match(r'^(\S.*?):\s*(.*)', line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip().strip('"').strip("'")
            # inline list: depends-on: [a, b, c]
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1]
                items = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
                result[key] = items
                current_list = None
            elif val == "" or val is None:
                # 下一行可能是 list
                current_list = []
                result[key] = current_list
            else:
                result[key] = val
                current_list = None
    return result


def load_skill_index(path: Path) -> set[str]:
    """從 SKILL_INDEX.md 提取技能名稱集合。"""
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    # 找 skill 名稱（backtick 或 **名稱**）
    names = set()
    for m in re.finditer(r'`([a-z][a-z0-9-_]+)`', text):
        names.add(m.group(1))
    for m in re.finditer(r'\*\*([a-z][a-z0-9-_]+)\*\*', text):
        names.add(m.group(1))
    # 也找 | skill-name | 表格格式
    for m in re.finditer(r'\|\s*([a-z][a-z0-9-_]+)\s*\|', text):
        names.add(m.group(1))
    return names


def main() -> int:
    skills_dir = BASE / "skills"
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))

    # 載入 SKILL_INDEX.md
    index_path = BASE / "skills" / "SKILL_INDEX.md"
    index_names = load_skill_index(index_path)

    registry: list[dict] = []
    trigger_map: dict[str, list[str]] = defaultdict(list)  # trigger -> [skill_names]
    all_skills_by_name: dict[str, dict] = {}

    for skill_path in skill_files:
        try:
            text = skill_path.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = parse_frontmatter(text)
        name = fm.get("name") or skill_path.parent.name
        version = fm.get("version", "")
        description = fm.get("description", "")
        # description 可能是多行字串，取第一行
        if isinstance(description, str):
            description = description.strip().split("\n")[0].strip()
        triggers = fm.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        depends_on = fm.get("depends-on") or fm.get("depends_on") or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        allowed_tools = fm.get("allowed-tools") or fm.get("allowed_tools") or []
        if isinstance(allowed_tools, str):
            # "  [Bash, Read, ...]" format
            allowed_tools = [t.strip().strip("[").strip("]") for t in allowed_tools.split(",")]
        rel_path = skill_path.relative_to(BASE).as_posix()
        entry = {
            "name": name,
            "path": rel_path,
            "version": str(version) if version else None,
            "description": description or None,
            "triggers": triggers if triggers else [],
            "depends_on": depends_on if depends_on else [],
            "allowed_tools": allowed_tools if allowed_tools else [],
            "stability": fm.get("stability", "stable"),
            "updated_at": fm.get("updated_at") or fm.get("updated-at") or None,
            "source": "project",
            "in_skill_index": (name in index_names or skill_path.parent.name in index_names),
        }
        registry.append(entry)
        all_skills_by_name[name] = entry

        # 觸發詞去重追蹤
        for t in triggers:
            trigger_map[t.lower()].append(name)

    # 找出衝突
    trigger_conflicts: list[dict] = []
    for trigger, skill_names in trigger_map.items():
        if len(skill_names) > 1:
            trigger_conflicts.append({"trigger": trigger, "skills": skill_names})

    # 找出缺少 SKILL_INDEX 的技能
    skills_in_index = sum(1 for e in registry if e["in_skill_index"])
    skills_missing = [e["name"] for e in registry if not e["in_skill_index"]]

    # 找出依賴缺漏
    broken_deps: list[dict] = []
    all_names = set(all_skills_by_name.keys()) | {Path(e["path"]).parent.name for e in registry}
    for entry in registry:
        for dep in entry["depends_on"]:
            # 忽略 config/ 路徑依賴
            if dep.startswith("config/") or dep.startswith("skills/"):
                continue
            if dep not in all_names:
                broken_deps.append({"skill": entry["name"], "missing_dep": dep})

    # 輸出 context/skill-registry.json
    output = {
        "version": 1,
        "generated_at": datetime.now().isoformat(),
        "generated_by": "tools/sync_skill_registry.py",
        "adr": "ADR-20260320-033",
        "skills": registry,
        "meta": {
            "total_skills": len(registry),
            "skills_in_index": skills_in_index,
            "skills_missing_from_index": len(skills_missing),
            "trigger_conflicts": len(trigger_conflicts),
            "broken_dependencies": len(broken_deps),
        },
    }
    out_path = BASE / "context" / "skill-registry.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[sync_skill_registry] context/skill-registry.json 已寫入（{len(registry)} 個 Skills）")

    # 輸出 context/skill-registry-conflicts.md
    conflicts_lines = [
        "# Skill Registry 衝突報告",
        f"> 生成時間：{datetime.now().isoformat()}",
        "> ADR-20260320-033",
        "",
    ]

    if trigger_conflicts:
        conflicts_lines += [
            "## 觸發詞衝突（同一觸發詞對應多個 Skill）",
            "",
        ]
        for c in trigger_conflicts:
            conflicts_lines.append(f"- `{c['trigger']}` → {', '.join(c['skills'])}")
        conflicts_lines.append("")
    else:
        conflicts_lines += ["## 觸發詞衝突", "", "✅ 無衝突", ""]

    if skills_missing:
        conflicts_lines += [
            f"## 未列於 SKILL_INDEX.md 的 Skills（{len(skills_missing)} 個）",
            "",
        ]
        for name in sorted(skills_missing):
            conflicts_lines.append(f"- {name}")
        conflicts_lines.append("")
    else:
        conflicts_lines += ["## 未列於 SKILL_INDEX.md 的 Skills", "", "✅ 所有 Skills 已在 SKILL_INDEX.md 中", ""]

    if broken_deps:
        conflicts_lines += [
            f"## 依賴缺漏（{len(broken_deps)} 個）",
            "",
        ]
        for d in broken_deps:
            conflicts_lines.append(f"- {d['skill']} → missing: `{d['missing_dep']}`")
        conflicts_lines.append("")
    else:
        conflicts_lines += ["## 依賴缺漏", "", "✅ 所有依賴均已存在", ""]

    conflicts_lines += [
        "## 統計摘要",
        "",
        "| 項目 | 數量 |",
        "|------|------|",
        f"| 總 Skills | {len(registry)} |",
        f"| 已在 SKILL_INDEX | {skills_in_index} |",
        f"| 未在 SKILL_INDEX | {len(skills_missing)} |",
        f"| 觸發詞衝突 | {len(trigger_conflicts)} |",
        f"| 依賴缺漏 | {len(broken_deps)} |",
    ]

    conflicts_path = BASE / "context" / "skill-registry-conflicts.md"
    conflicts_path.write_text("\n".join(conflicts_lines), encoding="utf-8")
    print("[sync_skill_registry] context/skill-registry-conflicts.md 已寫入")
    print(f"  trigger_conflicts: {len(trigger_conflicts)}")
    print(f"  skills_missing_from_index: {len(skills_missing)}")
    print(f"  broken_deps: {len(broken_deps)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
