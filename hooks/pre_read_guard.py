#!/usr/bin/env python3
"""
PreToolUse:Read Guard — 敏感路徑讀取攔截。

攔截規則：
  1. 讀取專案目錄外的敏感系統路徑（.ssh, .gnupg, /etc/shadow 等）
  2. 讀取 .env / credentials / token 檔案
  3. 讀取 Windows 系統憑據路徑

規則來源：config/hook-rules.yaml → read_rules（不可用時回退至內建預設值）。
攔截事件記錄至 logs/structured/YYYY-MM-DD.jsonl。
"""
import os
import re

from hook_utils import load_yaml_rules, filter_rules_by_preset, log_blocked_event, read_stdin_json, output_decision, get_compiled_regex


# YAML 不可用時的內建預設規則
FALLBACK_READ_RULES = [
    {
        "id": "sensitive-path",
        "description": "禁止讀取敏感系統路徑",
        "check": "path_match",
        "patterns": [
            r"\.ssh",
            r"\.gnupg",
            r"credentials(?!\.example|\.sample)",  # 不匹配範例檔案
            # 僅匹配 .env 或 .env.local，明確排除 .env.example / .env.sample / .env.template
            r"\.env(?!\.example|\.sample|\.template)",
            r"\.env\.local",
            r"/etc/shadow",
            r"/etc/passwd",
            r"\.aws/credentials",
            r"\.kube/config",
        ],
        "reason": "禁止讀取敏感系統檔案",
        "guard_tag": "read-guard",
    },
    {
        "id": "sensitive-files",
        "description": "禁止讀取敏感檔案",
        "check": "basename_in",
        "values": [".env", ".env.local", "credentials.json", "token.json",
                   "secrets.json", ".htpasswd", "id_rsa", "id_ed25519"],
        "reason_template": "禁止讀取敏感檔案: {matched}",
        "guard_tag": "secret-read-guard",
    },
    {
        "id": "windows-credentials",
        "description": "禁止讀取 Windows 憑據路徑",
        "check": "path_match",
        "patterns": [
            r"AppData.*Roaming.*Microsoft.*Credentials",
            r"AppData.*Roaming.*Microsoft.*Protect",
            r"Windows.*System32.*config.*SAM",
        ],
        "reason": "禁止讀取 Windows 系統憑據",
        "guard_tag": "win-cred-guard",
    },
]


def load_read_rules():
    """從 YAML 載入讀取規則，失敗時回退至內建預設值。"""
    rules = load_yaml_rules("read_rules", FALLBACK_READ_RULES)
    return filter_rules_by_preset(rules, "read_rules")


def _normalize_windows_path(file_path):
    """將 Git Bash/MSYS 風格路徑 /d/Source/... 轉為 D:\\Source\\...。

    支援雙斜線變體（如 /d//Source/...），使用 /+ 消費一或多個分隔符。
    """
    if not file_path or not file_path.startswith("/"):
        return file_path
    m = re.match(r"^/([a-zA-Z])/+(.*)", file_path)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", os.sep)
        return f"{drive}:{os.sep}{rest}"
    return file_path


def _is_within_project(file_path, project_root):
    """檢查路徑是否在專案目錄內（專案內路徑不攔截 .env 等）。"""
    try:
        # 先轉換 Unix-style drive path (/d/... -> D:\...)，否則 Windows 上會誤判
        normalized_input = _normalize_windows_path(file_path)
        resolved = os.path.abspath(os.path.normpath(normalized_input))
        norm_root = os.path.normpath(project_root)
        return resolved.startswith(norm_root)
    except (ValueError, OSError):
        return False


def check_read_path(file_path, rules=None, project_root=None):
    """檢查讀取路徑是否命中攔截規則。

    Returns:
        (blocked, reason, guard_tag)
    """
    if rules is None:
        rules = load_read_rules()
    if project_root is None:
        project_root = os.getcwd()

    if not file_path:
        return False, None, None

    basename = os.path.basename(file_path)
    # Normalize path for consistent matching
    normalized = file_path.replace("\\", "/")

    for rule in rules:
        check_type = rule.get("check", "")
        guard_tag = rule.get("guard_tag", rule.get("id", "unknown"))

        if check_type == "path_match":
            patterns = rule.get("patterns", [])
            for pattern in patterns:
                if get_compiled_regex(pattern, re.IGNORECASE).search(normalized):
                    # Allow reading these paths if they're within the project
                    if _is_within_project(file_path, project_root):
                        continue
                    reason = rule.get("reason", f"Blocked by rule: {rule.get('id')}")
                    return True, reason, guard_tag

        elif check_type == "basename_in":
            for v in rule.get("values", []):
                if basename == v or normalized.endswith(v):
                    # Only block if outside project directory
                    if not _is_within_project(file_path, project_root):
                        reason_template = rule.get("reason_template",
                                                   rule.get("reason", "Blocked"))
                        reason = reason_template.format(matched=v)
                        return True, reason, guard_tag

    return False, None, None


def main():
    data = read_stdin_json()
    if data is None:
        return output_decision("allow")

    file_path = data.get("tool_input", {}).get("file_path", "")
    session_id = data.get("session_id", "")

    blocked, reason, guard_tag = check_read_path(file_path)

    if blocked:
        log_blocked_event(session_id, "Read", file_path, reason, guard_tag)
        return output_decision("block", reason)

    return output_decision("allow")


if __name__ == "__main__":
    main()
