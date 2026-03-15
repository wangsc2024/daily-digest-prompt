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
  - critical: blocked >=3 OR errors >=5
  - warning: blocked 1-2 OR errors 1-4
  - info (no alert): everything healthy
"""
import sys
import json
import os
import re
import subprocess
import tempfile
import hashlib
from datetime import datetime, timedelta, date
from collections import Counter

NTFY_TOPIC = "wangsc2025"
NTFY_MAX_BYTES = 4096  # ntfy message size limit


def _get_skill_diff(reserved_bytes: int = 0) -> str:
    """Run git diff on SKILL.md files from repo root; truncated if exceeds ntfy limit."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        common = {"capture_output": True, "text": True, "timeout": 10, "cwd": project_root}
        result = subprocess.run(
            ["git", "diff", "skills/*/SKILL.md"],
            **common,
        )
        diff = result.stdout.strip()
        if not diff:
            result = subprocess.run(
                ["git", "diff", "--cached", "skills/*/SKILL.md"],
                **common,
            )
            diff = result.stdout.strip()
        if not diff:
            return "（工作區無差異：可能已 commit、已還原或未寫入磁碟）"
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
    schema_violations = [e for e in entries if "schema-fail" in e.get("tags", [])]

    # Count blocked reasons
    block_reasons = Counter(e.get("reason", "unknown") for e in blocked)

    # Count error tools
    error_tools = Counter(e.get("tool", "unknown") for e in errors)

    # Extract modified SKILL.md paths (deduplicated, preserve order)
    _seen_paths = {}
    for e in skill_modified:
        summary = e.get("summary", "")
        # Extract file path from summary (format: "path (<N> chars)" or just "path")
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
        "schema_violations": schema_violations,
        "schema_violation_count": len(schema_violations),
        "block_reasons": dict(block_reasons),
        "error_tools": dict(error_tools),
        "tag_counts": dict(tag_counts.most_common(15)),
    }


def build_alert_message(analysis: dict, gmail_expiry: "dict | None" = None) -> tuple:
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

    # Check schema violations (Guardrails output validation)
    if analysis["schema_violation_count"] > 0:
        issues.append(f"Schema 驗證失敗 {analysis['schema_violation_count']} 次（quality-gate.md 3.2）")
        if severity != "critical":
            severity = "warning"

    # Check Gmail OAuth expiry
    if gmail_expiry and gmail_expiry.get("needs_alert"):
        days = gmail_expiry["days_remaining"]
        expire = gmail_expiry["expire_date"]
        if days <= 0:
            issues.append(f"Gmail OAuth 已過期（{expire}）")
        else:
            issues.append(f"Gmail OAuth {days} 天後到期（{expire}）")
        issues.append("重新授權：pwsh -File gmail-reauth.ps1")
        if severity != "critical":
            severity = "warning"

    # Check SKILL.md modifications (informational, not an error)
    if analysis["skill_modified_count"] > 0:
        info_items.append(f"已修改 SKILL.md ({analysis['skill_modified_count']} 個檔案):")
        for path in analysis["skill_modified_paths"]:
            info_items.append(f"  - {path}")
        if not issues:  # Only if no errors/blocks, make this a warning
            severity = "warning"

    # Check Token budget (informational warning if exceeded)
    token_warning = _check_token_budget()
    if token_warning:
        issues.append(f"{token_warning}")
        if severity not in ("critical", "warning"):
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
        "schema_violations": analysis.get("schema_violation_count", 0),
        "status": severity,
        "alert_sent": alert_sent,
    }

    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


