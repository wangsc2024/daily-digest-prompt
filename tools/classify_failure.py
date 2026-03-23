#!/usr/bin/env python3
"""
ADR-20260323-042: 失敗模式 Taxonomy 與根因自動分類

使用方式：
  uv run python tools/classify_failure.py --report           # 分析最近 7 天並輸出報告
  uv run python tools/classify_failure.py --report --dry-run # 乾跑模式（不寫入檔案）
  uv run python tools/classify_failure.py --days 3           # 自訂天數
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = PROJECT_ROOT / "config" / "failure-taxonomy.yaml"
LOGS_DIR = PROJECT_ROOT / "logs" / "structured"
OUTPUT_PATH = PROJECT_ROOT / "analysis" / "failure-classification.json"


def load_taxonomy() -> dict:
    """載入 failure-taxonomy.yaml，回傳 {category: {keywords: [...]}} 結構。"""
    if not TAXONOMY_PATH.exists():
        print(f"[WARN] Taxonomy 不存在：{TAXONOMY_PATH}", file=sys.stderr)
        return {}
    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        name: {"keywords": cat.get("keywords", [])}
        for name, cat in data.get("categories", {}).items()
    }


def classify_record(record: dict, categories: dict) -> str:
    """依 taxonomy keywords 分類單一日誌記錄。"""
    if not categories:
        return "unclassified"
    tags = record.get("tags", [])
    text = (
        " ".join(tags)
        + " " + record.get("error_category", "")
        + " " + record.get("message", "")
    ).lower()
    scores = {
        cat: sum(1 for kw in info["keywords"] if kw.lower() in text)
        for cat, info in categories.items()
    }
    best = {cat: s for cat, s in scores.items() if s > 0}
    return max(best, key=best.get) if best else "unclassified"


def scan_failures(days: int, categories: dict) -> list[dict]:
    """掃描最近 N 天的 JSONL 日誌，提取失敗記錄並分類。"""
    today = datetime.now().date()
    failures = []
    for d in range(days):
        log_file = LOGS_DIR / f"{(today - timedelta(days=d)).isoformat()}.jsonl"
        if not log_file.exists():
            continue
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tags = record.get("tags", [])
                if not any(t in tags for t in ("error", "warn", "block", "blocked")):
                    continue
                failures.append({
                    "ts": record.get("ts", ""),
                    "tool": record.get("tool", ""),
                    "tags": tags,
                    "error_category": record.get("error_category", ""),
                    "classified_as": classify_record(record, categories),
                })
    return failures


def generate_report(failures: list[dict], days: int) -> dict:
    """產生失敗分類統計報告。"""
    breakdown = dict(Counter(f["classified_as"] for f in failures))
    return {
        "generated_at": datetime.now().isoformat(),
        "period_days": days,
        "total_failures": len(failures),
        "failure_breakdown": breakdown,
        "top_category": max(breakdown, key=breakdown.get) if breakdown else "none",
        "details": failures[:50],
    }


def main() -> int:
    args = sys.argv[1:]
    days = 7
    dry_run = "--dry-run" in args
    if "--report" not in args:
        print("用法: uv run python tools/classify_failure.py --report [--dry-run] [--days N]")
        return 0
    for i, arg in enumerate(args):
        if arg == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
    categories = load_taxonomy()
    if not categories:
        print("[ERROR] 無法載入 taxonomy", file=sys.stderr)
        return 1
    failures = scan_failures(days, categories)
    report = generate_report(failures, days)
    print(f"失敗分類報告（最近 {days} 天）")
    print(f"總失敗數: {report['total_failures']}")
    for cat, count in sorted(report["failure_breakdown"].items(), key=lambda x: -x[1]):
        pct = count / report["total_failures"] * 100 if report["total_failures"] > 0 else 0
        print(f"  {cat}: {count} ({pct:.1f}%)")
    if not dry_run:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n報告已寫入: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
