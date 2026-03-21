#!/usr/bin/env python3
"""
批次為 prompts/team/*.md 和 templates/auto-tasks/*.md 加入 version frontmatter（ADR-034）。
若檔案已有 frontmatter (--- 開頭) 則只補缺少的 version 欄位，若無 frontmatter 則在開頭插入。

用法：
  uv run python tools/add_prompt_versions.py              # 正式執行
  uv run python tools/add_prompt_versions.py --dry-run    # 僅預覽，不寫入
  uv run python tools/add_prompt_versions.py --skip-check # 跳過呼叫端安全檢查（不建議）
"""
from __future__ import annotations
import sys
import argparse
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
VERSION = "1.0.0"
RELEASED_AT = "2026-03-20"
UPDATED = 0

# 需要被加 frontmatter 的目錄
TARGET_DIRS = [
    ("prompts/team", "team_prompt"),
    ("templates/auto-tasks", "auto_task_template"),
]

# 辨識呼叫端有無 frontmatter 去除邏輯的模式
_STRIP_PATTERNS = [
    "Strip-Frontmatter",     # 大多數 .ps1 腳本的統一函式
    "# 移除 frontmatter",    # jiaoguang 的內嵌注解
    "jiaoguangLines[0].Trim() -eq '---'",  # jiaoguang 的內嵌去除實作
    "strip_frontmatter",     # Python 版本（未來）
]


def _check_callers() -> list[str]:
    """
    掃描所有 .ps1 檔案，找出讀取目標目錄的 Get-Content 呼叫，
    確認每行都有 Strip-Frontmatter 或等效去除邏輯。
    回傳問題描述清單（空 = 全部安全）。
    """
    target_path_fragments = []
    for dir_rel, _ in TARGET_DIRS:
        # 同時接受正斜線與反斜線
        target_path_fragments.append(dir_rel.replace("/", "\\"))
        target_path_fragments.append(dir_rel.replace("\\", "/"))

    issues: list[str] = []

    for ps1 in sorted(BASE.rglob("*.ps1")):
        if "backups" in ps1.parts:
            continue
        try:
            text = ps1.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "Get-Content" not in line:
                continue
            if not any(frag in line for frag in target_path_fragments):
                continue

            # 此行讀取了目標目錄的 .md 檔案
            # 安全條件：同行有 Strip-Frontmatter，或前後 20 行有去除邏輯
            context_start = max(0, i - 5)
            context_end = min(len(lines), i + 20)
            context = "\n".join(lines[context_start:context_end])

            # 檢查上下文中是否有非注解行含有去除邏輯
            context_lines = lines[context_start:context_end]
            has_protection = any(
                any(p in cl for p in _STRIP_PATTERNS)
                for cl in context_lines
                if not cl.strip().startswith("#")
            )
            if not has_protection:
                rel = ps1.relative_to(BASE)
                issues.append(
                    f"  {rel}:{i + 1}  →  {stripped[:90]}"
                )

    return issues


def process_file(path: Path, template_type: str, dry_run: bool) -> dict | None:
    """
    處理單一 markdown 檔案，加入或補全 frontmatter。
    dry_run=True 時只回傳預覽結果，不寫入磁碟。
    回傳 {name, path, version, released_at, action} 或 None（無需處理）。
    """
    global UPDATED
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    rel_path = path.relative_to(BASE).as_posix()

    if lines and lines[0].strip() == "---":
        # 已有 frontmatter — 找結束 ---
        end_idx = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx == -1:
            return None  # 無結束符，略過
        fm_text = "".join(lines[1:end_idx])
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
        new_fm = lines[1:end_idx] + [f'version: "{VERSION}"\n', f'released_at: "{RELEASED_AT}"\n']
        new_lines = ["---\n"] + new_fm + [lines[end_idx]] + lines[end_idx + 1:]
        if not dry_run:
            path.write_text("".join(new_lines), encoding="utf-8")
        UPDATED += 1
        return {
            "name": path.stem,
            "path": rel_path,
            "template_type": template_type,
            "version": VERSION,
            "released_at": RELEASED_AT,
            "action": "updated" if not dry_run else "would-update",
        }
    else:
        # 無 frontmatter — 在開頭插入
        fm_block = (
            f'---\n'
            f'name: "{path.stem}"\n'
            f'template_type: "{template_type}"\n'
            f'version: "{VERSION}"\n'
            f'released_at: "{RELEASED_AT}"\n'
            f'---\n'
        )
        if not dry_run:
            path.write_text(fm_block + text, encoding="utf-8")
        UPDATED += 1
        return {
            "name": path.stem,
            "path": rel_path,
            "template_type": template_type,
            "version": VERSION,
            "released_at": RELEASED_AT,
            "action": "inserted" if not dry_run else "would-insert",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="批次加入 prompt frontmatter（ADR-034）")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="僅預覽會發生什麼變更，不實際寫入任何檔案"
    )
    parser.add_argument(
        "--skip-check", action="store_true",
        help="跳過呼叫端 Strip-Frontmatter 安全檢查（不建議）"
    )
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    skip_check: bool = args.skip_check

    if dry_run:
        print("[add_prompt_versions] ── DRY-RUN 模式，不會寫入任何檔案 ──")

    # ── 預飛行安全檢查 ──────────────────────────────────────────────────────
    if not skip_check:
        print("[add_prompt_versions] 預飛行檢查：掃描呼叫端 Strip-Frontmatter...")
        issues = _check_callers()
        if issues:
            print("[add_prompt_versions] ❌ 發現以下呼叫端缺少 Strip-Frontmatter 保護：")
            for issue in issues:
                print(issue)
            print()
            print("[add_prompt_versions] 請先在上述位置加入 Strip-Frontmatter，")
            print("  或使用 --skip-check 強制跳過（可能導致 Claude 誤判 prompt 為文件）。")
            return 1
        print("[add_prompt_versions] ✅ 所有呼叫端均有 Strip-Frontmatter 保護")
    else:
        print("[add_prompt_versions] ⚠ 已跳過呼叫端安全檢查")

    # ── 處理目標目錄 ─────────────────────────────────────────────────────────
    versions: list[dict] = []

    for dir_rel, template_type in TARGET_DIRS:
        target_dir = BASE / dir_rel
        if not target_dir.exists():
            print(f"[add_prompt_versions] 目錄不存在，略過：{dir_rel}")
            continue
        for md in sorted(target_dir.glob("*.md")):
            result = process_file(md, template_type, dry_run)
            if result:
                versions.append(result)

    # ── 摘要報告 ─────────────────────────────────────────────────────────────
    changed = [v for v in versions if v.get("action") not in ("skipped",)]
    print(f"\n[add_prompt_versions] 處理 {len(versions)} 個檔案，異動 {len(changed)} 個")
    for v in changed:
        print(f"  {v['action']:14} {v['path']}")

    if dry_run:
        print("\n[add_prompt_versions] DRY-RUN 完成，未寫入任何檔案。")
        print("  如要實際執行，請移除 --dry-run 參數。")
        return 0

    # ── 寫入 state/template-versions.json ────────────────────────────────────
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
