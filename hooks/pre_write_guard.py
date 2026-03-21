#!/usr/bin/env python3
"""
PreToolUse:Write/Edit Guard — 檔案寫入機器強制攔截。

攔截規則：
  1. 寫入 nul 檔案 — Windows 上會建立實體檔案
  2. 寫入 scheduler-state.json — 該檔案由 PowerShell 腳本獨佔維護
  3. 寫入敏感檔案（.env, credentials.json 等）
  4. 路徑遍歷／專案外寫入 — 預設僅告警與 ntfy，不阻擋（action: warn_only）

規則來源：config/hook-rules.yaml（不可用時回退至內建預設值）。
攔截事件記錄至 logs/structured/YYYY-MM-DD.jsonl。
"""
import json
import os
import re

from hook_utils import (
    filter_rules_by_preset,
    load_yaml_rules,
    log_blocked_event,
    output_decision,
    read_stdin_json,
    send_ntfy_alert,
    validate_json_schema,
)

# YAML 不可用時的內建預設規則
FALLBACK_WRITE_RULES = [
    {
        "id": "nul-file",
        "check": "basename_equals",
        "value": "nul",
        "case_insensitive": True,
        "reason": "禁止寫入 nul 檔案（Windows 上會建立實體檔案）",
        "guard_tag": "nul-guard",
    },
    {
        "id": "scheduler-state",
        "check": "path_contains",
        "value": "scheduler-state.json",
        "reason": "禁止 Agent 寫入 scheduler-state.json（此檔案由 PowerShell 腳本維護）",
        "guard_tag": "state-guard",
    },
    {
        "id": "sensitive-files",
        "check": "basename_in",
        "values": [".env", ".env.local", "credentials.json", "token.json",
                   "secrets.json", ".htpasswd", "id_rsa", "id_ed25519"],
        "reason_template": "禁止寫入敏感檔案: {matched}",
        "guard_tag": "secret-guard",
    },
    {
        "id": "path-traversal",
        "check": "path_traversal",
        "reason_template": "偵測到專案目錄外寫入（原路徑遍歷防護）: ({resolved})",
        "guard_tag": "traversal-guard",
        "action": "warn_only",
    },
    # 註解：SKILL.md 保護規則已移除，因為會阻擋用戶明確要求的合法修改
    # 改依賴 Git 版本控制作為安全網
    # {
    #     "id": "skill-md-protect",
    #     "check": "basename_equals",
    #     "value": "SKILL.md",
    #     "reason": "SKILL.md 為系統行為定義，不可在執行期間修改",
    #     "guard_tag": "skill-protect",
    # },
]


def load_write_rules():
    """從 YAML 載入寫入規則，失敗時回退至內建預設值。"""
    rules = load_yaml_rules("write_rules", FALLBACK_WRITE_RULES)
    return filter_rules_by_preset(rules, "write_rules")


def _get_reason(rule, **format_kwargs):
    """從規則取得攔截原因，支援 reason 直接值與 reason_template 格式化。"""
    if "reason" in rule:
        return rule["reason"]
    template = rule.get("reason_template", "Blocked by rule: {id}")
    format_kwargs.setdefault("id", rule.get("id", "unknown"))
    return template.format(**format_kwargs)


def _check_basename_equals(rule, basename):
    """檢查 basename 是否完全匹配指定值。"""
    value = rule.get("value", "")
    if rule.get("case_insensitive", False):
        return basename.lower() == value.lower()
    return basename == value


def _check_basename_in(rule, basename, file_path):
    """檢查 basename 是否在指定清單中（同時檢查路徑尾端）。"""
    for v in rule.get("values", []):
        if basename == v or file_path.endswith(v):
            return True, v
    return False, None


# 允許寫入的例外路徑（Claude Code 內部作業需要）
_TRAVERSAL_ALLOWLIST = [
    os.path.normpath(os.path.expanduser("~/.claude")).lower(),  # Claude Code plans/settings
]


def _build_allowlist(rules):
    """從規則的 allowed_paths 欄位補充白名單（外部化到 YAML）。"""
    extra = []
    for rule in rules:
        if rule.get("check") == "path_traversal":
            for p in rule.get("allowed_paths", []):
                extra.append(os.path.normpath(p).lower())
    return _TRAVERSAL_ALLOWLIST + extra


def _check_path_traversal(file_path, project_root, allowlist=None):
    """檢查路徑是否逃逸專案目錄。對所有路徑解析後比對 project_root。"""
    if allowlist is None:
        allowlist = _TRAVERSAL_ALLOWLIST
    try:
        # 使用 realpath 解析 symlink，防止 symlink 指向專案外的目錄繞過邊界檢查
        resolved = os.path.realpath(os.path.normpath(file_path))
        norm_root = os.path.realpath(os.path.normpath(project_root))
        # Windows 路徑大小寫不敏感，用 lower() 比對避免磁碟代號不一致
        resolved_l = resolved.lower()
        root_l = norm_root.lower()
        if resolved_l == root_l or resolved_l.startswith(root_l + os.sep.lower()):
            return False, resolved  # 在專案目錄內，放行
        # 例外允許清單（內建 + YAML 外部化）
        for allowed in allowlist:
            if resolved_l == allowed or resolved_l.startswith(allowed + os.sep.lower()):
                return False, resolved
        return True, resolved
    except (ValueError, OSError):
        return True, file_path


