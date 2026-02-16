#!/usr/bin/env python3
"""
PreToolUse:Write/Edit Guard — 檔案寫入機器強制攔截。

攔截規則：
  1. 寫入 nul 檔案 — Windows 上會建立實體檔案
  2. 寫入 scheduler-state.json — 該檔案由 PowerShell 腳本獨佔維護
  3. 寫入敏感檔案（.env, credentials.json 等）
  4. 路徑遍歷攻擊（../ 逃逸專案目錄）

規則來源：config/hook-rules.yaml（不可用時回退至內建預設值）。
攔截事件記錄至 logs/structured/YYYY-MM-DD.jsonl。
"""
import os

from hook_utils import load_yaml_rules, log_blocked_event, read_stdin_json, output_decision


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
        "values": [".env", "credentials.json", "token.json", "secrets.json", ".htpasswd"],
        "reason_template": "禁止寫入敏感檔案: {matched}",
        "guard_tag": "secret-guard",
    },
    {
        "id": "path-traversal",
        "check": "path_traversal",
        "reason_template": "禁止路徑遍歷攻擊: 目標路徑在專案目錄外 ({resolved})",
        "guard_tag": "traversal-guard",
    },
    {
        "id": "skill-md-protect",
        "check": "basename_equals",
        "value": "SKILL.md",
        "reason": "SKILL.md 為系統行為定義，不可在執行期間修改",
        "guard_tag": "skill-protect",
    },
]


def load_write_rules():
    """從 YAML 載入寫入規則，失敗時回退至內建預設值。"""
    return load_yaml_rules("write_rules", FALLBACK_WRITE_RULES)


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


def _check_path_traversal(file_path, project_root):
    """檢查路徑是否逃逸專案目錄。僅在路徑含 .. 時觸發。"""
    if ".." not in file_path:
        return False, None

    try:
        resolved = os.path.abspath(os.path.normpath(file_path))
        norm_root = os.path.normpath(project_root)
        if not resolved.startswith(norm_root):
            return True, resolved
    except (ValueError, OSError):
        return True, file_path

    return False, None


def check_write_path(file_path, rules=None, project_root=None):
    """檢查檔案路徑是否命中寫入攔截規則。

    Args:
        file_path: 目標檔案路徑
        rules: 規則清單（None 時自動載入）
        project_root: 專案根目錄（用於路徑遍歷檢查，預設為 cwd）

    Returns:
        (blocked, reason, guard_tag) — 未命中時 reason 與 guard_tag 為 None。
    """
    if rules is None:
        rules = load_write_rules()
    if project_root is None:
        project_root = os.getcwd()

    basename = os.path.basename(file_path) if file_path else ""

    for rule in rules:
        check_type = rule.get("check", "")
        guard_tag = rule.get("guard_tag", rule.get("id", "unknown"))

        if check_type == "basename_equals":
            if _check_basename_equals(rule, basename):
                return True, _get_reason(rule), guard_tag

        elif check_type == "path_contains":
            value = rule.get("value", "")
            if value and value in file_path:
                return True, _get_reason(rule), guard_tag

        elif check_type == "basename_in":
            matched, matched_value = _check_basename_in(rule, basename, file_path)
            if matched:
                return True, _get_reason(rule, matched=matched_value), guard_tag

        elif check_type == "path_traversal":
            escaped, resolved = _check_path_traversal(file_path, project_root)
            if escaped:
                return True, _get_reason(rule, resolved=resolved), guard_tag

    return False, None, None


def main():
    data = read_stdin_json()
    if data is None:
        output_decision("allow")

    tool_name = data.get("tool_name", "Write")
    file_path = data.get("tool_input", {}).get("file_path", "")
    session_id = data.get("session_id", "")

    blocked, reason, guard_tag = check_write_path(file_path)

    if blocked:
        log_blocked_event(session_id, tool_name, file_path, reason, guard_tag)
        output_decision("block", reason)

    output_decision("allow")


if __name__ == "__main__":
    main()
