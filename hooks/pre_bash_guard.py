#!/usr/bin/env python3
"""
PreToolUse:Bash Guard — Bash 指令機器強制攔截。

攔截規則：
  1. nul 重導向（> nul, 2>nul）— Windows 上會建立實體 nul 檔案
  2. Agent 寫入 scheduler-state.json — 該檔案由 PowerShell 腳本獨佔維護
  3. 刪除根目錄（rm -rf /）
  4. Force push 到 main/master
  5. 讀取敏感環境變數（TOKEN/SECRET/KEY/PASSWORD）
  6. 透過網路傳送敏感變數

規則來源：config/hook-rules.yaml（不可用時回退至內建預設值）。
攔截事件記錄至 logs/structured/YYYY-MM-DD.jsonl。
"""
import re

from hook_utils import load_yaml_rules, log_blocked_event, read_stdin_json, output_decision


# YAML 不可用時的內建預設規則
FALLBACK_BASH_RULES = [
    {
        "id": "nul-redirect",
        "pattern": r"(>|2>)\s*nul(\s|$|;|&|\|)",
        "flags": "IGNORECASE",
        "reason": "禁止 nul 重導向（會建立 nul 實體檔案）。請改用 > /dev/null 2>&1",
        "guard_tag": "nul-guard",
    },
    {
        "id": "scheduler-state-write",
        "contains": "scheduler-state.json",
        "pattern": r"(>|>>|tee\s|cp\s.*scheduler|mv\s.*scheduler|echo\s.*>.*scheduler)",
        "reason": "禁止 Agent 寫入 scheduler-state.json（此檔案由 PowerShell 腳本維護）",
        "guard_tag": "state-guard",
    },
    {
        "id": "destructive-delete",
        "patterns": [
            r"rm\s+-[rR]f\s+/(\s|$)",
            r"rm\s+-[rR]f\s+~",
            r"rm\s+-[rR]f\s+\.(\s|$|/)",
            r"rm\s+-[rR]f\s+\*",
        ],
        "reason": "禁止破壞性刪除操作（根目錄/家目錄/當前目錄/萬用字元）",
        "guard_tag": "safety-guard",
    },
    {
        "id": "force-push",
        "patterns": [
            r"git\s+push\s+.*--force.*\s+(main|master)(\s|$)",
            r"git\s+push\s+-f\s+.*\s+(main|master)(\s|$)",
        ],
        "reason": "禁止 force push 到 main/master 分支",
        "guard_tag": "git-guard",
    },
    {
        "id": "sensitive-env",
        "patterns": [
            r"echo\s+\$[A-Z_]*(TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL)",
            r"printenv\s+.*(TOKEN|SECRET|KEY|PASSWORD)",
            r"env\s*\|\s*grep\s+.*(TOKEN|SECRET|KEY|PASSWORD)",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止讀取敏感環境變數",
        "guard_tag": "env-guard",
    },
    {
        "id": "exfiltration",
        "pattern": r"curl.*(-d|--data).*\$(TOKEN|SECRET|KEY|PASSWORD)",
        "flags": "IGNORECASE",
        "reason": "禁止透過網路傳送敏感變數",
        "guard_tag": "exfiltration-guard",
    },
]


def load_bash_rules():
    """從 YAML 載入 bash 規則，失敗時回退至內建預設值。"""
    return load_yaml_rules("bash_rules", FALLBACK_BASH_RULES)


def _get_patterns(rule):
    """從規則取得 pattern 清單（支援單一 pattern 或多個 patterns）。"""
    patterns = rule.get("patterns", [])
    single = rule.get("pattern")
    if single and not patterns:
        return [single]
    return patterns


def _get_re_flags(rule):
    """從規則取得 regex flags。"""
    return re.IGNORECASE if rule.get("flags") == "IGNORECASE" else 0


def check_bash_command(command, rules=None):
    """檢查 bash 指令是否命中攔截規則。

    Returns:
        (blocked, reason, guard_tag) — 未命中時 reason 與 guard_tag 為 None。
    """
    if rules is None:
        rules = load_bash_rules()

    for rule in rules:
        # 前置條件：指令必須包含指定字串才繼續檢查
        contains = rule.get("contains")
        if contains and contains not in command:
            continue

        re_flags = _get_re_flags(rule)
        patterns = _get_patterns(rule)

        if any(re.search(p, command, re_flags) for p in patterns):
            reason = rule.get("reason", "Blocked by rule: " + rule.get("id", "unknown"))
            guard_tag = rule.get("guard_tag", rule.get("id", "unknown"))
            return True, reason, guard_tag

    return False, None, None


def main():
    data = read_stdin_json()
    if data is None:
        output_decision("allow")

    command = data.get("tool_input", {}).get("command", "")
    session_id = data.get("session_id", "")

    blocked, reason, guard_tag = check_bash_command(command)

    if blocked:
        log_blocked_event(session_id, "Bash", command, reason, guard_tag)
        output_decision("block", reason)

    output_decision("allow")


if __name__ == "__main__":
    main()
