#!/usr/bin/env python3
"""
Stop Hook - Session-end health check + auto-alert via ntfy.

When the Agent session ends, this hook:
  1. Reads today's structured log (logs/structured/YYYY-MM-DD.jsonl)
  2. Analyzes: blocked events, errors, cache bypass violations
  3. Writes session summary to logs/structured/session-summary.jsonl
  4. If issues detected, sends ntfy alert to wangsc2025

Alert severity:
  - critical: blocked events OR 5+ errors
  - warning: 1-4 errors OR cache bypass detected
  - info (no alert): everything healthy
"""
import sys
import json
import os
import subprocess
from datetime import datetime
from collections import Counter

NTFY_TOPIC = "wangsc2025"


def read_todays_log() -> list:
    """Read today's structured log entries."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join("logs", "structured", f"{today}.jsonl")

    if not os.path.exists(log_file):
        return []

    entries = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def analyze_entries(entries: list) -> dict:
    """Analyze log entries and return analysis results."""
    blocked = [e for e in entries if e.get("event") == "blocked"]
    errors = [e for e in entries if e.get("has_error")]
    api_calls = [e for e in entries if "api-call" in e.get("tags", [])]
    cache_reads = [e for e in entries if "cache-read" in e.get("tags", [])]
    cache_writes = [e for e in entries if "cache-write" in e.get("tags", [])]
    skill_reads = [e for e in entries if "skill-read" in e.get("tags", [])]
    sub_agents = [e for e in entries if "sub-agent" in e.get("tags", [])]

    # Detect cache bypass: API source called without preceding cache read
    api_sources = set()
    for entry in api_calls:
        for tag in entry.get("tags", []):
            if tag in ("todoist", "pingtung-news", "hackernews", "knowledge", "gmail"):
                api_sources.add(tag)

    cache_read_sources = set()
    for entry in cache_reads:
        summary = entry.get("summary", "").lower()
        for source, patterns in {
            "todoist": ["todoist"],
            "pingtung-news": ["pingtung"],
            "hackernews": ["hackernews"],
            "knowledge": ["knowledge"],
            "gmail": ["gmail"],
        }.items():
            if any(p in summary for p in patterns):
                cache_read_sources.add(source)

    cache_bypassed = api_sources - cache_read_sources

    # Count blocked reasons
    block_reasons = Counter(e.get("reason", "unknown") for e in blocked)

    # Count error tools
    error_tools = Counter(e.get("tool", "unknown") for e in errors)

    # Tag frequency
    all_tags = []
    for e in entries:
        all_tags.extend(e.get("tags", []))
    tag_counts = Counter(all_tags)

    return {
        "total_calls": len(entries),
        "blocked": blocked,
        "blocked_count": len(blocked),
        "errors": errors,
        "error_count": len(errors),
        "api_calls": len(api_calls),
        "cache_reads": len(cache_reads),
        "cache_writes": len(cache_writes),
        "skill_reads": len(skill_reads),
        "sub_agents": len(sub_agents),
        "cache_bypassed": list(cache_bypassed),
        "block_reasons": dict(block_reasons),
        "error_tools": dict(error_tools),
        "tag_counts": dict(tag_counts.most_common(15)),
    }


def build_alert_message(analysis: dict) -> tuple:
    """Build alert message. Returns (severity, title, message) or None if healthy."""
    issues = []
    severity = "info"

    # Check blocked events
    if analysis["blocked_count"] > 0:
        issues.append(f"攔截 {analysis['blocked_count']} 次違規操作:")
        for reason, count in analysis["block_reasons"].items():
            issues.append(f"  - {reason} (x{count})")
        severity = "critical" if analysis["blocked_count"] >= 3 else "warning"

    # Check errors
    if analysis["error_count"] > 0:
        issues.append(f"偵測到 {analysis['error_count']} 次工具錯誤:")
        for tool, count in analysis["error_tools"].items():
            issues.append(f"  - {tool} (x{count})")
        if analysis["error_count"] >= 5:
            severity = "critical"
        elif severity != "critical":
            severity = "warning"

    # Check cache bypass
    if analysis["cache_bypassed"]:
        bypassed_str = ", ".join(analysis["cache_bypassed"])
        issues.append(f"快取繞過警告 (未先查快取): {bypassed_str}")
        if severity == "info":
            severity = "warning"

    if not issues:
        return None

    # Build message
    header = (
        f"工具呼叫: {analysis['total_calls']} | "
        f"API: {analysis['api_calls']} | "
        f"快取讀取: {analysis['cache_reads']} | "
        f"錯誤: {analysis['error_count']} | "
        f"攔截: {analysis['blocked_count']}"
    )

    title_map = {
        "critical": "Harness 嚴重警告",
        "warning": "Harness 警告",
    }
    title = title_map.get(severity, "Harness 報告")

    message = header + "\n\n" + "\n".join(issues)
    return severity, title, message


def send_ntfy_alert(title: str, message: str, severity: str):
    """Send ntfy alert notification."""
    priority = 5 if severity == "critical" else 4
    tags = ["rotating_light", "shield"] if severity == "critical" else ["warning", "shield"]

    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": message,
        "priority": priority,
        "tags": tags,
    }

    payload_file = "hooks_alert_temp.json"
    try:
        with open(payload_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

        subprocess.run(
            [
                "curl", "-s",
                "-H", "Content-Type: application/json; charset=utf-8",
                "-d", f"@{payload_file}",
                "https://ntfy.sh",
            ],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass
    finally:
        if os.path.exists(payload_file):
            os.remove(payload_file)


def write_session_summary(analysis: dict, alert_sent: bool, severity: str):
    """Write session summary to summary log."""
    summary_file = os.path.join("logs", "structured", "session-summary.jsonl")
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)

    summary = {
        "ts": datetime.now().astimezone().isoformat(),
        "total_calls": analysis["total_calls"],
        "api_calls": analysis["api_calls"],
        "cache_reads": analysis["cache_reads"],
        "cache_writes": analysis["cache_writes"],
        "skill_reads": analysis["skill_reads"],
        "sub_agents": analysis["sub_agents"],
        "blocked": analysis["blocked_count"],
        "errors": analysis["error_count"],
        "cache_bypassed": analysis["cache_bypassed"],
        "status": severity,
        "alert_sent": alert_sent,
    }

    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


def main():
    # Read stdin (Stop hook receives session info, but we don't need it)
    try:
        sys.stdin.read()
    except Exception:
        pass

    entries = read_todays_log()
    if not entries:
        sys.exit(0)

    analysis = analyze_entries(entries)
    alert = build_alert_message(analysis)

    if alert:
        severity, title, message = alert
        send_ntfy_alert(title, message, severity)
        write_session_summary(analysis, alert_sent=True, severity=severity)
    else:
        write_session_summary(analysis, alert_sent=False, severity="healthy")

    sys.exit(0)


if __name__ == "__main__":
    main()
