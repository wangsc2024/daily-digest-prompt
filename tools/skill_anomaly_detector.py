"""
Skill Anomaly Detector (ADR-038)

掃描 logs/structured/*.jsonl，統計各 Skill/Tool 的呼叫次數、I/O 大小、
失敗率，偵測 5 種異常模式，分析低效呼叫鏈，產出建議報告。

輸出：
  - analysis/skill-usage-baseline.json
  - analysis/inefficient-skill-chains.json
  - context/skill-health-report.json
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Project root: two levels up from tools/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs" / "structured"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
CONTEXT_DIR = PROJECT_ROOT / "context"

LOOKBACK_DAYS = 7

# Anomaly thresholds
OVERUSE_SIGMA = 3
UNDERUSE_MIN_CALLS_7D = 1
HIGH_FAILURE_RATE = 0.30
INEFFICIENT_IO_BYTES = 10_000  # 10 KB per call
DUPLICATE_API_THRESHOLD = 3  # same URL in one session
REPEATED_READ_THRESHOLD = 3  # same file read >N times in a session


def _today() -> datetime:
    """Return current date in local timezone."""
    return datetime.now(timezone(timedelta(hours=8)))


def _date_range(days: int) -> list[str]:
    """Return list of date strings (YYYY-MM-DD) for recent N days."""
    today = _today().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


def load_entries(days: int = LOOKBACK_DAYS) -> list[dict]:
    """Load JSONL entries from recent N days."""
    entries: list[dict] = []
    dates = _date_range(days)
    for date_str in dates:
        path = LOGS_DIR / f"{date_str}.jsonl"
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    return entries


def compute_tool_stats(entries: list[dict]) -> dict[str, dict]:
    """Compute per-tool statistics: call_count, total_input, total_output, failures, avg_io."""
    stats: dict[str, dict] = defaultdict(lambda: {
        "call_count": 0,
        "total_input": 0,
        "total_output": 0,
        "failures": 0,
        "durations": [],
    })
    for e in entries:
        tool = e.get("tool", "unknown")
        s = stats[tool]
        s["call_count"] += 1
        s["total_input"] += e.get("input_len", 0)
        s["total_output"] += e.get("output_len", 0)
        if e.get("has_error", False):
            s["failures"] += 1
    # Finalize
    result = {}
    for tool, s in stats.items():
        count = s["call_count"]
        result[tool] = {
            "call_count": count,
            "total_input_bytes": s["total_input"],
            "total_output_bytes": s["total_output"],
            "avg_io_bytes": round((s["total_input"] + s["total_output"]) / count) if count else 0,
            "failure_count": s["failures"],
            "failure_rate": round(s["failures"] / count, 4) if count else 0,
        }
    return result


def detect_overuse(tool_stats: dict[str, dict]) -> list[dict]:
    """Detect tools with call count > mean + 3σ."""
    counts = [s["call_count"] for s in tool_stats.values()]
    if len(counts) < 2:
        return []
    mean = statistics.mean(counts)
    stdev = statistics.stdev(counts)
    if stdev == 0:
        return []
    threshold = mean + OVERUSE_SIGMA * stdev
    anomalies = []
    for tool, s in tool_stats.items():
        if s["call_count"] > threshold:
            anomalies.append({
                "pattern": "overuse",
                "tool": tool,
                "call_count": s["call_count"],
                "threshold": round(threshold, 1),
                "sigma": round((s["call_count"] - mean) / stdev, 2),
                "suggestion": f"工具 {tool} 呼叫次數異常偏高（{s['call_count']} 次，閾值 {threshold:.0f}）。"
                              f"建議檢查是否有重複呼叫、可合併的操作，或可使用快取減少呼叫。",
            })
    return anomalies


def detect_underuse(tool_stats: dict[str, dict]) -> list[dict]:
    """Detect tools called fewer than threshold in 7 days."""
    anomalies = []
    for tool, s in tool_stats.items():
        if s["call_count"] < UNDERUSE_MIN_CALLS_7D:
            anomalies.append({
                "pattern": "underuse",
                "tool": tool,
                "call_count": s["call_count"],
                "threshold": UNDERUSE_MIN_CALLS_7D,
                "suggestion": f"工具 {tool} 近 7 天幾乎未使用（{s['call_count']} 次）。"
                              f"建議確認是否為廢棄工具，或是否有應使用但未使用的場景。",
            })
    return anomalies


def detect_high_failure_rate(tool_stats: dict[str, dict]) -> list[dict]:
    """Detect tools with failure rate > 30%."""
    anomalies = []
    for tool, s in tool_stats.items():
        if s["call_count"] >= 3 and s["failure_rate"] > HIGH_FAILURE_RATE:
            anomalies.append({
                "pattern": "high_failure_rate",
                "tool": tool,
                "failure_rate": s["failure_rate"],
                "failure_count": s["failure_count"],
                "call_count": s["call_count"],
                "threshold": HIGH_FAILURE_RATE,
                "suggestion": f"工具 {tool} 失敗率 {s['failure_rate']:.0%}（{s['failure_count']}/{s['call_count']}）。"
                              f"建議檢查錯誤日誌，修復根因或增加重試/降級機制。",
            })
    return anomalies


def detect_inefficient_io(tool_stats: dict[str, dict]) -> list[dict]:
    """Detect tools with avg I/O > 10KB per call."""
    anomalies = []
    for tool, s in tool_stats.items():
        if s["call_count"] >= 3 and s["avg_io_bytes"] > INEFFICIENT_IO_BYTES:
            anomalies.append({
                "pattern": "inefficient_io",
                "tool": tool,
                "avg_io_bytes": s["avg_io_bytes"],
                "threshold": INEFFICIENT_IO_BYTES,
                "call_count": s["call_count"],
                "suggestion": f"工具 {tool} 平均 I/O {s['avg_io_bytes']:,} bytes/call（閾值 {INEFFICIENT_IO_BYTES:,}）。"
                              f"建議減少單次傳輸量，使用增量讀取或快取機制。",
            })
    return anomalies


def detect_duplicate_api(entries: list[dict]) -> list[dict]:
    """Detect same URL/summary called >3 times in a single session."""
    # Group by session (sid)
    sessions: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        sid = e.get("sid", "")
        if sid:
            sessions[sid].append(e)

    anomalies = []
    seen_pairs: set[tuple[str, str]] = set()
    for sid, session_entries in sessions.items():
        url_counts: Counter = Counter()
        for e in session_entries:
            summary = e.get("summary", "")
            tool = e.get("tool", "")
            if summary:
                url_counts[(tool, summary)] += 1
        for (tool, summary), count in url_counts.items():
            if count > DUPLICATE_API_THRESHOLD:
                key = (tool, summary)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                short_summary = summary if len(summary) <= 80 else summary[:77] + "..."
                anomalies.append({
                    "pattern": "duplicate_api",
                    "tool": tool,
                    "summary": short_summary,
                    "count_in_session": count,
                    "session_id": sid,
                    "threshold": DUPLICATE_API_THRESHOLD,
                    "suggestion": f"同一 session 中 {tool}('{short_summary}') 被呼叫 {count} 次。"
                                  f"建議快取結果或合併呼叫以減少重複。",
                })
    return anomalies


def analyze_skill_chains(entries: list[dict]) -> dict:
    """Analyze call chains per session for inefficiencies."""
    sessions: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        sid = e.get("sid") or e.get("trace_id", "")
        if sid:
            sessions[sid].append(e)

    inefficient_chains: list[dict] = []

    for sid, session_entries in sessions.items():
        # Sort by timestamp
        session_entries.sort(key=lambda x: x.get("ts", ""))

        # Pattern 1: Read same file >3 times
        read_files: Counter = Counter()
        for e in session_entries:
            if e.get("tool") == "Read":
                read_files[e.get("summary", "")] += 1
        for filepath, count in read_files.items():
            if count > REPEATED_READ_THRESHOLD:
                short_path = filepath if len(filepath) <= 80 else filepath[:77] + "..."
                inefficient_chains.append({
                    "type": "repeated_read",
                    "session_id": sid,
                    "file": short_path,
                    "read_count": count,
                    "suggestion": f"同一 session 重複讀取 '{short_path}' {count} 次。建議快取首次讀取結果。",
                })

        # Pattern 2: Circular calls (A->B->A pattern in tool sequence)
        tool_sequence = [e.get("tool", "") for e in session_entries]
        if len(tool_sequence) >= 3:
            circular_pairs: set[tuple[str, str]] = set()
            for i in range(len(tool_sequence) - 2):
                if tool_sequence[i] == tool_sequence[i + 2] and tool_sequence[i] != tool_sequence[i + 1]:
                    pair = (tool_sequence[i], tool_sequence[i + 1])
                    circular_pairs.add(pair)
            for a, b in circular_pairs:
                # Only flag if it happens frequently (>2 oscillations)
                pattern_count = sum(
                    1 for i in range(len(tool_sequence) - 2)
                    if tool_sequence[i] == a and tool_sequence[i + 1] == b and tool_sequence[i + 2] == a
                )
                if pattern_count >= 2:
                    inefficient_chains.append({
                        "type": "circular_call",
                        "session_id": sid,
                        "pattern": f"{a} ↔ {b}",
                        "oscillation_count": pattern_count,
                        "suggestion": f"偵測到 {a} ↔ {b} 來回切換 {pattern_count} 次。建議合併操作或重構工作流程。",
                    })

        # Pattern 3: Not using cache - reading config files that should be cached
        config_reads = [
            e for e in session_entries
            if e.get("tool") == "Read" and ("config" in e.get("summary", "").lower() or "yaml" in e.get("summary", "").lower())
        ]
        config_file_counts: Counter = Counter(e.get("summary", "") for e in config_reads)
        for filepath, count in config_file_counts.items():
            if count > 2:
                short_path = filepath if len(filepath) <= 80 else filepath[:77] + "..."
                inefficient_chains.append({
                    "type": "uncached_config",
                    "session_id": sid,
                    "file": short_path,
                    "read_count": count,
                    "suggestion": f"配置檔 '{short_path}' 在同一 session 讀取 {count} 次，建議載入後快取。",
                })

    # Deduplicate by type+file (keep highest count)
    deduped: dict[str, dict] = {}
    for chain in inefficient_chains:
        key = f"{chain['type']}:{chain.get('file', chain.get('pattern', ''))}"
        if key not in deduped or chain.get("read_count", chain.get("oscillation_count", 0)) > deduped[key].get("read_count", deduped[key].get("oscillation_count", 0)):
            deduped[key] = chain

    return {
        "scan_period_days": LOOKBACK_DAYS,
        "total_sessions_analyzed": len(sessions),
        "inefficient_chains": list(deduped.values()),
        "generated_at": _today().isoformat(),
    }


def build_health_report(
    tool_stats: dict[str, dict],
    anomalies: list[dict],
    chain_analysis: dict,
    total_entries: int,
) -> dict:
    """Build the final skill health report with suggestions."""
    # Group anomalies by tool
    tool_anomalies: dict[str, list[dict]] = defaultdict(list)
    for a in anomalies:
        tool_anomalies[a.get("tool", "unknown")].append(a)

    # Per-tool health
    tool_health: list[dict] = []
    for tool, stats in sorted(tool_stats.items(), key=lambda x: -x[1]["call_count"]):
        issues = tool_anomalies.get(tool, [])
        health_status = "healthy" if not issues else "warning" if len(issues) == 1 else "critical"
        tool_health.append({
            "tool": tool,
            "status": health_status,
            "call_count": stats["call_count"],
            "failure_rate": stats["failure_rate"],
            "avg_io_bytes": stats["avg_io_bytes"],
            "anomaly_count": len(issues),
            "suggestions": [i["suggestion"] for i in issues],
        })

    # Summary
    total_anomalies = len(anomalies)
    pattern_counts = Counter(a["pattern"] for a in anomalies)

    return {
        "report_version": 1,
        "generated_at": _today().isoformat(),
        "scan_period_days": LOOKBACK_DAYS,
        "total_log_entries": total_entries,
        "total_tools_tracked": len(tool_stats),
        "summary": {
            "total_anomalies": total_anomalies,
            "anomalies_by_pattern": dict(pattern_counts),
            "inefficient_chains": len(chain_analysis.get("inefficient_chains", [])),
            "overall_health": (
                "healthy" if total_anomalies == 0
                else "warning" if total_anomalies <= 3
                else "critical"
            ),
        },
        "tool_health": tool_health,
        "top_suggestions": [a["suggestion"] for a in anomalies[:10]],
    }


def write_json(path: Path, data: dict) -> None:
    """Write JSON with UTF-8, no ASCII escaping."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Written: {path}")


