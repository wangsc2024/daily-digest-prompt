#!/usr/bin/env python3
"""
Structured Hook Logs Query Tool

Query and analyze the structured JSONL logs produced by the hook system.

Usage:
  python3 hooks/query_logs.py                     # Today's summary
  python3 hooks/query_logs.py --days 7             # Last 7 days
  python3 hooks/query_logs.py --tag api-call       # Filter by tag
  python3 hooks/query_logs.py --blocked            # Show only blocked events
  python3 hooks/query_logs.py --errors             # Show only errors
  python3 hooks/query_logs.py --cache-audit        # Cache bypass analysis
  python3 hooks/query_logs.py --sessions           # Session summaries
  python3 hooks/query_logs.py --format json        # JSON output
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from collections import Counter


LOG_DIR = os.path.join("logs", "structured")


def load_entries(days: int) -> list:
    """Load JSONL entries from the last N days."""
    entries = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"{date}.jsonl")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            entry["_date"] = date
                            entries.append(entry)
                        except json.JSONDecodeError:
                            pass
    return entries


def load_session_summaries(days: int) -> list:
    """Load session summary entries."""
    summary_file = os.path.join(LOG_DIR, "session-summary.jsonl")
    if not os.path.exists(summary_file):
        return []

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    summaries = []
    with open(summary_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if entry.get("ts", "") >= cutoff:
                        summaries.append(entry)
                except json.JSONDecodeError:
                    pass
    return summaries


def print_summary(entries: list, days: int):
    """Print human-readable summary."""
    if not entries:
        print(f"  近 {days} 天無結構化日誌")
        return

    total = len(entries)
    blocked = [e for e in entries if e.get("event") == "blocked"]
    errors = [e for e in entries if e.get("has_error")]
    api_calls = [e for e in entries if "api-call" in e.get("tags", [])]
    cache_reads = [e for e in entries if "cache-read" in e.get("tags", [])]
    skill_reads = [e for e in entries if "skill-read" in e.get("tags", [])]
    sub_agents = [e for e in entries if "sub-agent" in e.get("tags", [])]

    # Per-day breakdown
    dates = Counter(e.get("_date", "unknown") for e in entries)

    print(f"  期間: 近 {days} 天 ({len(dates)} 天有記錄)")
    print(f"  總工具呼叫: {total}")
    print()

    # Tool distribution
    tool_counts = Counter(e.get("tool", "?") for e in entries)
    print("  [工具分布]")
    for tool, count in tool_counts.most_common():
        bar = "#" * min(count, 40)
        print(f"    {tool:8s} {count:4d}  {bar}")
    print()

    # Tag frequency
    all_tags = []
    for e in entries:
        all_tags.extend(e.get("tags", []))
    tag_counts = Counter(all_tags)
    print("  [標籤頻率 Top 10]")
    for tag, count in tag_counts.most_common(10):
        print(f"    {tag:20s} {count:4d}")
    print()

    # Key metrics
    print("  [關鍵指標]")
    print(f"    API 呼叫:    {len(api_calls)}")
    print(f"    快取讀取:    {len(cache_reads)}")
    print(f"    Skill 讀取:  {len(skill_reads)}")
    print(f"    子 Agent:    {len(sub_agents)}")

    # Health indicators
    blocked_color = "\033[31m" if blocked else "\033[32m"
    error_color = "\033[31m" if errors else "\033[32m"
    reset = "\033[0m"
    print(f"    攔截事件:    {blocked_color}{len(blocked)}{reset}")
    print(f"    錯誤事件:    {error_color}{len(errors)}{reset}")

    if blocked:
        print()
        print("  [攔截詳情]")
        for b in blocked:
            print(f"    [{b.get('ts', '?')[:19]}] {b.get('tool')}: {b.get('reason', '?')}")

    if errors:
        print()
        print("  [錯誤詳情 (前 5 筆)]")
        for e in errors[:5]:
            print(f"    [{e.get('ts', '?')[:19]}] {e.get('tool')}: {e.get('summary', '?')[:80]}")


def print_cache_audit(entries: list):
    """Audit cache usage patterns."""
    print()
    print("  [快取審計]")

    api_calls = [e for e in entries if "api-call" in e.get("tags", [])]
    cache_reads = [e for e in entries if "cache-read" in e.get("tags", [])]
    cache_writes = [e for e in entries if "cache-write" in e.get("tags", [])]

    # Group by source
    sources = ["todoist", "pingtung-news", "hackernews", "knowledge", "gmail"]
    print(f"    {'來源':15s} {'API呼叫':>8s} {'快取讀取':>8s} {'快取寫入':>8s} {'狀態':>8s}")
    print(f"    {'─' * 15} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")

    for source in sources:
        apis = len([e for e in api_calls if source in e.get("tags", [])])
        reads = len([e for e in cache_reads if source in e.get("tags", [])])
        writes = len([e for e in cache_writes if source in e.get("tags", [])])

        if apis == 0 and reads == 0:
            status = "無活動"
        elif reads >= apis:
            status = "正常"
        elif reads > 0:
            status = "部分"
        else:
            status = "繞過!"

        color = "\033[32m" if status == "正常" else "\033[33m" if status in ("部分", "無活動") else "\033[31m"
        reset = "\033[0m"
        print(f"    {source:15s} {apis:>8d} {reads:>8d} {writes:>8d} {color}{status:>8s}{reset}")


def print_sessions(days: int):
    """Print session summaries."""
    summaries = load_session_summaries(days)
    if not summaries:
        print(f"  近 {days} 天無 session 記錄")
        return

    print(f"  近 {days} 天 session 記錄: {len(summaries)} 筆")
    print()
    print(f"    {'時間':20s} {'呼叫':>5s} {'API':>5s} {'快取':>5s} {'攔截':>4s} {'錯誤':>4s} {'告警':>4s} {'狀態':>8s}")
    print(f"    {'─' * 20} {'─' * 5} {'─' * 5} {'─' * 5} {'─' * 4} {'─' * 4} {'─' * 4} {'─' * 8}")

    for s in summaries[-20:]:  # Last 20 sessions
        ts = s.get("ts", "?")[:19]
        total = s.get("total_calls", 0)
        api = s.get("api_calls", 0)
        cache = s.get("cache_reads", 0)
        blocked = s.get("blocked", 0)
        errors = s.get("errors", 0)
        alert = "Y" if s.get("alert_sent") else "-"
        status = s.get("status", "?")

        color = "\033[32m" if status == "healthy" else "\033[33m" if status == "warning" else "\033[31m"
        reset = "\033[0m"
        print(f"    {ts:20s} {total:>5d} {api:>5d} {cache:>5d} {blocked:>4d} {errors:>4d} {alert:>4s} {color}{status:>8s}{reset}")


def main():
    parser = argparse.ArgumentParser(description="查詢結構化 Hook 日誌")
    parser.add_argument("--days", type=int, default=1, help="查詢天數 (預設: 1)")
    parser.add_argument("--tag", type=str, help="依標籤過濾")
    parser.add_argument("--blocked", action="store_true", help="僅顯示攔截事件")
    parser.add_argument("--errors", action="store_true", help="僅顯示錯誤事件")
    parser.add_argument("--cache-audit", action="store_true", help="快取使用審計")
    parser.add_argument("--sessions", action="store_true", help="Session 摘要")
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="輸出格式"
    )
    args = parser.parse_args()

    print()
    print("========================================")
    print("  Hook 結構化日誌報告")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("========================================")
    print()

    if args.sessions:
        print_sessions(args.days)
        print()
        return

    entries = load_entries(args.days)

    # Apply filters
    if args.blocked:
        entries = [e for e in entries if e.get("event") == "blocked"]
        print(f"  過濾: 僅攔截事件 ({len(entries)} 筆)")
    elif args.errors:
        entries = [e for e in entries if e.get("has_error")]
        print(f"  過濾: 僅錯誤事件 ({len(entries)} 筆)")
    elif args.tag:
        entries = [e for e in entries if args.tag in e.get("tags", [])]
        print(f"  過濾: 標籤 '{args.tag}' ({len(entries)} 筆)")

    if args.format == "json":
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return

    print_summary(entries, args.days)

    if args.cache_audit:
        print_cache_audit(entries)

    print()
    print("========================================")
    print()


if __name__ == "__main__":
    main()
