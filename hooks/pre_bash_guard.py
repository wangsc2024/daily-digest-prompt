#!/usr/bin/env python3
"""
PreToolUse:Bash Guard - Machine-enforced rules for Bash commands.

Blocks dangerous patterns that previously relied on Agent self-discipline:
  Rule 1: nul redirects (> nul, 2>nul) - creates physical 'nul' file on Windows
  Rule 2: Agent writing to scheduler-state.json (PowerShell-only file)
  Rule 3: Destructive operations (rm -rf /)

Blocked events are logged to logs/structured/YYYY-MM-DD.jsonl
"""
import sys
import json
import os
import re
from datetime import datetime


def log_blocked(session_id: str, command: str, reason: str, guard_tag: str):
    """Write blocked event to structured JSONL log."""
    log_dir = os.path.join("logs", "structured")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".jsonl")

    entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "sid": (session_id or "")[:12],
        "tool": "Bash",
        "event": "blocked",
        "reason": reason,
        "summary": command[:200],
        "tags": ["blocked", guard_tag],
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        # Can't parse input - allow (don't break the agent)
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    session_id = data.get("session_id", "")

    # === Rule 1: Block nul redirects ===
    # Matches: > nul, 2>nul, 2> nul, >>nul, > NUL (any case)
    # These create a physical file named 'nul' on Windows (not /dev/null)
    if re.search(r"(>|2>)\s*nul(\s|$|;|&|\|)", command, re.IGNORECASE):
        reason = "禁止 nul 重導向（會建立 nul 實體檔案）。請改用 > /dev/null 2>&1"
        log_blocked(session_id, command, reason, "nul-guard")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # === Rule 2: Block writing to scheduler-state.json ===
    # This file is maintained by PowerShell scripts only; Agent should only read it.
    if "scheduler-state.json" in command and re.search(
        r"(>|>>|tee\s|cp\s.*scheduler|mv\s.*scheduler|echo\s.*>.*scheduler)",
        command,
    ):
        reason = "禁止 Agent 寫入 scheduler-state.json（此檔案由 PowerShell 腳本維護）"
        log_blocked(session_id, command, reason, "state-guard")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # === Rule 3: Block destructive recursive delete on root ===
    if re.search(r"rm\s+-[rR]f\s+/(\s|$)", command):
        reason = "禁止刪除根目錄"
        log_blocked(session_id, command, reason, "safety-guard")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # === Rule 4: Block force push to main/master ===
    if re.search(
        r"git\s+push\s+.*--force.*\s+(main|master)(\s|$)", command
    ) or re.search(r"git\s+push\s+-f\s+.*\s+(main|master)(\s|$)", command):
        reason = "禁止 force push 到 main/master 分支"
        log_blocked(session_id, command, reason, "git-guard")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # All checks passed - allow (output JSON to avoid "not start with {" debug noise)
    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