def main() -> None:
    print(f"[Skill Anomaly Detector] Scanning {LOOKBACK_DAYS} days of logs...")
    print(f"  Logs dir: {LOGS_DIR}")

    # Load
    entries = load_entries(LOOKBACK_DAYS)
    print(f"  Loaded {len(entries)} log entries")

    if not entries:
        print("  No log entries found. Generating empty reports.")

    # Tool stats
    tool_stats = compute_tool_stats(entries)
    print(f"  Tracked {len(tool_stats)} unique tools")

    # Detect anomalies
    anomalies: list[dict] = []
    anomalies.extend(detect_overuse(tool_stats))
    anomalies.extend(detect_underuse(tool_stats))
    anomalies.extend(detect_high_failure_rate(tool_stats))
    anomalies.extend(detect_inefficient_io(tool_stats))
    anomalies.extend(detect_duplicate_api(entries))
    print(f"  Detected {len(anomalies)} anomalies")

    # Chain analysis
    chain_analysis = analyze_skill_chains(entries)
    print(f"  Found {len(chain_analysis['inefficient_chains'])} inefficient chains")

    # Health report
    health_report = build_health_report(tool_stats, anomalies, chain_analysis, len(entries))

    # Baseline (tool stats + anomalies)
    baseline = {
        "generated_at": _today().isoformat(),
        "scan_period_days": LOOKBACK_DAYS,
        "total_entries": len(entries),
        "tool_stats": tool_stats,
        "anomalies": anomalies,
    }

    # Write outputs
    print("\nWriting output files:")
    write_json(ANALYSIS_DIR / "skill-usage-baseline.json", baseline)
    write_json(ANALYSIS_DIR / "inefficient-skill-chains.json", chain_analysis)
    write_json(CONTEXT_DIR / "skill-health-report.json", health_report)

    # Summary
    print("\n[Summary]")
    print(f"  Health: {health_report['summary']['overall_health']}")
    print(f"  Anomalies: {health_report['summary']['total_anomalies']}")
    print(f"  Inefficient chains: {health_report['summary']['inefficient_chains']}")
    if anomalies:
        print(f"  Top anomaly patterns: {dict(Counter(a['pattern'] for a in anomalies))}")


if __name__ == "__main__":
    main()
