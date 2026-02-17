#!/usr/bin/env python3
"""
PostToolUse Logger - Structured JSONL logging for all tool calls.

Writes machine-parseable log entries to logs/structured/YYYY-MM-DD.jsonl
with automatic tagging for:
  - API calls (source detection: todoist, pingtung, hackernews, knowledge, ntfy, gmail)
  - Cache operations (read/write)
  - Skill reads (SKILL.md access)
  - Skill modifications (SKILL.md Write/Edit) — tagged with 'skill-modified'
  - Memory operations (digest-memory, auto-tasks-today)
  - Sub-agent spawning
  - Errors detected in output
"""
import sys
import json
import os
from datetime import datetime


# Source detection patterns for API calls
API_SOURCE_PATTERNS = {
    "todoist": ["todoist.com", "todoist"],
    "pingtung-news": ["ptnews-mcp", "pingtung"],
    "hackernews": ["hacker-news.firebaseio", "hn.algolia"],
    "knowledge": ["localhost:3000"],
    "ntfy": ["ntfy.sh"],
    "gmail": ["gmail.googleapis"],
}

# Error keywords in tool output
ERROR_KEYWORDS = [
    "error",
    "failed",
    "timeout",
    "refused",
    "denied",
    "exception",
    "traceback",
    "404",
    "500",
    "502",
    "503",
]

# Only detect errors for tools that produce execution output (not file content)
ERROR_DETECT_TOOLS = {"Bash", "Write", "Edit"}

# Benign patterns that contain error keywords but aren't actual errors
BENIGN_PATTERNS = [
    "erroraction", "error_msg", "errormsg", "silentlycontinue",
    "error_keywords",       # variable name in own source code
    "has_error",            # JSON field name
    "error_count",          # JSON field name
    "error-handling",       # documentation
    "on_error", "onerror",  # callback/event names
    "stderr",               # stream name
    "no error", "0 error",  # no-error context
    "0 failed",             # success context (e.g., "imported 5, 0 failed")
    "error_tools",          # JSON field name in analysis
    "error_detect",         # variable/config name
    "failed_count",         # JSON field name
    "exit code 0",          # successful exit
    "errors: []",           # empty errors array
    "errors: 0",            # zero errors
]


def detect_api_sources(text: str) -> list:
    """Detect which API sources are referenced in a command/path."""
    sources = []
    lower = text.lower()
    for source, patterns in API_SOURCE_PATTERNS.items():
        if any(p in lower for p in patterns):
            sources.append(source)
    return sources


def classify_bash(command: str) -> tuple:
    """Classify a Bash command and return (summary, tags)."""
    tags = []
    summary = command[:200]

    if "curl" in command:
        tags.append("api-call")
        tags.extend(detect_api_sources(command))
        # Distinguish read vs write API calls
        # curl -d / --data implies POST even without -X POST
        if any(m in command for m in ["-X POST", "-X PUT", "-X DELETE", "-X PATCH",
                                       " -d ", " -d@", " --data", " --data-binary",
                                       " --data-raw"]):
            tags.append("api-write")
        else:
            tags.append("api-read")
    if "rm " in command:
        tags.append("file-delete")
    if "git " in command:
        tags.append("git")
        if "git push" in command:
            tags.append("git-push")
        if "git commit" in command:
            tags.append("git-commit")
    if "claude -p" in command:
        tags.append("sub-agent")
    if "python" in command or "pytest" in command:
        tags.append("python")

    return summary, tags


def classify_write(tool_input: dict) -> tuple:
    """Classify a Write tool call and return (summary, tags)."""
    path = tool_input.get("file_path", "")
    content_len = len(tool_input.get("content", ""))
    tags = []
    summary = f"{path} ({content_len} chars)"

    if "cache/" in path or "cache\\" in path:
        tags.append("cache-write")
        tags.extend(detect_api_sources(path))
    if "digest-memory" in path:
        tags.append("memory-write")
    if "auto-tasks-today" in path:
        tags.append("frequency-write")
    if "ntfy" in os.path.basename(path).lower():
        tags.append("ntfy-payload")
    if "import_note" in path:
        tags.append("kb-import-payload")
    if "task_prompt" in path:
        tags.append("sub-agent-prompt")
    if "todoist-history" in path:
        tags.append("history-write")
    if "SKILL.md" in path or path.endswith("SKILL.md"):
        tags.append("skill-modified")  # 高優先級事件

    return summary, tags


