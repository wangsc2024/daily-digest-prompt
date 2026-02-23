#!/usr/bin/env python3
"""
PreToolUse:Bash Guard — Bash 指令機器強制攔截。

攔截規則：
  1. nul 重導向（> nul, 2>nul）— Windows 上會建立實體 nul 檔案
  2. Agent 寫入 scheduler-state.json — 該檔案由 PowerShell 腳本獨佔維護
  3. 刪除根目錄（rm -rf /）
  4. Force push 到 main/master
  5. 讀取敏感環境變數（TOKEN/SECRET/KEY/PASSWORD）
  6. 透過網路傳送敏感變數（含 @file、pipe、wget 等多種方式）
  7. Windows 破壞性刪除（del /s, rmdir /s, Remove-Item -Recurse）

規則來源：config/hook-rules.yaml（不可用時回退至內建預設值）。
攔截事件記錄至 logs/structured/YYYY-MM-DD.jsonl。
"""
import re

from hook_utils import load_yaml_rules, filter_rules_by_preset, log_blocked_event, read_stdin_json, output_decision, get_compiled_regex


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
        # 移除 contains 預檢查，改用精確的寫入操作匹配（排除 ls/cat/grep/python read 等只讀操作）
        "pattern": r"(?<![0-9&])>\s*[^&].*scheduler-state\.json|>>\s*.*scheduler-state\.json|(tee|cp|mv)\s+.*scheduler-state\.json|echo\s+.*>\s*.*scheduler-state\.json",
        "reason": "禁止 Agent 寫入 scheduler-state.json（此檔案由 PowerShell 腳本維護）",
        "guard_tag": "state-guard",
    },
    {
        "id": "destructive-delete",
        "patterns": [
            r"rm\s+-[rR]f\s+/(\s|$)",
            r"rm\s+-[rR]f\s+~",
            r"rm\s+-[rR]f\s+\.(\s|$)",
            r"rm\s+-[rR]f\s+\*",
        ],
        "reason": "禁止破壞性刪除操作（根目錄/家目錄/當前目錄/萬用字元）",
        "guard_tag": "safety-guard",
    },
    {
        "id": "destructive-delete-windows",
        "description": "禁止 Windows 風格的破壞性刪除操作",
        "patterns": [
            r"del\s+/[sS]\s+/[qQ]?\s*[A-Za-z]:\\",
            r"rmdir\s+/[sS]\s+/[qQ]?\s*[A-Za-z]:\\",
            r"Remove-Item\s+.*-Recurse.*[A-Za-z]:\\",
            r"Remove-Item\s+.*[A-Za-z]:\\.*-Recurse",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止 Windows 破壞性刪除操作（del /s, rmdir /s, Remove-Item -Recurse 針對磁碟根目錄）",
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
        "id": "sensitive-env-set",
        "description": "禁止透過 set 指令洩露環境變數",
        "patterns": [
            r"\bset\s*\|\s*grep\s+.*(TOKEN|SECRET|KEY|PASSWORD)",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止透過 set 指令洩露敏感環境變數",
        "guard_tag": "env-guard",
    },
    {
        "id": "exfiltration",
        "pattern": r"curl.*(-d|--data).*\$(TOKEN|SECRET|KEY|PASSWORD)",
        "flags": "IGNORECASE",
        "reason": "禁止透過網路傳送敏感變數",
        "guard_tag": "exfiltration-guard",
    },
    {
        "id": "exfiltration-file",
        "description": "禁止透過 @file 方式外洩敏感檔案",
        "patterns": [
            r"curl\s.*(-d|--data|--data-binary|--data-raw|--data-urlencode)\s+@\s*\.env\b",
            r"curl\s.*(-d|--data|--data-binary|--data-raw|--data-urlencode)\s+@\s*credentials",
            r"curl\s.*(-d|--data|--data-binary|--data-raw|--data-urlencode)\s+@\s*token\.json",
            r"curl\s.*(-d|--data|--data-binary|--data-raw|--data-urlencode)\s+@\s*secrets\.json",
            r"curl\s.*(-d|--data|--data-binary|--data-raw|--data-urlencode)\s+@\s*\.htpasswd",
            r"curl\s.*(-d|--data|--data-binary|--data-raw|--data-urlencode)\s+@\s*id_rsa",
            r"curl\s.*(-d|--data|--data-binary|--data-raw|--data-urlencode)\s+@\s*id_ed25519",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止透過 curl @file 方式外洩敏感檔案（.env, credentials, token, secrets 等）",
        "guard_tag": "exfiltration-guard",
    },
    {
        "id": "exfiltration-pipe",
        "description": "禁止透過 pipe 方式外洩敏感檔案",
        "patterns": [
            r"cat\s+.*\.(env|htpasswd)\s*\|.*curl",
            r"cat\s+.*(credentials|secrets|token)\.json\s*\|.*curl",
            r"cat\s+.*(id_rsa|id_ed25519)\s*\|.*curl",
            r"cat\s+.*\.(env|htpasswd)\s*\|.*(wget|nc\s)",
            r"cat\s+.*(credentials|secrets|token)\.json\s*\|.*(wget|nc\s)",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止透過 pipe 方式將敏感檔案內容傳送到外部網路",
        "guard_tag": "exfiltration-guard",
    },
    {
        "id": "exfiltration-wget",
        "description": "禁止透過 wget 外洩敏感資料",
        "patterns": [
            r"wget\s.*--post-data.*\$(TOKEN|SECRET|KEY|PASSWORD)",
            r"wget\s.*--post-file\s*=?\s*\.env\b",
            r"wget\s.*--post-file\s*=?\s*(credentials|secrets|token)\.json",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止透過 wget 傳送敏感資料",
        "guard_tag": "exfiltration-guard",
    },
    {
        "id": "exfiltration-subshell",
        "description": "禁止透過子 shell ($() / ``) 方式外洩敏感檔案",
        "patterns": [
            r"(curl|wget)\s.*(\$\(|`)cat\s+.*\.(env|htpasswd)",
            r"(curl|wget)\s.*(\$\(|`)cat\s+.*(credentials|secrets|token)\.json",
            r"(curl|wget)\s.*(\$\(|`)cat\s+.*(id_rsa|id_ed25519)",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止透過子 shell ($() / ``) 方式外洩敏感檔案內容",
        "guard_tag": "exfiltration-guard",
    },
    {
        "id": "exfiltration-base64",
        "description": "禁止透過 base64 編碼後外洩敏感檔案",
        "patterns": [
            r"base64\s+\.env\b.*\|\s*(curl|wget)",
            r"base64\s+(credentials|secrets|token)\.json.*\|\s*(curl|wget)",
            r"base64\s+(id_rsa|id_ed25519).*\|\s*(curl|wget)",
            r"base64\s+\.htpasswd.*\|\s*(curl|wget)",
            r"cat\s+.*\.(env|htpasswd)\s*\|.*base64.*\|\s*(curl|wget)",
            r"cat\s+.*(credentials|secrets|token)\.json\s*\|.*base64.*\|\s*(curl|wget)",
            r"cat\s+.*(id_rsa|id_ed25519)\s*\|.*base64.*\|\s*(curl|wget)",
        ],
        "flags": "IGNORECASE",
        "reason": "禁止透過 base64 編碼後將敏感檔案內容傳送到外部網路",
        "guard_tag": "exfiltration-guard",
    },
]


def load_bash_rules():
    """從 YAML 載入 bash 規則，失敗時回退至內建預設值。"""
    rules = load_yaml_rules("bash_rules", FALLBACK_BASH_RULES)
    return filter_rules_by_preset(rules, "bash_rules")


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

        if any(get_compiled_regex(p, re_flags).search(command) for p in patterns):
            reason = rule.get("reason", "Blocked by rule: " + rule.get("id", "unknown"))
            guard_tag = rule.get("guard_tag", rule.get("id", "unknown"))
            return True, reason, guard_tag

    return False, None, None


def main():
    data = read_stdin_json()
    if data is None:
        return output_decision("allow")

    command = data.get("tool_input", {}).get("command", "")
    session_id = data.get("session_id", "")

    blocked, reason, guard_tag = check_bash_command(command)

    if blocked:
        log_blocked_event(session_id, "Bash", command, reason, guard_tag)
        return output_decision("block", reason)

    return output_decision("allow")


if __name__ == "__main__":
    main()
