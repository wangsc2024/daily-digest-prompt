#!/usr/bin/env python3
"""
PreToolUse:Write/Edit Guard - Machine-enforced rules for file writes.

Blocks dangerous write patterns that previously relied on Agent self-discipline:
  Rule 1: Writing to 'nul' file (creates physical file on Windows)
  Rule 2: Writing to scheduler-state.json (PowerShell-only file)
  Rule 3: Writing to sensitive paths (.env, credentials, etc.)
  Rule 4: Path traversal attacks (../ sequences escaping project directory)

Blocked events are logged to logs/structured/YYYY-MM-DD.jsonl
"""
import sys
import json
import os
from datetime import datetime


def log_blocked(session_id: str, tool: str, path: str, reason: str, guard_tag: str):
    """Write blocked event to structured JSONL log."""
    log_dir = os.path.join("logs", "structured")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".jsonl")

    entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "sid": (session_id or "")[:12],
        "tool": tool,
        "event": "blocked",
        "reason": reason,
        "summary": path,
        "tags": ["blocked", guard_tag],
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "Write")
    tool_input = data.get("tool_input", {})
    session_id = data.get("session_id", "")

    # Extract path from Write or Edit tool input
    file_path = tool_input.get("file_path", "")

    # Normalize for comparison
    basename = os.path.basename(file_path) if file_path else ""

    # === Rule 1: Block writing to 'nul' file ===
    if basename.lower() == "nul":
        reason = "禁止寫入 nul 檔案（Windows 上會建立實體檔案）"
        log_blocked(session_id, tool_name, file_path, reason, "nul-guard")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # === Rule 2: Block writing to scheduler-state.json ===
    if "scheduler-state.json" in file_path:
        reason = "禁止 Agent 寫入 scheduler-state.json（此檔案由 PowerShell 腳本維護）"
        log_blocked(session_id, tool_name, file_path, reason, "state-guard")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # === Rule 3: Block writing to sensitive paths ===
    sensitive_patterns = [".env", "credentials.json", "token.json", "secrets.json", ".htpasswd"]
    for pattern in sensitive_patterns:
        if basename == pattern or file_path.endswith(pattern):
            reason = f"禁止寫入敏感檔案: {pattern}"
            log_blocked(session_id, tool_name, file_path, reason, "secret-guard")
            print(json.dumps({"decision": "block", "reason": reason}))
            sys.exit(0)

    # === Rule 4: Block path traversal attacks ===
    # Detect attempts to escape the project directory using ../
    if file_path:
        # Normalize path and check for traversal patterns
        normalized = os.path.normpath(file_path)
        project_root = os.path.normpath(os.getcwd())

        # Check if path contains .. sequences that could escape project
        if ".." in file_path:
            # Resolve to absolute path and verify it's within project
            try:
                resolved = os.path.abspath(normalized)
                if not resolved.startswith(project_root):
                    reason = f"禁止路徑遍歷攻擊: 目標路徑在專案目錄外 ({resolved})"
                    log_blocked(session_id, tool_name, file_path, reason, "traversal-guard")
                    print(json.dumps({"decision": "block", "reason": reason}))
                    sys.exit(0)
            except (ValueError, OSError):
                reason = f"禁止無效路徑: {file_path}"
                log_blocked(session_id, tool_name, file_path, reason, "path-guard")
                print(json.dumps({"decision": "block", "reason": reason}))
                sys.exit(0)

    # All checks passed - allow (output JSON to avoid "not start with {" debug noise)
    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