def classify_read(tool_input: dict) -> tuple:
    """Classify a Read tool call and return (summary, tags)."""
    path = tool_input.get("file_path", "")
    tags = []
    summary = path

    if "cache/" in path or "cache\\" in path:
        tags.append("cache-read")
        tags.extend(detect_api_sources(path))
    if "SKILL.md" in path:
        tags.append("skill-read")
    if "SKILL_INDEX" in path:
        tags.append("skill-index")
    if "digest-memory" in path:
        tags.append("memory-read")
    if "scheduler-state" in path:
        tags.append("state-read")
    if "auto-tasks-today" in path:
        tags.append("frequency-read")
    if "todoist-history" in path:
        tags.append("history-read")

    return summary, tags


def classify_edit(tool_input: dict) -> tuple:
    """Classify an Edit tool call and return (summary, tags)."""
    path = tool_input.get("file_path", "")
    tags = ["file-edit"]
    summary = path

    if path.endswith(".ps1"):
        tags.append("powershell-edit")
    if path.endswith(".md"):
        tags.append("markdown-edit")
    if path.endswith(".json"):
        tags.append("json-edit")
    if "SKILL.md" in path or path.endswith("SKILL.md"):
        tags.append("skill-modified")  # 高優先級事件

    return summary, tags


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        print("{}")
        sys.exit(0)

    tool_name = data.get("tool_name", "unknown")
    tool_input = data.get("tool_input", {})
    tool_output = str(data.get("tool_output", ""))
    session_id = data.get("session_id", "")

    # Classify tool call
    if tool_name == "Bash":
        summary, tags = classify_bash(tool_input.get("command", ""))
    elif tool_name == "Write":
        summary, tags = classify_write(tool_input)
    elif tool_name == "Read":
        summary, tags = classify_read(tool_input)
    elif tool_name == "Edit":
        summary, tags = classify_edit(tool_input)
    else:
        summary = str(tool_input)[:200]
        tags = [tool_name.lower()]

    # Detect errors in output (only for execution tools, not file-content tools)
    has_error = False
    if tool_name in ERROR_DETECT_TOOLS and tool_output:
        lower_output = tool_output[:2000].lower()
        if any(kw in lower_output for kw in ERROR_KEYWORDS):
            if not any(benign in lower_output for benign in BENIGN_PATTERNS):
                has_error = True
                tags.append("error")

    # Team mode tagging (Phase 2.3: structured logging enhancement)
    if os.environ.get("CLAUDE_TEAM_MODE") == "1":
        tags.append("team-mode")

        # Phase tagging (based on prompt filename patterns in summary)
        summary_lower = summary.lower()
        if "fetch-" in summary_lower:
            tags.append("phase1")
        elif "assemble" in summary_lower or "todoist-assemble" in summary_lower:
            tags.append("phase2")
        elif "todoist-query" in summary_lower:
            tags.append("phase1-query")

    # Build log entry
    entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "sid": (session_id or "")[:12],
        "tool": tool_name,
        "event": "post",
        "summary": summary,
        "output_len": len(tool_output),
        "has_error": has_error,
        "tags": tags,
    }

    # Write to JSONL (with disk protection)
    log_dir = os.path.join("logs", "structured")
    log_file = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".jsonl")

    try:
        os.makedirs(log_dir, exist_ok=True)

        # Emergency rotation: if log file exceeds 50MB, rename and start fresh
        if os.path.exists(log_file):
            log_size = os.path.getsize(log_file)
            if log_size > 50 * 1024 * 1024:  # 50MB
                rotated = log_file + ".rotated"
                # Keep only the latest rotated copy to avoid unbounded growth
                if os.path.exists(rotated):
                    os.remove(rotated)
                os.rename(log_file, rotated)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Silent fail — do not disrupt Agent workflow

    print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