def _cleanup_stale_state_files(retention_days=7):
    """清理過期的 loop-state-*.json 和 stop-alert-*.json 檔案。

    這些檔案由 agent_guardian.py（LoopDetector）和 on_stop_alert.py（session 去重）
    產生，無自動清理機制會導致 state/ 目錄無限膨脹。
    """
    state_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
    if not os.path.isdir(state_dir):
        return

    cutoff_ts = (datetime.now() - timedelta(days=retention_days)).timestamp()
    patterns = (r"^loop-state-[0-9a-f]+\.json$", r"^stop-alert-[0-9a-f]+\.json$")
    removed = 0

    for fname in os.listdir(state_dir):
        if not any(re.match(p, fname) for p in patterns):
            continue
        fpath = os.path.join(state_dir, fname)
        try:
            if os.path.getmtime(fpath) < cutoff_ts:
                os.remove(fpath)
                removed += 1
        except OSError:
            pass

    return removed


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
    # 使用 atomic_write_lines 避免團隊模式下多 Agent 並行結束時的競態損壞
    summary_file = os.path.join(log_dir, "session-summary.jsonl")
    if not os.path.exists(summary_file):
        return
    kept = []
    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
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
        from hook_utils import atomic_write_lines
        atomic_write_lines(summary_file, kept)
    except ImportError:
        # hook_utils 不可用時退回直接寫入
        try:
            if kept:
                with open(summary_file, "w", encoding="utf-8") as f:
                    for line in kept:
                        f.write(line + "\n")
        except OSError:
            pass
    except OSError:
        pass


def _update_metrics_daily() -> None:
    """從今日所有 JSONL 記錄計算日指標，更新 context/metrics-daily.json。

    完整重算今日記錄（覆寫模式），保留 14 天滾動窗口。
    使用 file_lock + atomic_write_json 防止並行 session 競態條件。
    由 main() 在 _rotate_logs() 之後呼叫。
    """
    try:
        from hook_utils import file_lock, atomic_write_json, safe_load_json
    except ImportError:
        return  # hook_utils 不可用時靜默跳過

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    metrics_file = os.path.join(project_root, "context", "metrics-daily.json")
    today = datetime.now().strftime("%Y-%m-%d")

    # 讀取今日所有 JSONL（所有 session 合計，非僅本 session）
    log_file = os.path.join(project_root, "logs", "structured", f"{today}.jsonl")
    all_entries = _parse_all_entries(log_file)
    if not all_entries:
        return

    # 計算指標
    all_tags = []
    for e in all_entries:
        all_tags.extend(e.get("tags", []))
    tag_counts = Counter(all_tags)

    api_calls       = tag_counts.get("api-call", 0)
    cache_reads     = tag_counts.get("cache-read", 0)
    cache_writes    = tag_counts.get("cache-write", 0)
    blocked_count   = sum(1 for e in all_entries if e.get("event") == "blocked")
    loop_suspected  = tag_counts.get("loop-suspected", 0)
    error_count     = sum(1 for e in all_entries if e.get("has_error"))
    skill_reads     = tag_counts.get("skill-read", 0)
    total_calls     = len(all_entries)

    # 快取命中率：cache_reads / (cache_reads + api_calls)
    cache_total = cache_reads + api_calls
    cache_hit_ratio = round(cache_reads / cache_total * 100, 1) if cache_total > 0 else 0.0

    # 平均輸入 IO（output_len 目前因 hooks 協定限制始終為 0，僅計 input_len）
    total_input = sum(e.get("input_len", 0) for e in all_entries)
    avg_io = round(total_input / total_calls, 0) if total_calls > 0 else 0

    # 從 session-summary.jsonl 計算今日 session 成功率
    session_success_rate = None
    summary_file = os.path.join(project_root, "logs", "structured", "session-summary.jsonl")
    if os.path.exists(summary_file):
        today_sessions = []
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            if entry.get("ts", "")[:10] == today:
                                today_sessions.append(entry)
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
        if today_sessions:
            healthy = sum(
                1 for s in today_sessions
                if s.get("status") in ("healthy", "info")
            )
            session_success_rate = round(healthy / len(today_sessions) * 100, 1)

    new_record: dict = {
        "date": today,
        "total_tool_calls": total_calls,
        "api_calls": api_calls,
        "cache_reads": cache_reads,
        "cache_writes": cache_writes,
        "cache_hit_ratio": cache_hit_ratio,
        "blocked_count": blocked_count,
        "loop_suspected_count": loop_suspected,
        "error_count": error_count,
        "skill_reads": skill_reads,
        "avg_io_per_call": avg_io,
    }
    if session_success_rate is not None:
        new_record["session_success_rate"] = session_success_rate

    try:
        os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
        with file_lock(metrics_file):
            data = safe_load_json(metrics_file, default={"schema_version": 1, "records": []})
            records: list = data.get("records", [])
            # 覆寫今日記錄（每次 session 結束後完整重算，不增量累積）
            records = [r for r in records if r.get("date") != today]
            records.append(new_record)
            # 保留 14 天滾動窗口
            cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
            records = sorted(
                [r for r in records if r.get("date", "") >= cutoff],
                key=lambda r: r.get("date", ""),
            )
            data["records"] = records
            data["updated"] = datetime.now().isoformat()
            atomic_write_json(metrics_file, data)
    except Exception:
        pass  # 不中斷 Agent 流程


