#!/usr/bin/env python3
"""
Prompt Versioning CLI — Proposal 005 × prompt-version-tracker 合併升級
版本：1.0.0（2026-03-23）

功能：
  check  — 掃描所有 prompt/template 的版本狀態
  bump   — 依語義版本（Major/Minor/Patch）遞增版本號並更新 changelog
  init   — 為無 frontmatter 的 prompt 加入初始版本 frontmatter
  report — 生成版本覆蓋率與品質回歸報告

使用方式：
  uv run python tools/prompt-versioning.py check --dir prompts/team
  uv run python tools/prompt-versioning.py bump --prompt prompts/team/xxx.md --type patch --changes "修正步驟 3" --impact low
  uv run python tools/prompt-versioning.py init --prompt prompts/team/xxx.md
  uv run python tools/prompt-versioning.py report
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── 常數 ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
REGISTRY_FILE = PROJECT_ROOT / "context" / "prompt-version-registry.json"
QUALITY_RESULTS_GLOB = str(PROJECT_ROOT / "results" / "todoist-auto-*.json")

SCAN_GLOBS = [
    "prompts/team/*.md",
    "prompts/team/todoist-auto-*.md",
    "templates/auto-tasks/*.md",
    "templates/sub-agent/*.md",
]

BUMP_RULES = {
    "major": "破壞性變更（輸出格式大幅調整、移除必填欄位）",
    "minor": "新增功能（新增步驟、新增可選欄位）",
    "patch": "修正或優化（措辭調整、範例更新）",
}


# ── 工具函數 ─────────────────────────────────────────────────────────────────

def compute_hash(path: Path) -> str:
    """計算檔案 SHA256 前 12 字元（raw bytes）。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，回傳 (meta_dict, body)。"""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2]


def bump_semver(version: str, bump_type: str) -> str:
    """遞增語義版本號。"""
    version = version.lstrip("v")
    parts = version.split(".")
    while len(parts) < 3:
        parts.append("0")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump_type == "major":
        major += 1; minor = 0; patch = 0
    elif bump_type == "minor":
        minor += 1; patch = 0
    else:  # patch
        patch += 1
    return f"{major}.{minor}.{patch}"


def collect_prompts() -> list[Path]:
    """收集所有需追蹤的 prompt 檔案（去重）。"""
    seen = set()
    paths = []
    for pattern in SCAN_GLOBS:
        for f in glob.glob(str(PROJECT_ROOT / pattern)):
            p = Path(f)
            if p not in seen:
                seen.add(p)
                paths.append(p)
    return sorted(paths)


# ── 指令：check ───────────────────────────────────────────────────────────────

def cmd_check(args) -> int:
    scan_dir = args.dir
    if scan_dir:
        files = sorted(Path(PROJECT_ROOT / scan_dir).glob("*.md"))
    else:
        files = collect_prompts()

    results = []
    for p in files:
        content = p.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(content)
        results.append({
            "file": str(p.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "name": meta.get("name", "MISSING"),
            "version": meta.get("version", "MISSING"),
            "has_changelog": "changelog" in content.lower(),
            "content_hash": compute_hash(p),
        })

    total = len(results)
    has_version = sum(1 for r in results if r["version"] != "MISSING")
    missing = [r["file"] for r in results if r["version"] == "MISSING"]

    print(f"\n📋 Prompt 版本掃描結果（共 {total} 個）")
    print(f"   有版本: {has_version} / {total} ({round(has_version/max(total,1)*100)}%)")
    if missing:
        print(f"\n⚠️  缺少版本 frontmatter（{len(missing)} 個）：")
        for f in missing:
            print(f"   - {f}")
    else:
        print("✅ 所有 prompt 均有版本 frontmatter")

    print("\n版本清單：")
    for r in results:
        marker = "✅" if r["version"] != "MISSING" else "❌"
        print(f"  {marker} {r['file']}  v{r['version']}  [{r['content_hash']}]")

    return 0 if not missing else 1


# ── 指令：bump ────────────────────────────────────────────────────────────────

def cmd_bump(args) -> int:
    prompt_path = PROJECT_ROOT / args.prompt
    if not prompt_path.exists():
        print(f"❌ 找不到檔案：{args.prompt}", file=sys.stderr)
        return 1

    bump_type = args.type
    if bump_type not in BUMP_RULES:
        print(f"❌ 無效的 bump type：{bump_type}（需為 major/minor/patch）", file=sys.stderr)
        return 1

    content = prompt_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)

    if not meta:
        print(f"⚠️  {args.prompt} 無 frontmatter，請先執行 init 指令", file=sys.stderr)
        return 1

    old_version = meta.get("version", "0.0.0").lstrip("v")
    new_version = bump_semver(old_version, bump_type)
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

    # 建立 changelog 條目
    changelog_entry = (
        f"\n  - version: \"{new_version}\"\n"
        f"    date: \"{today}\"\n"
        f"    type: \"{bump_type}\"\n"
        f"    changes: \"{args.changes}\"\n"
        f"    impact: \"{args.impact}\"\n"
    )

    # 更新 frontmatter
    def replace_version(m):
        return f'version: "{new_version}"'

    new_content = content
    # 更新 version 欄位
    new_content = re.sub(r'version:\s*["\']?[\d.]+["\']?', f'version: "{new_version}"', new_content, count=1)
    # 更新 last_updated（若存在）
    new_content = re.sub(r'last_updated:\s*["\']?[\d\-T:+]+["\']?',
                         f'last_updated: "{today}"', new_content, count=1)
    # 追加 changelog（在第一個 --- 結束前）
    if "changelog:" in new_content:
        # 找到 changelog: 後追加
        new_content = re.sub(r'(changelog:)', r'\1' + changelog_entry, new_content, count=1)
    else:
        # 在 frontmatter 結尾（第一個 --- 前）插入 changelog
        parts = new_content.split("---", 2)
        if len(parts) >= 3:
            parts[1] = parts[1].rstrip() + f"\nchangelog:{changelog_entry}"
            new_content = "---".join(parts)

    prompt_path.write_text(new_content, encoding="utf-8")
    print(f"✅ {args.prompt}")
    print(f"   版本: v{old_version} → v{new_version} ({bump_type})")
    print(f"   變更: {args.changes}")
    print(f"   影響: {args.impact}")

    # 更新 registry
    _update_registry(prompt_path)
    return 0


# ── 指令：init ────────────────────────────────────────────────────────────────

def cmd_init(args) -> int:
    prompt_path = PROJECT_ROOT / args.prompt
    if not prompt_path.exists():
        print(f"❌ 找不到檔案：{args.prompt}", file=sys.stderr)
        return 1

    content = prompt_path.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(content)

    if meta.get("version"):
        print(f"⚠️  已有版本 frontmatter (v{meta['version']})，跳過 init")
        return 0

    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    name = prompt_path.stem  # 用檔名作為預設 name

    fm = f"""---