def check_write_path(file_path, rules=None, project_root=None):
    """檢查檔案路徑是否命中寫入攔截規則。

    Args:
        file_path: 目標檔案路徑
        rules: 規則清單（None 時自動載入）
        project_root: 專案根目錄（用於路徑遍歷檢查，預設為 cwd）

    Returns:
        (blocked, reason, guard_tag, traversal_warn) — 未命中時 reason、guard_tag 為 None，
        traversal_warn 為 False。path_traversal 且 action=warn_only 時 blocked=False、
        traversal_warn=True（僅記錄／通知，不阻擋）。
    """
    if rules is None:
        rules = load_write_rules()
    if project_root is None:
        # 從 __file__ 推導專案根目錄，比 os.getcwd() 更可靠
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    basename = os.path.basename(file_path) if file_path else ""
    allowlist = _build_allowlist(rules)

    for rule in rules:
        check_type = rule.get("check", "")
        guard_tag = rule.get("guard_tag", rule.get("id", "unknown"))

        if check_type == "basename_equals":
            if _check_basename_equals(rule, basename):
                return True, _get_reason(rule), guard_tag, False

        elif check_type == "path_contains":
            value = rule.get("value", "")
            if value and value in file_path:
                return True, _get_reason(rule), guard_tag, False

        elif check_type == "basename_in":
            matched, matched_value = _check_basename_in(rule, basename, file_path)
            if matched:
                return True, _get_reason(rule, matched=matched_value), guard_tag, False

        elif check_type == "path_traversal":
            escaped, resolved = _check_path_traversal(file_path, project_root, allowlist)
            if escaped:
                reason = _get_reason(rule, resolved=resolved)
                if rule.get("action") == "warn_only":
                    return False, reason, guard_tag, True
                return True, reason, guard_tag, False

    return False, None, None, False


# ADR-026：results/todoist-auto-*.json 的 schema 驗證
_AUTO_TASK_RESULT_PATTERN = re.compile(r"results[/\\]todoist-auto-[a-z_]+\.json$", re.IGNORECASE)
_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "schemas", "results-auto-task-schema.json"
)
_cached_result_schema: dict | None = None


def _load_result_schema() -> dict:
    global _cached_result_schema
    if _cached_result_schema is None:
        try:
            with open(_SCHEMA_PATH, encoding="utf-8") as f:
                _cached_result_schema = json.load(f)
        except (OSError, json.JSONDecodeError):
            _cached_result_schema = {}
    return _cached_result_schema


def _validate_auto_task_result(file_path: str, content: str, session_id: str, tool_name: str):
    """對 results/todoist-auto-*.json 執行 Schema 驗證；驗證失敗僅記錄 warning，不攔截。"""
    schema = _load_result_schema()
    if not schema:
        return  # schema 不可用，跳過

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return  # 內容非 JSON，交由寫入後再處理

    is_valid, errors = validate_json_schema(data, schema)
    if not is_valid:
        log_blocked_event(
            session_id, tool_name, file_path,
            f"[ADR-026 WARN] results schema 驗證失敗：{'; '.join(errors)}",
            "schema-warn",
            level="warn"
        )


def main():
    data = read_stdin_json()
    if data is None:
        return output_decision("allow")

    tool_name = data.get("tool_name", "Write")
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    session_id = data.get("session_id", "")

    blocked, reason, guard_tag, traversal_warn = check_write_path(file_path)

    if traversal_warn:
        log_blocked_event(
            session_id, tool_name, file_path, reason, guard_tag, level="warn"
        )
        send_ntfy_alert(
            f"[Write Guard] {guard_tag}（已放行）",
            f"路徑: {file_path}\n原因: {reason}\n（僅通知，未阻擋寫入）",
            "warning",
        )
    elif blocked:
        log_blocked_event(session_id, tool_name, file_path, reason, guard_tag)
        send_ntfy_alert(
            f"[Write Guard] {guard_tag}",
            f"路徑: {file_path}\n原因: {reason}",
            "warning",
        )
        return output_decision("block", reason)

    # ADR-026：todoist-auto 結果檔 schema 驗證（warning-only，不攔截）
    if _AUTO_TASK_RESULT_PATTERN.search(file_path):
        content = tool_input.get("content", tool_input.get("new_string", ""))
        if content:
            _validate_auto_task_result(file_path, content, session_id, tool_name)

    return output_decision("allow")


if __name__ == "__main__":
    main()
