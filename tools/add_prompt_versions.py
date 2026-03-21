#!/usr/bin/env python3
"""
批次為 prompts/team/*.md 和 templates/auto-tasks/*.md 加入 version frontmatter（ADR-034）。
若檔案已有 frontmatter (--- 開頭) 則只補缺少的 version 欄位，若無 frontmatter 則在開頭插入。
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
VERSION = "1.0.0"
RELEASED_AT = "2026-03-20"
UPDATED = 0


def process_file(path: Path, template_type: str) -> dict | None:
    """
    處理單一 markdown 檔案，加入或補全 frontmatter。
    回傳 {name, path, version, released_at} 或 None（若已是最新）。
    """
    global UPDATED
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    rel_path = path.relative_to(BASE).as_posix()

    if lines and lines[0].strip() == "---":
        # 已有 frontmatter - 找結束 ---
        end_idx = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx == -1:
            # 無結束符，不處理
            return None
        fm_lines = lines[1:end_idx]
        fm_text = "".join(fm_lines)
        # 已有 version 欄位則跳過
        if "version:" in fm_text:
            return {
                "name": path.stem,
                "path": rel_path,
                "template_type": template_type,
                "version": VERSION,
                "released_at": RELEASED_AT,
                "already_had_frontmatter": True,
                "action": "skipped",
            }
        # 插入 version 欄位到 frontmatter 結尾前
        new_fm = fm_lines + [f'version: "{VERSION}"\n', f'released_at: "{RELEASED_AT}"\n']
        new_lines = ["---\n"] + new_fm + [lines[end_idx]] + lines[end_idx + 1:]
        path.write_text("".join(new_lines), encoding="utf-8")
        UPDATED += 1
        return {
            "name": path.stem,
            "path": rel_path,
            "template_type": template_type,
            "version": VERSION,
            "released_at": RELEASED_AT,
            "action": "updated",
        }
    else:
        # 無 frontmatter - 在開頭插入
        # 嘗試從第一行提取 title（如「# 標題」或「你是 XXX Agent」）
        first_line = lines[0].strip() if lines else ""
        if first_line.startswith("#"):
            name_hint = first_line.lstrip("#").strip()[:50]
        elif first_line.startswith("你是"):
            name_hint = first_line[:40]
        else:
            name_hint = path.stem

        fm_block = f'---\nname: "{path.stem}"\ntemplate_type: "{template_type}"\nversion: "{VERSION}"\nreleased_at: "{RELEASED_AT}"\n---\n'
        new_text = fm_block + text
        path.write_text(new_text, encoding="utf-8")
        UPDATED += 1
        return {
            "name": path.stem,
            "path": rel_path,
            "template_type": template_type,
            "version": VERSION,
            "released_at": RELEASED_AT,
            "action": "inserted",
        }


def main() -> int:
    versions: list[dict] = []

    # prompts/team/*.md
    team_dir = BASE / "prompts" / "team"
    for md in sorted(team_dir.glob("*.md")):
        result = process_file(md, "team_prompt")
        if result:
            versions.append(result)

    # templates/auto-tasks/*.md
    auto_dir = BASE / "templates" / "auto-tasks"
    for md in sorted(auto_dir.glob("*.md")):
        result = process_file(md, "auto_task_template")
        if result:
            versions.append(result)

    print(f"[add_prompt_versions] 處理 {len(versions)} 個檔案，更新 {UPDATED} 個")
    for v in versions:
        if v.get("action") != "skipped":
            print(f"  {v['action']:8} {v['path']}")

    # 寫入 state/template-versions.json
    import json
    out = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(),
        "adr": "ADR-20260320-034",
        "description": "記錄所有 prompts/team/*.md 和 templates/auto-tasks/*.md 的版本歷史",
        "templates": versions,
        "meta": {
            "total": len(versions),
            "updated": UPDATED,
            "current_version": VERSION,
        },
    }
    out_path = BASE / "state" / "template-versions.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[add_prompt_versions] state/template-versions.json 已寫入（{len(versions)} 條記錄）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
