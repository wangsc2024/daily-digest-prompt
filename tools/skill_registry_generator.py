#!/usr/bin/env python3
"""
Skill Registry Generator

自動掃描 skills/*/SKILL.md frontmatter，生成機器可讀的 skills/skill-registry.json。

功能：
- 掃描所有 SKILL.md 的 frontmatter（name, version, description, triggers, depends-on, allowed-tools）
- 觸發詞衝突偵測（同一關鍵字對應多個 Skill 發出警告）
- 依賴圖驗證（檢查 depends-on 是否存在）
- 生成 JSON registry
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


def parse_frontmatter(skill_md_path: Path) -> dict[str, Any] | None:
    """解析 SKILL.md 的 frontmatter"""
    try:
        content = skill_md_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None

        # 提取 frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_text = parts[1].strip()
        fm = yaml.safe_load(frontmatter_text)
        return fm
    except Exception as e:
        print(f"❌ 解析 {skill_md_path} 失敗: {e}", file=sys.stderr)
        return None


def scan_skills(skills_dir: Path) -> list[dict[str, Any]]:
    """掃描所有 Skills"""
    skills = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        fm = parse_frontmatter(skill_md)
        if not fm:
            print(f"⚠️  跳過 {skill_md}（無有效 frontmatter）", file=sys.stderr)
            continue

        skill_name = fm.get("name", skill_md.parent.name)
        skills.append(
            {
                "name": skill_name,
                "version": fm.get("version", "0.0.0"),
                "description": fm.get("description", "").strip(),
                "triggers": fm.get("triggers", []),
                "depends_on": fm.get("depends-on", []),
                "allowed_tools": fm.get("allowed-tools", []),
                "skill_md_path": str(skill_md.relative_to(skills_dir.parent)),
            }
        )

    return skills


def detect_trigger_conflicts(skills: list[dict[str, Any]]) -> list[str]:
    """偵測觸發詞衝突"""
    trigger_map = defaultdict(list)
    for skill in skills:
        for trigger in skill["triggers"]:
            trigger_map[trigger.lower()].append(skill["name"])

    conflicts = []
    for trigger, skill_names in trigger_map.items():
        if len(skill_names) > 1:
            conflicts.append(f"觸發詞 '{trigger}' 衝突：{', '.join(skill_names)}")

    return conflicts


def validate_dependencies(skills: list[dict[str, Any]]) -> list[str]:
    """驗證依賴圖（僅檢查 Skill 依賴，忽略 config/tools/state 路徑）"""
    skill_names = {s["name"] for s in skills}
    errors = []

    for skill in skills:
        for dep in skill["depends_on"]:
            # 忽略非 Skill 的依賴項（config/tools/state/skills 路徑）
            if any(
                dep.startswith(prefix)
                for prefix in ["config/", "tools/", "state/", "skills/"]
            ):
                continue

            # 檢查 Skill 依賴是否存在
            if dep not in skill_names:
                errors.append(f"{skill['name']} 依賴不存在的 Skill: {dep}")

    return errors


def generate_registry(
    skills: list[dict[str, Any]], output_path: Path
) -> tuple[bool, list[str]]:
    """生成 registry JSON"""
    warnings = []

    # 觸發詞衝突偵測
    conflicts = detect_trigger_conflicts(skills)
    if conflicts:
        warnings.extend(conflicts)
        print(f"⚠️  發現 {len(conflicts)} 個觸發詞衝突", file=sys.stderr)
        for conflict in conflicts:
            print(f"   - {conflict}", file=sys.stderr)

    # 依賴圖驗證
    dep_errors = validate_dependencies(skills)
    if dep_errors:
        warnings.extend(dep_errors)
        print(f"❌ 發現 {len(dep_errors)} 個依賴錯誤", file=sys.stderr)
        for error in dep_errors:
            print(f"   - {error}", file=sys.stderr)
        return False, warnings

    # 生成 JSON
    registry = {
        "version": "1.0.0",
        "generated_at": Path(__file__).stat().st_mtime,
        "total_skills": len(skills),
        "skills": skills,
    }

    output_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"✅ Registry 已生成：{output_path}")
    print(f"   - 總 Skills 數：{len(skills)}")
    print(f"   - 觸發詞衝突：{len(conflicts)} 個")
    print(f"   - 依賴錯誤：{len(dep_errors)} 個")

    return True, warnings


def main():
    parser = argparse.ArgumentParser(description="生成 Skill Registry")
    parser.add_argument("--validate", action="store_true", help="僅驗證，不生成檔案")
    parser.add_argument(
        "--output",
        default="skills/skill-registry.json",
        help="輸出檔案路徑（預設：skills/skill-registry.json）",
    )
    args = parser.parse_args()

    # 專案根目錄
    project_root = Path(__file__).parent.parent
    skills_dir = project_root / "skills"
    output_path = project_root / args.output

    if not skills_dir.exists():
        print(f"❌ Skills 目錄不存在：{skills_dir}", file=sys.stderr)
        sys.exit(1)

    # 掃描 Skills
    print(f"📂 掃描 Skills 目錄：{skills_dir}")
    skills = scan_skills(skills_dir)

    if not skills:
        print("❌ 未找到任何 Skills", file=sys.stderr)
        sys.exit(1)

    # 驗證模式
    if args.validate:
        print(f"\n🔍 驗證模式（不生成檔案）")
        conflicts = detect_trigger_conflicts(skills)
        dep_errors = validate_dependencies(skills)

        print(f"\n總 Skills 數：{len(skills)}")
        print(f"觸發詞衝突：{len(conflicts)} 個")
        if conflicts:
            for c in conflicts:
                print(f"   - {c}")

        print(f"依賴錯誤：{len(dep_errors)} 個")
        if dep_errors:
            for e in dep_errors:
                print(f"   - {e}")

        if dep_errors:
            sys.exit(1)
        sys.exit(0)

    # 生成 registry
    print(f"\n📝 生成 Registry...")
    success, warnings = generate_registry(skills, output_path)

    if not success:
        sys.exit(1)

    if warnings:
        print(f"\n⚠️  有 {len(warnings)} 個警告，但 Registry 已成功生成")
        sys.exit(0)

    print("\n✅ 全部完成，無錯誤")


if __name__ == "__main__":
    main()
