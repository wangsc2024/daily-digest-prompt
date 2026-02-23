#!/usr/bin/env python3
"""
Stop Hook - Session-end health check + auto-alert via ntfy.

When the Agent session ends, this hook:
  1. Reads entries from today's structured log for THIS session only
  2. Analyzes: blocked events, errors
  3. Writes session summary to logs/structured/session-summary.jsonl
  4. If issues detected, sends ntfy alert to wangsc2025
  5. Rotates logs older than 7 days

Session isolation: Filters log entries by session_id to prevent
false positives from concurrent sessions (e.g., team mode where
multiple claude -p processes run in parallel). Falls back to
offset-based analysis if session_id is unavailable.

Alert severity:
  - critical: blocked ≥3 OR errors ≥5
  - warning: blocked 1-2 OR errors 1-4
  - info (no alert): everything healthy
"""
import sys
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta
from collections import Counter

NTFY_TOPIC = "wangsc2025"
NTFY_MAX_BYTES = 4096  # ntfy message size limit


def _get_skill_diff(reserved_bytes: int = 0) -> str:
    """Run git diff on SKILL.md files, truncated only if it exceeds ntfy's 4096-byte limit."""
    try:
        result = subprocess.run(
            ["git", "diff", "skills/*/SKILL.md"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        diff = result.stdout.strip()
        if not diff:
            diff = subprocess.run(
                ["git", "diff", "--cached", "skills/*/SKILL.md"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        if not diff:
            return "（無 unstaged/staged 差異，可能已 commit）"
        max_bytes = NTFY_MAX_BYTES - reserved_bytes
        encoded = diff.encode("utf-8")
        if len(encoded) > max_bytes:
            diff = encoded[: max_bytes - 20].decode("utf-8", errors="ignore") + "\n... (已截斷)"
        return diff
    except Exception as e:
        return f"（git diff 失敗: {e}）"


def _offset_file() -> str:
    """Return path to the offset tracking file for today."""
    return os.path.join("logs", "structured", ".last_analyzed_offset")


def _read_offset() -> tuple:
    """Read last analyzed offset. Returns (date_str, line_count)."""
    path = _offset_file()
    if not os.path.exists(path):
        return ("", 0)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("date", ""), data.get("offset", 0))
    except (json.JSONDecodeError, Exception):
        return ("", 0)


def _write_offset(date_str: str, offset: int):
    """Write the current analyzed offset."""
    path = _offset_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "offset": offset}, f)


def _parse_all_entries(log_file: str) -> list:
    """Parse all entries from a JSONL log file."""
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


def read_session_entries(today: str, sid_prefix: str) -> list:
    """Read entries for a specific session from today's log.

    Filters by session ID prefix (first 12 chars) to isolate
    this session's entries from concurrent sessions.
    """
    log_file = os.path.join("logs", "structured", f"{today}.jsonl")
    all_entries = _parse_all_entries(log_file)
    return [e for e in all_entries if e.get("sid", "").startswith(sid_prefix)]


def read_todays_log() -> tuple:
    """Read only NEW entries from today's structured log (offset-based fallback).

    Returns (new_entries, total_line_count) where new_entries only
    contains lines added since the last analysis.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join("logs", "structured", f"{today}.jsonl")

    if not os.path.exists(log_file):
        return ([], 0)

    # Read all lines
    with open(log_file, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    total_count = len(all_lines)

    # Determine offset: skip lines already analyzed
    prev_date, prev_offset = _read_offset()
    skip = prev_offset if prev_date == today else 0

    # Parse only new lines
    new_entries = []
    for line in all_lines[skip:]:
        line = line.strip()
        if line:
            try:
                new_entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    return (new_entries, total_count)


def analyze_entries(entries: list) -> dict:
    """Analyze log entries and return analysis results."""
    blocked = [e for e in entries if e.get("event") == "blocked"]
    errors = [e for e in entries if e.get("has_error")]
    api_calls = [e for e in entries if "api-call" in e.get("tags", [])]
    cache_reads = [e for e in entries if "cache-read" in e.get("tags", [])]
    cache_writes = [e for e in entries if "cache-write" in e.get("tags", [])]
    skill_reads = [e for e in entries if "skill-read" in e.get("tags", [])]
    skill_modified = [e for e in entries if "skill-modified" in e.get("tags", [])]
    sub_agents = [e for e in entries if "sub-agent" in e.get("tags", [])]

    # Count blocked reasons
    block_reasons = Counter(e.get("reason", "unknown") for e in blocked)

    # Count error tools
    error_tools = Counter(e.get("tool", "unknown") for e in errors)

    # Extract modified SKILL.md paths (deduplicated, preserve order)
    _seen_paths = {}
    for e in skill_modified:
        summary = e.get("summary", "")
        # Extract file path from summary (format: "path (XXX chars)" or just "path")
        path_match = re.search(r"^(.*?)(?:\s+\(|$)", summary)
        if path_match:
            _seen_paths[path_match.group(1)] = True
    skill_modified_paths = list(_seen_paths.keys())

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
        "skill_modified": skill_modified,
        "skill_modified_count": len(skill_modified_paths),
        "skill_modified_paths": skill_modified_paths,
        "sub_agents": len(sub_agents),
        "block_reasons": dict(block_reasons),
        "error_tools": dict(error_tools),
        "tag_counts": dict(tag_counts.most_common(15)),
    }


def build_alert_message(analysis: dict) -> tuple:
    """Build alert message. Returns (severity, title, message) or None if healthy."""
    issues = []
    info_items = []  # Non-critical informational items
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

    # Check SKILL.md modifications (informational, not an error)
    if analysis["skill_modified_count"] > 0:
        info_items.append(f"⚠️ 已修改 SKILL.md ({analysis['skill_modified_count']} 個檔案):")
        for path in analysis["skill_modified_paths"]:
            info_items.append(f"  - {path}")
        if not issues:  # Only if no errors/blocks, make this a warning
            severity = "warning"

    # If only SKILL.md modifications (no errors/blocks), send as info notification
    if not issues and info_items:
        # Build message for info-level SKILL.md notification
        header = (
            f"工具呼叫: {analysis['total_calls']} | "
            f"API: {analysis['api_calls']} | "
            f"快取讀取: {analysis['cache_reads']}"
        )
        title = "SKILL.md 修改通知"
        body = header + "\n\n" + "\n".join(info_items) + "\n\n[git diff skills/*/SKILL.md]\n"
        reserved = len(body.encode("utf-8"))
        message = body + _get_skill_diff(reserved_bytes=reserved)
        return "info", title, message

    if not issues:
        return None

    # Build message for warning/critical alerts
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

    all_items = issues + ([""] + info_items if info_items else [])
    message = header + "\n\n" + "\n".join(all_items)
    if info_items:
        diff_prefix = "\n\n[git diff skills/*/SKILL.md]\n"
        reserved = len((message + diff_prefix).encode("utf-8"))
        message += diff_prefix + _get_skill_diff(reserved_bytes=reserved)
    return severity, title, message


def send_ntfy_alert(title: str, message: str, severity: str):
    """Send ntfy alert notification.

    Security: Uses tempfile.NamedTemporaryFile to avoid race conditions
    and ensure cleanup even on exceptions.
    """
    priority_map = {"critical": 5, "warning": 4, "info": 3}
    priority = priority_map.get(severity, 3)

    tags_map = {
        "critical": ["rotating_light", "shield"],
        "warning": ["warning", "shield"],
        "info": ["information_source", "pencil2"],  # SKILL.md 修改通知
    }
    tags = tags_map.get(severity, ["information_source"])

    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": message,
        "priority": priority,
        "tags": tags,
    }

    # Use tempfile for secure temporary file handling
    # delete=False required for Windows (can't read while open)
    fd = None
    try:
        fd = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            prefix='ntfy_alert_',
            encoding='utf-8',
            delete=False
        )
        json.dump(payload, fd, ensure_ascii=False)
        fd.close()  # Close before subprocess reads it (Windows requirement)

        subprocess.run(
            [
                "curl", "-s",
                "-H", "Content-Type: application/json; charset=utf-8",
                "-d", f"@{fd.name}",
                "https://ntfy.sh",
            ],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass
    finally:
        # Ensure cleanup regardless of success/failure
        if fd and os.path.exists(fd.name):
            try:
                os.unlink(fd.name)
            except OSError:
                pass


def write_session_summary(analysis: dict, alert_sent: bool, severity: str,
                          session_id: str = ""):
    """Write session summary to summary log."""
    summary_file = os.path.join("logs", "structured", "session-summary.jsonl")
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)

    summary = {
        "ts": datetime.now().astimezone().isoformat(),
        "sid": session_id[:12] if session_id else "",
        "total_calls": analysis["total_calls"],
        "api_calls": analysis["api_calls"],
        "cache_reads": analysis["cache_reads"],
        "cache_writes": analysis["cache_writes"],
        "skill_reads": analysis["skill_reads"],
        "skill_modified": analysis.get("skill_modified_count", 0),
        "sub_agents": analysis["sub_agents"],
        "blocked": analysis["blocked_count"],
        "errors": analysis["error_count"],
        "status": severity,
        "alert_sent": alert_sent,
    }

    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


def _rotate_logs(retention_days=7):
    """刪除超過保留天數的結構化日誌與過期 session-summary 條目。"""
    log_dir = os.path.join("logs", "structured")
    if not os.path.isdir(log_dir):
        return
    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")

    # Rotate dated JSONL files (YYYY-MM-DD.jsonl)
    for fname in os.listdir(log_dir):
        if re.match(r"\d{4}-\d{2}-\d{2}\.jsonl$", fname):
            if fname[:10] < cutoff:
                try:
                    os.remove(os.path.join(log_dir, fname))
                except OSError:
                    pass

    # Trim session-summary.jsonl: keep only entries within retention window
    summary_file = os.path.join(log_dir, "session-summary.jsonl")
    if not os.path.exists(summary_file):
        return
    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        kept = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get("ts", "")[:10]
                if ts >= cutoff:
                    kept.append(line)
            except json.JSONDecodeError:
                pass
        with open(summary_file, "w", encoding="utf-8") as f:
            for line in kept:
                f.write(line + "\n")
    except OSError:
        pass


def main():
    # Read stdin - Stop hook receives session info as JSON
    session_id = ""
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            input_data = json.loads(raw)
            session_id = input_data.get("session_id", "")
    except (json.JSONDecodeError, Exception):
        pass

    today = datetime.now().strftime("%Y-%m-%d")

    if session_id:
        # Session-isolated analysis (preferred): only analyze THIS session's entries
        sid_prefix = session_id[:12]
        entries = read_session_entries(today, sid_prefix)
    else:
        # Fallback: offset-based analysis (for backward compatibility)
        entries, total_count = read_todays_log()
        _write_offset(today, total_count)

    if not entries:
        write_session_summary(
            analyze_entries([]), alert_sent=False, severity="healthy",
            session_id=session_id,
        )
        print("{}")
        sys.exit(0)

    analysis = analyze_entries(entries)
    alert = build_alert_message(analysis)

    if alert:
        severity, title, message = alert
        send_ntfy_alert(title, message, severity)
        write_session_summary(
            analysis, alert_sent=True, severity=severity,
            session_id=session_id,
        )
    else:
        write_session_summary(
            analysis, alert_sent=False, severity="healthy",
            session_id=session_id,
        )

    _rotate_logs()
    print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