name: "{name}"
version: "1.0.0"
last_updated: "{today}"
updated_by: "manual"
changelog:
  - version: "1.0.0"
    date: "{today}"
    type: "init"
    changes: "初版"
    impact: "n/a"
---

"""
    # 若原本沒有 frontmatter，直接在前面插入
    if not content.startswith("---"):
        new_content = fm + content
    else:
        new_content = content  # 已有 frontmatter 但無 version，不強制覆寫

    prompt_path.write_text(new_content, encoding="utf-8")
    print(f"✅ {args.prompt} 已加入初始 frontmatter (v1.0.0)")
    _update_registry(prompt_path)
    return 0


# ── 指令：report ──────────────────────────────────────────────────────────────

def cmd_report(args) -> int:
    files = collect_prompts()
    registry = _load_registry()

    version_data = []
    for p in files:
        content = p.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(content)
        key = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
        old_hash = registry.get("entries", {}).get(key, {}).get("content_hash", "")
        curr_hash = compute_hash(p)
        version_data.append({
            "file": key,
            "version": meta.get("version", "MISSING"),
            "content_hash": curr_hash,
            "changed_since_registry": old_hash != curr_hash and old_hash != "",
        })

    total = len(version_data)
    has_version = sum(1 for r in version_data if r["version"] != "MISSING")
    changed = [r for r in version_data if r["changed_since_registry"]]

    # 品質回歸偵測
    regressions = _detect_quality_regressions(registry)

    print(f"\n📊 Prompt 版本追蹤報告 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'─'*55}")
    print(f"  總計 prompt/template: {total}")
    print(f"  版本覆蓋率:           {has_version}/{total} ({round(has_version/max(total,1)*100)}%)")
    print(f"  自上次 registry 有變更: {len(changed)} 個")
    if changed:
        print("  變更清單：")
        for r in changed:
            print(f"    ⚡ {r['file']}  v{r['version']}")

    if regressions:
        print(f"\n🔴 品質回歸警告（{len(regressions)} 個）：")
        for reg in regressions:
            print(f"  - {reg['task_key']}: 品質分 {reg['before']:.1f} → {reg['after']:.1f} (Δ{reg['delta']:.1f})")
    else:
        print("\n✅ 無品質回歸")

    recommendations = []
    if has_version < total:
        recommendations.append(f"執行 `init` 補齊 {total - has_version} 個 prompt 的版本 frontmatter")
    if changed:
        recommendations.append(f"對 {len(changed)} 個已變更 prompt 執行 `bump` 遞增版本號")
    if regressions:
        recommendations.append("調查品質回歸原因，確認是否為 prompt 變更所致")

    if recommendations:
        print("\n💡 建議行動：")
        for i, r in enumerate(recommendations, 1):
            print(f"  {i}. {r}")

    # 寫入 results/prompt-version-report.json（供 check-health.ps1 / system-audit 引用）
    report_path = PROJECT_ROOT / "results" / "prompt-version-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "agent": "prompt-version-tracker",
        "task_type": "auto",
        "task_key": "prompt_version_tracker",
        "status": "success",
        "coverage": {
            "total": total,
            "has_version": has_version,
            "pct": round(has_version / max(total, 1) * 100, 1),
        },
        "changed_since_registry": len(changed),
        "regressions": [
            {"task_key": r["task_key"], "delta": r["delta"]}
            for r in regressions
        ],
        "recommendations": recommendations,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "summary": (
            f"版本覆蓋率 {round(has_version/max(total,1)*100)}%（{has_version}/{total}），"
            f"回歸 {len(regressions)} 個"
        ),
    }
    report_path.write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n📄 報告已寫入：results/prompt-version-report.json")

    return 0


# ── 品質回歸偵測 ──────────────────────────────────────────────────────────────

def _detect_quality_regressions(registry: dict) -> list[dict]:
    """比對當前結果檔案與 registry 記錄的品質分數，偵測回歸。"""
    regressions = []
    prev_quality = registry.get("quality_snapshot", {})

    for rf in glob.glob(QUALITY_RESULTS_GLOB):
        try:
            r = json.loads(Path(rf).read_text(encoding="utf-8"))
            task_key = r.get("task_key", "")
            qs = r.get("quality_score", {})
            avg = qs.get("average") if isinstance(qs, dict) else None
            if not task_key or avg is None:
                continue
            if task_key in prev_quality:
                prev_avg = prev_quality[task_key]
                delta = avg - prev_avg
                if delta < -1.0:  # 品質下降 > 1 分視為回歸
                    regressions.append({
                        "task_key": task_key,
                        "before": prev_avg,
                        "after": avg,
                        "delta": delta,
                    })
        except Exception:
            continue

    return regressions


# ── Registry 操作 ─────────────────────────────────────────────────────────────

def _load_registry() -> dict:
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"generated_at": "", "entries": {}, "quality_snapshot": {}}


def _update_registry(prompt_path: Path) -> None:
    """更新單一 prompt 的 registry 記錄。"""
    registry = _load_registry()
    key = str(prompt_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    registry.setdefault("entries", {})[key] = {
        "content_hash": compute_hash(prompt_path),
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    registry["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Prompt Versioning CLI")
    sub = parser.add_subparsers(dest="command")

    # check
    p_check = sub.add_parser("check", help="掃描所有 prompt 版本狀態")
    p_check.add_argument("--dir", default="", help="指定掃描目錄（預設掃描全部）")

    # bump
    p_bump = sub.add_parser("bump", help="遞增版本號並更新 changelog")
    p_bump.add_argument("--prompt", required=True, help="prompt 相對路徑")
    p_bump.add_argument("--type", required=True, choices=["major", "minor", "patch"])
    p_bump.add_argument("--changes", required=True, help="變更描述")
    p_bump.add_argument("--impact", default="low", choices=["low", "medium", "high"])

    # init
    p_init = sub.add_parser("init", help="加入初始版本 frontmatter")
    p_init.add_argument("--prompt", required=True, help="prompt 相對路徑")

    # report
    sub.add_parser("report", help="生成版本覆蓋率與品質回歸報告")

    args = parser.parse_args()
    os.chdir(PROJECT_ROOT)  # 確保相對路徑正確

    if args.command == "check":
        sys.exit(cmd_check(args))
    elif args.command == "bump":
        sys.exit(cmd_bump(args))
    elif args.command == "init":
        sys.exit(cmd_init(args))
    elif args.command == "report":
        sys.exit(cmd_report(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
