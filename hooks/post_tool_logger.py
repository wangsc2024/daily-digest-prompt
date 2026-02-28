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
  - Error classification (via agent_guardian.ErrorClassifier)
  - Token economy tracking (input_len + output_len per call)
  - Behavior pattern collection (Instinct Lite — via behavior_tracker)
"""
import sys
import json
import os
from datetime import datetime

# Import agent_guardian for error classification and loop detection
try:
    from agent_guardian import ErrorClassifier, LoopDetector
    AGENT_GUARDIAN_AVAILABLE = True
    _error_classifier = ErrorClassifier()  # Module-level singleton
except ImportError:
    AGENT_GUARDIAN_AVAILABLE = False
    _error_classifier = None

# Import behavior tracker for Instinct Lite pattern collection
try:
    from behavior_tracker import track as track_behavior
    BEHAVIOR_TRACKER_AVAILABLE = True
except ImportError:
    BEHAVIOR_TRACKER_AVAILABLE = False

# Import shared API source patterns
from hook_utils import API_SOURCE_PATTERNS

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
# This list is the hardcoded fallback; the authoritative list is loaded from
# config/hook-rules.yaml benign_output_patterns at module initialisation.
_BENIGN_PATTERNS_FALLBACK = [
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
    "exit code: 0",         # successful exit (colon-space-0 variant)
    "exit code 0 ",         # successful exit (space-terminated, avoids matching 0xFF)
    "exit code 0\n",        # successful exit (newline-terminated)
    "errors: []",           # empty errors array
    "errors: 0",            # zero errors
    "error_category",       # agent_guardian JSON field name
    "error_classification", # post_tool_logger variable name
    "error-",               # error-xxx tag prefix in own JSONL output
    "benign_patterns",      # variable name in own source code
    '"denied": false',      # JSON boolean field (permission denied: false)
]


def _load_benign_patterns_from_yaml() -> list:
    """從 hook-rules.yaml 載入良性輸出模式，失敗時回退硬編碼清單。"""
    try:
        from hook_utils import find_config_path
        config_path = find_config_path()
        if config_path:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            patterns = config.get("benign_output_patterns")
            if isinstance(patterns, list) and patterns:
                return [str(p).lower() for p in patterns]
    except Exception:
        pass
    return _BENIGN_PATTERNS_FALLBACK


# Module-level: load from YAML (falls back to hardcoded list on any error)
BENIGN_PATTERNS = _load_benign_patterns_from_yaml()


def detect_api_sources(text: str) -> list:
    """Detect which API sources are referenced in a command/path."""
    sources = []
    lower = text.lower()
    for source, patterns in API_SOURCE_PATTERNS.items():
        if any(p in lower for p in patterns):
            sources.append(source)
    return sources


def _cmd_has_word(command: str, word: str) -> bool:
    """Check if command contains word at a word boundary (start or after space/|/;/&)."""
    return command.startswith(word) or (" " + word) in command or ("|" + word) in command or (";" + word) in command


def classify_bash(command: str) -> tuple:
    """Classify a Bash command and return (summary, tags)."""
    tags = []
    summary = command[:200]

    if _cmd_has_word(command, "curl"):
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
    if _cmd_has_word(command, "rm "):
        tags.append("file-delete")
    if _cmd_has_word(command, "git "):
        tags.append("git")
        if "git push" in command:
            tags.append("git-push")
        if "git commit" in command:
            tags.append("git-commit")
    if "claude -p" in command:
        tags.append("sub-agent")
    if _cmd_has_word(command, "python") or _cmd_has_word(command, "pytest"):
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


def _find_token_usage_file() -> str:
    """找 token-usage.json 的路徑"""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "token-usage.json"),
        "state/token-usage.json",
    ]
    for c in candidates:
        parent = os.path.dirname(c)
        if parent and os.path.exists(parent):
            return c
    return candidates[0]


def _update_token_usage(input_len: int, output_len: int, tool_name: str) -> None:
    """累積 Token 估算統計（input_len/3.5 + output_len/3.5 ≈ tokens）。

    使用 .lock 檔案保護 read-modify-write 序列，防止團隊並行模式
    （5 路 Phase 1）下多個進程同時更新導致計數遺失。
    """
    try:
        token_file = _find_token_usage_file()
        lock_path = token_file + ".lock"
        lock_fd = None
        try:
            # 取得檔案鎖（跨平台，與 CircuitBreaker._atomic_update 相同模式）
            lock_fd = open(lock_path, "w")
            try:
                import msvcrt
                msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            except (ImportError, OSError):
                try:
                    import fcntl
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (ImportError, OSError):
                    pass  # 無鎖可用時退化為無鎖模式

            today = datetime.now().strftime("%Y-%m-%d")

            # 持鎖後重新讀取（確保讀到最新狀態）
            if os.path.exists(token_file):
                try:
                    with open(token_file, "r", encoding="utf-8") as f:
                        usage = json.load(f)
                except Exception:
                    usage = {"daily": {}, "updated": ""}
            else:
                usage = {"daily": {}, "updated": ""}

            # 確保今日條目
            if today not in usage.get("daily", {}):
                usage.setdefault("daily", {})[today] = {
                    "estimated_tokens": 0, "tool_calls": 0,
                    "input_chars": 0, "output_chars": 0
                }

            # 估算 token（字元 ÷ 3.5，中英混合取中間值）
            estimated = (input_len + output_len) / 3.5

            day_data = usage["daily"][today]
            day_data["estimated_tokens"] = day_data.get("estimated_tokens", 0) + estimated
            day_data["tool_calls"] = day_data.get("tool_calls", 0) + 1
            day_data["input_chars"] = day_data.get("input_chars", 0) + input_len
            day_data["output_chars"] = day_data.get("output_chars", 0) + output_len

            usage["updated"] = datetime.now().isoformat()

            # 只保留 7 天
            import datetime as _dt
            cutoff = (_dt.datetime.now() - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
            usage["daily"] = {k: v for k, v in usage["daily"].items() if k >= cutoff}

            # 原子寫入（持鎖期間完成，確保無競態）
            try:
                from hook_utils import atomic_write_json
                atomic_write_json(token_file, usage)
            except ImportError:
                with open(token_file, "w", encoding="utf-8") as f:
                    json.dump(usage, f, ensure_ascii=False)
        finally:
            if lock_fd:
                lock_fd.close()
                try:
                    os.remove(lock_path)
                except OSError:
                    pass
    except Exception:
        pass  # token 統計失敗不影響主流程


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

    # Error classification (for Bash + API calls)
    error_classification = None
    if AGENT_GUARDIAN_AVAILABLE and tool_name == "Bash":
        command = tool_input.get("command", "")
        exit_code = 1 if has_error else 0  # 簡化判定，實際 exit code 未傳入
        error_classification = _error_classifier.classify(tool_name, command, tool_output, exit_code)

        # 加入分類標籤
        if error_classification["category"] != "success":
            tags.append(f"error-{error_classification['category']}")
        if error_classification["api_source"]:
            # api_source 已在前面 classify_bash 加入，這裡確保一致
            pass

    # Loop Detection（session 狀態持久化於 state/loop-state-{sid}.json）
    loop_detection = None
    if AGENT_GUARDIAN_AVAILABLE:
        try:
            # 決定 params_summary（依 tool 類型）
            if tool_name == "Bash":
                params_summary = tool_input.get("command", "")[:100]
            else:
                params_summary = tool_input.get("file_path", "") or str(tool_input)[:100]

            output_snippet = tool_output[:500] if tool_output else ""

            # 讀取 session 狀態
            sid_prefix = (session_id or "unknown")[:8]
            loop_state_file = os.path.join("state", f"loop-state-{sid_prefix}.json")
            initial_state = None
            if os.path.exists(loop_state_file):
                try:
                    with open(loop_state_file, "r", encoding="utf-8") as f:
                        initial_state = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

            detector = LoopDetector(warning_mode=True, initial_state=initial_state)
            loop_result = detector.check_loop(tool_name, params_summary, output_snippet)

            # 寫回新狀態
            try:
                os.makedirs("state", exist_ok=True)
                with open(loop_state_file, "w", encoding="utf-8") as f:
                    json.dump(detector.get_state(), f)
            except OSError:
                pass

            if loop_result.get("loop_detected"):
                tags.append("loop-suspected")
                loop_detection = loop_result
        except Exception as e:
            import sys
            print(f"[post_tool_logger] loop detection error: {e}", file=sys.stderr)
            pass  # 不中斷 Agent 流程，但記錄錯誤到 stderr

    # Compute input size for token economy tracking
    input_len = len(json.dumps(tool_input, ensure_ascii=False)) if tool_input else 0

    # Build log entry
    entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "sid": (session_id or "")[:12],
        "trace_id": os.environ.get("DIGEST_TRACE_ID", ""),
        "phase": os.environ.get("AGENT_PHASE", ""),
        "agent": os.environ.get("AGENT_NAME", ""),
        "tool": tool_name,
        "event": "post",
        "summary": summary,
        "input_len": input_len,
        "output_len": len(tool_output),
        "has_error": has_error,
        "tags": tags,
    }

    # Add loop detection details if detected
    if loop_detection:
        entry["loop_type"] = loop_detection.get("loop_type")
        entry["loop_warning_only"] = loop_detection.get("warning_only", True)

    # Add error classification details if available
    if error_classification:
        entry["error_category"] = error_classification["category"]
        entry["retry_intent"] = error_classification["retry_intent"]
        entry["wait_seconds"] = error_classification["wait_seconds"]
        entry["should_alert"] = error_classification["should_alert"]
        if error_classification["api_source"]:
            entry["api_source"] = error_classification["api_source"]

    # Add parent_trace_id for sub-agent calls
    if "sub-agent" in tags and entry["trace_id"]:
        entry["parent_trace_id"] = entry["trace_id"]

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

    # Token usage tracking
    _update_token_usage(
        input_len=entry.get("input_len", 0),
        output_len=entry.get("output_len", 0),
        tool_name=entry.get("tool", ""),
    )

    # Behavior pattern tracking (Instinct Lite)
    if BEHAVIOR_TRACKER_AVAILABLE:
        try:
            track_behavior(
                tool=tool_name,
                summary=summary,
                tags=tags,
                has_error=has_error,
                input_len=input_len,
                output_len=len(tool_output),
            )
        except Exception:
            pass  # Silent fail — behavior tracking is optional

    print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