def _compute_error_budget() -> list:
    """讀取 config/slo.yaml + context/metrics-daily.json，計算每個 SLO 的 Error Budget 狀態。

    Returns list of dicts:
        id, name, metric, target, actual, remaining_pct, status
        status: "ok" | "warning" | "critical" | "no_data"
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        return []

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    slo_file = os.path.join(project_root, "config", "slo.yaml")
    metrics_file = os.path.join(project_root, "context", "metrics-daily.json")

    if not os.path.exists(slo_file) or not os.path.exists(metrics_file):
        return []

    try:
        with open(slo_file, "r", encoding="utf-8") as f:
            slo_config = yaml.safe_load(f)
        with open(metrics_file, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)
    except (yaml.YAMLError, json.JSONDecodeError, OSError):
        return []

    slos = slo_config.get("slos", [])
    records = metrics_data.get("records", [])
    if not records:
        return []

    # 取最近 window_days 內的記錄平均值（或最新單日值）
    today_str = datetime.now().strftime("%Y-%m-%d")

    results = []
    for slo in slos:
        slo_id = slo.get("id", "?")
        name = slo.get("name", "?")
        metric = slo.get("metric", "")
        target = slo.get("target", 0)
        direction = slo.get("metric_direction", "higher_is_better")
        warning_thresh = slo.get("warning_threshold", 30)
        critical_thresh = slo.get("critical_threshold", 10)
        window_days = slo.get("window_days", 7)

        # 取窗口內記錄
        cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        window_records = [r for r in records if r.get("date", "") >= cutoff]
        if not window_records:
            results.append({
                "id": slo_id, "name": name, "metric": metric,
                "target": target, "actual": None,
                "remaining_pct": None, "status": "no_data",
            })
            continue

        # 取窗口內平均值（忽略 None）
        values = [r[metric] for r in window_records if metric in r and r[metric] is not None]
        if not values:
            results.append({
                "id": slo_id, "name": name, "metric": metric,
                "target": target, "actual": None,
                "remaining_pct": None, "status": "no_data",
            })
            continue

        actual = round(sum(values) / len(values), 3)

        # Error Budget 計算
        # higher_is_better: remaining = (actual - target) / (1 - target) × 100 [若 target < 1]
        # lower_is_better:  remaining = (target - actual) / target × 100
        if direction == "higher_is_better":
            if target >= 1.0:  # 絕對值目標（如 SLO-006 skill_reads ≥ 3）
                remaining_pct = min(100.0, (actual / target) * 100) if target > 0 else 100.0
            else:  # 比例目標（0~1）
                budget_range = 1.0 - target
                remaining_pct = ((actual - target) / budget_range * 100) if budget_range > 0 else 100.0
        else:  # lower_is_better
            if target == 0:  # 目標是 0（如 loop_suspected）
                remaining_pct = 100.0 if actual == 0 else max(-100.0, (target - actual) / max(actual, 1) * 100)
            else:
                remaining_pct = max(-100.0, (target - actual) / target * 100)

        remaining_pct = round(remaining_pct, 1)

        # 狀態判斷
        if remaining_pct < critical_thresh:
            status = "critical"
        elif remaining_pct < warning_thresh:
            status = "warning"
        else:
            status = "ok"

        results.append({
            "id": slo_id, "name": name, "metric": metric,
            "target": target, "actual": actual,
            "remaining_pct": remaining_pct, "status": status,
        })

    return results


def _check_slow_session(entries: list) -> "dict | None":
    """比較本 session 工具呼叫數與 14 天 P95，偵測 Slow Session。

    Returns dict with slow_detected, session_calls, p95_calls, ratio
    Returns None if insufficient data.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    metrics_file = os.path.join(project_root, "context", "metrics-daily.json")

    if not entries or not os.path.exists(metrics_file):
        return None

    try:
        with open(metrics_file, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    records = metrics_data.get("records", [])
    if len(records) < 3:  # 需要至少 3 天才有意義
        return None

    # 計算歷史 P95（total_tool_calls）
    past_totals = [r.get("total_tool_calls", 0) for r in records if r.get("total_tool_calls", 0) > 0]
    if not past_totals:
        return None

    past_totals.sort()
    p95_idx = int(len(past_totals) * 0.95)
    p95_calls = past_totals[min(p95_idx, len(past_totals) - 1)]

    session_calls = len(entries)
    if p95_calls == 0:
        return None

    ratio = round(session_calls / p95_calls, 2)
    slow_detected = ratio > 1.5

    return {
        "slow_detected": slow_detected,
        "session_calls": session_calls,
        "p95_calls": p95_calls,
        "ratio": ratio,
    }


def check_gmail_token_expiry() -> "dict | None":
    """Check Gmail OAuth refresh token expiry (7-day Testing mode limit).

    Google Cloud OAuth apps in 'Testing' mode issue refresh tokens that
    expire 7 days after issuance, regardless of usage frequency.

    Tracks re-authorization by hashing the refresh token value.
    When the hash changes, a new OAuth flow occurred and the timer resets.

    Returns dict with status info, or None if token file is absent.
    Keys: days_remaining, expire_date, issued_date, needs_alert, expired.
    """
    # 用腳本位置推算專案根目錄，避免 cwd 不同時找不到檔案
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_script_dir)
    TOKEN_PATH = os.path.join(_project_root, "key", "token.json")
    STATE_PATH = os.path.join(_project_root, "state", "gmail-oauth-state.json")
    EXPIRE_DAYS = 7
    WARN_DAYS = 2

    if not os.path.exists(TOKEN_PATH):
        return None

    try:
        with open(TOKEN_PATH, encoding="utf-8") as f:
            token_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # 只取 refresh_token，立即清除其餘敏感欄位，避免 exception path 洩漏
    refresh_token = token_data.pop("refresh_token", "")
    token_data.clear()
    del token_data
    if not refresh_token:
        return None

    rt_hash = hashlib.sha256(refresh_token.encode()).hexdigest()[:12]
    today = date.today()

    # Load existing state
    state = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            state = {}

    def _save_state(s: dict):
        state_dir = os.path.dirname(STATE_PATH)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
        try:
            from hook_utils import atomic_write_json
            atomic_write_json(STATE_PATH, s)
        except ImportError:
            try:
                with open(STATE_PATH, "w", encoding="utf-8") as f:
                    json.dump(s, f, ensure_ascii=False)
            except OSError:
                pass

    stored_hash = state.get("refresh_token_hash", "")
    if rt_hash != stored_hash:
        # New OAuth flow detected — reset issued_date to today
        issued_date = today
        _save_state({"refresh_token_hash": rt_hash, "issued_date": today.isoformat()})
    else:
        try:
            issued_date = datetime.strptime(state.get("issued_date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            # Corrupt state — reset to today
            issued_date = today
            state["issued_date"] = today.isoformat()
            _save_state(state)

    expire_date = issued_date + timedelta(days=EXPIRE_DAYS)
    days_remaining = (expire_date - today).days

    today_str = today.isoformat()
    already_alerted_today = state.get("last_alerted_date", "") == today_str
    return {
        "days_remaining": days_remaining,
        "expire_date": expire_date.isoformat(),
        "issued_date": issued_date.isoformat(),
        "needs_alert": days_remaining <= WARN_DAYS and not already_alerted_today,
        "expired": days_remaining <= 0,
    }


def _find_token_usage_file_for_stop() -> str:
    """找 token-usage.json 的路徑（供 on_stop_alert 使用）。"""
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_script_dir)
    return os.path.join(_project_root, "state", "token-usage.json")


def _get_token_warn_limit() -> int:
    """從 config/budget.yaml 讀取 Harness Token 警告門檻（80% 每日上限）。

    使用 daily_budget.claude_tokens × warn_threshold（預設 0.80）。
    若無法讀取 config，回退為 1.5M。
    """
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(_script_dir)
    budget_path = os.path.join(project_root, "config", "budget.yaml")
    if not os.path.exists(budget_path):
        return 1_500_000
    try:
        import yaml  # noqa: F401

        with open(budget_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        daily = cfg.get("daily_budget") or {}
        limit = int(daily.get("claude_tokens", 12_000_000))
        ratio = float(daily.get("warn_threshold", 0.80))
        return int(limit * ratio)  # 80% 門檻
    except (OSError, TypeError, KeyError, ValueError):
        return 1_500_000


def _check_token_budget() -> "str | None":
    """檢查今日 Token 估算是否超過 80% 每日上限。

    門檻來源：config/budget.yaml 的 daily_budget.claude_tokens × warn_threshold（80%）。
    每日只通知一次（冷卻機制）：在 state/token-budget-state.json 記錄
    last_alerted_date，同一天內只發出第一次警告，避免每個 session
    結束都重複通知。

    Returns:
        警告字串（若超過門檻且今日尚未通知），否則 None。
    """
    try:
        warn_limit = _get_token_warn_limit()
        token_file = _find_token_usage_file_for_stop()
        if not os.path.exists(token_file):
            return None

        with open(token_file, "r", encoding="utf-8") as f:
            usage = json.load(f)

        today = datetime.now().strftime("%Y-%m-%d")
        day_data = usage.get("daily", {}).get(today, {})
        estimated = day_data.get("estimated_tokens", 0)

        if estimated <= warn_limit:
            return None

        # 冷卻機制：今日已通知過則跳過
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        state_path = os.path.join(project_root, "state", "token-budget-state.json")

        state: dict = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except (json.JSONDecodeError, OSError):
                state = {}

        if state.get("last_alerted_date") == today:
            return None  # 今日已通知，冷卻中

        # 更新冷卻狀態
        state["last_alerted_date"] = today
        try:
            from hook_utils import atomic_write_json
            atomic_write_json(state_path, state)
        except ImportError:
            try:
                os.makedirs(os.path.dirname(state_path), exist_ok=True)
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False)
            except OSError:
                pass

        limit_m = warn_limit / 1_000_000
        return f"今日 Token 估算超過 80% 門檻（{limit_m:.1f}M）：{estimated / 1_000_000:.1f}M"
    except Exception:
        return None


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

    # Session 去重：同一 session 在 10 分鐘內不重複發送告警
    if session_id:
        dedup_path = os.path.join("state", f"stop-alert-{session_id[:8]}.json")
        try:
            from datetime import timezone
            dedup_data = json.loads(open(dedup_path, encoding="utf-8").read()) if os.path.exists(dedup_path) else {}
            last_sent = dedup_data.get("last_sent", "")
            if last_sent:
                last_dt = datetime.fromisoformat(last_sent)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                now_dt = datetime.now(tz=timezone.utc)
                # 每個 session 最多發一次告警（無論間隔多長）
                print(json.dumps({"dedup": True, "last_sent": last_sent}))
                sys.exit(0)
        except Exception:
            pass

    if session_id:
        # Session-isolated analysis (preferred): only analyze THIS session's entries
        sid_prefix = session_id[:12]
        entries = read_session_entries(today, sid_prefix)
    else:
        # Fallback: offset-based analysis (for backward compatibility)
        entries, total_count = read_todays_log()
        _write_offset(today, total_count)

    # Check Gmail OAuth expiry (independent of session log entries)
    gmail_expiry = check_gmail_token_expiry()

    if not entries and not (gmail_expiry and gmail_expiry.get("needs_alert")):
        write_session_summary(
            analyze_entries([]), alert_sent=False, severity="healthy",
            session_id=session_id,
        )
        print("{}")
        sys.exit(0)

    analysis = analyze_entries(entries)
    alert = build_alert_message(analysis, gmail_expiry=gmail_expiry)

    if alert:
        severity, title, message = alert
        send_ntfy_alert(title, message, severity)
        # 記錄本次發送時間（用於 session 去重）
        if session_id:
            try:
                dedup_path = os.path.join("state", f"stop-alert-{session_id[:8]}.json")
                from datetime import timezone
                with open(dedup_path, "w", encoding="utf-8") as _f:
                    json.dump({"last_sent": datetime.now(tz=timezone.utc).isoformat(), "sid": session_id[:12]}, _f)
            except Exception:
                pass
        # 寫入每日去重標記（僅在 Gmail 到期告警觸發時）
        if gmail_expiry and gmail_expiry.get("needs_alert"):
            _state_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "state", "gmail-oauth-state.json",
            )
            try:
                with open(_state_path, "r", encoding="utf-8") as _f:
                    _state = json.load(_f)
                _state["last_alerted_date"] = date.today().isoformat()
                try:
                    from hook_utils import atomic_write_json
                    atomic_write_json(_state_path, _state)
                except ImportError:
                    with open(_state_path, "w", encoding="utf-8") as _f:
                        json.dump(_state, _f, ensure_ascii=False)
            except (OSError, json.JSONDecodeError):
                pass
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
    _cleanup_stale_state_files()
    _update_metrics_daily()

    # Level 4-B: Error Budget 計算（寫入後才讀，確保今日資料最新）
    try:
        slo_results = _compute_error_budget()
        critical_slos = [s for s in slo_results if s["status"] == "critical"]
        warning_slos = [s for s in slo_results if s["status"] == "warning"]

        if critical_slos:
            lines = [f"SLO 預算耗盡：{len(critical_slos)} 項"]
            for s in critical_slos[:3]:
                actual_str = f"{s['actual']}" if s["actual"] is not None else "N/A"
                remaining_str = f"{s['remaining_pct']}%" if s["remaining_pct"] is not None else "N/A"
                lines.append(f"  ❌ {s['id']} {s['name']}: 實際={actual_str} 目標={s['target']} 剩餘={remaining_str}")
            send_ntfy_alert(
                f"[SLO] {len(critical_slos)} 項 Error Budget 耗盡",
                "\n".join(lines),
                "critical",
            )
        elif warning_slos and not alert:
            # 僅在無其他告警時才發 SLO warning（避免告警轟炸）
            lines = [f"SLO 預算偏低：{len(warning_slos)} 項"]
            for s in warning_slos[:2]:
                remaining_str = f"{s['remaining_pct']}%" if s["remaining_pct"] is not None else "N/A"
                lines.append(f"  ⚠️ {s['id']} {s['name']}: 剩餘={remaining_str}")
            send_ntfy_alert(
                f"[SLO] {len(warning_slos)} 項 Error Budget 偏低",
                "\n".join(lines),
                "warning",
            )
    except Exception:
        pass  # 不中斷 Agent 流程

    # Level 4-C: Slow Session 偵測
    try:
        slow_info = _check_slow_session(entries if entries else [])
        if slow_info and slow_info.get("slow_detected"):
            send_ntfy_alert(
                "[Slow Session] 工具呼叫數超出 P95 × 1.5",
                (f"本次呼叫數：{slow_info['session_calls']} 次\n"
                 f"歷史 P95：{slow_info['p95_calls']} 次\n"
                 f"比率：{slow_info['ratio']}x（閾值 1.5x）\n"
                 "可能原因：迴圈重試、快取失效、任務複雜度異常"),
                "warning",
            )
    except Exception:
        pass

    print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
