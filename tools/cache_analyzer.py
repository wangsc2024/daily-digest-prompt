#!/usr/bin/env python3
"""cache_analyzer.py - 快取命中率分析工具（ADR-046）
分析 JSONL 日誌中的快取事件，計算命中率並與目標比較。
"""
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import argparse

PROJECT_ROOT = Path(__file__).parent.parent

def load_hit_rate_targets():
    """從 cache-policy.yaml 讀取命中率目標"""
    try:
        import yaml
        with open(PROJECT_ROOT / "config" / "cache-policy.yaml", encoding="utf-8") as f:
            policy = yaml.safe_load(f)
        return policy.get("hit_rate_targets", {}).get("per_source", {})
    except Exception:
        return {}

def analyze_cache_events(days: int = 7) -> dict:
    """分析 JSONL 日誌中的快取事件"""
    log_dir = PROJECT_ROOT / "logs" / "structured"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stats = defaultdict(lambda: {"hits": 0, "misses": 0, "degraded": 0})

    if not log_dir.exists():
        return {}

    for log_file in sorted(log_dir.glob("*.jsonl")):
        try:
            with open(log_file, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts_str = entry.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue
                    except Exception:
                        continue

                    # 從 summary/tags 辨識快取事件
                    summary = entry.get("summary", "").lower()
                    tags = entry.get("tags", [])

                    source = None
                    for src in ["todoist", "pingtung", "hackernews", "knowledge", "gmail", "chatroom"]:
                        if src in summary or any(src in str(t) for t in tags):
                            source = "pingtung-news" if src == "pingtung" else src
                            break

                    if source is None:
                        continue

                    if "cache_hit" in tags or "cache-hit" in summary or "valid" in summary:
                        stats[source]["hits"] += 1
                    elif "cache_miss" in tags or "cache-miss" in summary:
                        stats[source]["misses"] += 1
                    elif "degraded" in tags or "stale" in summary:
                        stats[source]["degraded"] += 1
        except Exception:
            continue

    return dict(stats)

def compute_hit_rates(stats: dict) -> dict:
    """計算各端點命中率"""
    results = {}
    for source, counts in stats.items():
        total = counts["hits"] + counts["misses"] + counts["degraded"]
        if total == 0:
            continue
        hit_rate = counts["hits"] / total
        results[source] = {
            "hit_rate": round(hit_rate, 3),
            "hits": counts["hits"],
            "misses": counts["misses"],
            "degraded": counts["degraded"],
            "total": total,
        }
    return results

def main():
    parser = argparse.ArgumentParser(description="快取命中率分析工具")
    parser.add_argument("--days", type=int, default=7, help="分析天數（預設 7）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    args = parser.parse_args()

    stats = analyze_cache_events(days=args.days)
    hit_rates = compute_hit_rates(stats)
    targets = load_hit_rate_targets()

    if args.json:
        print(json.dumps(hit_rates, ensure_ascii=False, indent=2))
        return

    print(f"\n=== 快取命中率分析（近 {args.days} 天）===")

    if not hit_rates:
        print("（無足夠的快取事件日誌，可能需要 post_tool_logger 產生更多標籤化日誌）")
        return

    overall_hits = sum(v["hits"] for v in hit_rates.values())
    overall_total = sum(v["total"] for v in hit_rates.values())
    overall_rate = overall_hits / overall_total if overall_total > 0 else 0
    target_overall = targets.get("overall", 0.40)
    status = "OK" if overall_rate >= target_overall else "BELOW TARGET"
    print(f"\n整體命中率：{overall_rate:.1%} [{status}]（目標 {target_overall:.0%}+）")

    print("\n各端點：")
    for source, data in sorted(hit_rates.items()):
        rate = data["hit_rate"]
        target = targets.get(source, 0.40)
        status = "OK" if rate >= target else "BELOW"
        print(f"  {source:15s}: {rate:.1%} [{status}] (目標 {target:.0%}, {data['hits']}/{data['total']})")

    print()

if __name__ == "__main__":
    main()
