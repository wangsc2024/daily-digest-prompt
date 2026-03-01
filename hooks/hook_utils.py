#!/usr/bin/env python3
"""
Hook 共用工具模組 — 提供 YAML 配置載入與結構化日誌記錄。

所有 PreToolUse guard 共用此模組，避免重複實作。
"""
import json
import os
import re
import sys
from datetime import datetime


# 模組層級正則編譯快取（避免重複編譯 hot path 中的 pattern）
_compiled_regex_cache: dict = {}

# 模組層級 YAML 配置快取（避免同一進程多次開檔讀取 hook-rules.yaml）
_yaml_config_cache: dict = {"loaded": False, "data": None}


def get_compiled_regex(pattern: str, flags: int = 0):
    """從快取取得已編譯正則，未命中時編譯並快取。"""
    key = (pattern, flags)
    if key not in _compiled_regex_cache:
        _compiled_regex_cache[key] = re.compile(pattern, flags)
    return _compiled_regex_cache[key]


# API 來源偵測 patterns（供 post_tool_logger 和 agent_guardian 共用）
API_SOURCE_PATTERNS = {
    "todoist": ["todoist.com", "todoist"],
    "pingtung-news": ["ptnews-mcp", "pingtung"],
    "hackernews": ["hacker-news.firebaseio", "hn.algolia"],
    "knowledge": ["localhost:3000"],
    "ntfy": ["ntfy.sh"],
    "gmail": ["gmail.googleapis"],
}


# Prompt Injection 偵測 patterns（供 hook 或 Python 腳本引用）
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s*:\s*you\s+are",
    r"<\s*/?\s*system",
    r"ADMIN\s*MODE",
    r"forget\s+(everything|all)",
    r"you\s+are\s+now\s+a",
    r"disregard\s+(all|any)\s+(previous|prior)",
]


def find_config_path(filename="hook-rules.yaml"):
    """從 hooks/ 上層或 cwd 尋找配置檔，找不到回傳 None。"""
    # 優先：以本腳本位置推算 hooks/../config/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    candidate = os.path.join(project_root, "config", filename)
    if os.path.isfile(candidate):
        return candidate

    # 備援：以 cwd 為基準
    candidate = os.path.join("config", filename)
    if os.path.isfile(candidate):
        return candidate

    return None


def clear_yaml_config_cache():
    """清除 YAML 配置快取，下次呼叫將重新載入。"""
    _yaml_config_cache["loaded"] = False
    _yaml_config_cache["data"] = None


def _load_yaml_config():
    """載入 hook-rules.yaml 完整配置（含模組層級快取）。

    單次 YAML 開檔供 load_yaml_rules + filter_rules_by_preset 共用，
    避免同一 hook 呼叫中重複開檔讀取。快取在進程生命週期內有效，
    可透過 clear_yaml_config_cache() 手動清除。
    """
    if _yaml_config_cache["loaded"]:
        return _yaml_config_cache["data"]

    config_path = find_config_path()
    if config_path is None:
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = None
        return None

    try:
        import yaml
    except ImportError:
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = None
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = data
        return data
    except Exception:
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = None
        return None


def load_yaml_rules(section_key, fallback_rules):
    """載入 YAML 配置中指定區段的規則，失敗時回傳 fallback。

    Args:
        section_key: YAML 頂層鍵名（如 "bash_rules"、"write_rules"）
        fallback_rules: YAML 不可用時的預設規則清單
    """
    config = _load_yaml_config()
    if config is None:
        return fallback_rules

    rules = config.get(section_key)
    if not isinstance(rules, list) or not rules:
        return fallback_rules
    return rules


def load_yaml_section(section_key, fallback=None):
    """載入 YAML 配置中指定區段（通用版，不限於規則清單）。

    與 load_yaml_rules 不同，此函數不要求值為 list，
    可用於取得任意型別的配置值（list/dict/str 等）。

    Args:
        section_key: YAML 頂層鍵名（如 "benign_output_patterns"）
        fallback: YAML 不可用或區段不存在時的預設值
    """
    config = _load_yaml_config()
    if config is None:
        return fallback

    value = config.get(section_key)
    if value is None:
        return fallback
    return value


def filter_rules_by_preset(rules, section_key="bash_rules"):
    """根據環境變數 HOOK_SECURITY_PRESET 過濾規則。

    讀取 hook-rules.yaml 的 presets 配置，根據當前 preset 的 enabled_priorities
    過濾規則清單，僅保留符合優先級的規則。

    Args:
        rules: 規則清單（必須含 priority 欄位）
        section_key: 規則區段名稱（用於日誌）

    Returns:
        過濾後的規則清單
    """
    preset_name = os.environ.get("HOOK_SECURITY_PRESET", "normal").lower()

    if preset_name == "normal":
        return rules

    config = _load_yaml_config()
    if config is None:
        return rules

    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        return rules

    preset_config = presets.get(preset_name)
    if not preset_config or not isinstance(preset_config, dict):
        return rules

    enabled_priorities = preset_config.get("enabled_priorities", ["critical", "high", "medium", "low"])

    filtered = [r for r in rules if r.get("priority", "medium") in enabled_priorities]

    if not filtered:
        return rules

    return filtered


def get_rule_patterns(rule):
    """從規則取得 pattern 清單（支援單一 pattern 或多個 patterns）。

    供 pre_bash_guard、pre_read_guard 等 guard 共用，避免重複實作。
    """
    patterns = rule.get("patterns", [])
    single = rule.get("pattern")
    if single and not patterns:
        return [single]
    return patterns


def get_rule_re_flags(rule):
    """從規則取得 regex flags。

    供 pre_bash_guard、pre_read_guard 等 guard 共用，避免重複實作。
    """
    return re.IGNORECASE if rule.get("flags") == "IGNORECASE" else 0


def log_blocked_event(session_id, tool, summary, reason, guard_tag):
    """將攔截事件寫入結構化 JSONL 日誌。"""
    log_dir = os.path.join("logs", "structured")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".jsonl")

    entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "sid": (session_id or "")[:12],
        "tool": tool,
        "event": "blocked",
        "reason": reason,
        "summary": summary[:200],
        "tags": ["blocked", guard_tag],
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_stdin_json():
    """從 stdin 讀取 JSON，解析失敗回傳 None。"""
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def output_decision(decision, reason=None, protocol_version="1.0"):
    """輸出 Hook 決策 JSON 並結束（含協議版本）。

    Args:
        decision: "allow" 或 "block"
        reason: 選填的原因說明
        protocol_version: 協議版本號（預設 "1.0"）
    """
    result = {
        "protocol_version": protocol_version,
        "decision": decision,
        "timestamp": datetime.now().isoformat()
    }
    if reason:
        result["reason"] = reason
    print(json.dumps(result))
    sys.exit(0)


def atomic_write_json(filepath: str, data) -> None:
    """原子寫入 JSON 檔案（write-to-temp + os.replace()）。

    防止多個 Agent 並行寫入同一 JSON 導致資料損壞。
    在 POSIX 和 Windows NTFS 上 os.replace() 均為原子操作。

    注意：此函數保證目標檔案不會處於半寫入狀態，
    但不保護 read-modify-write 序列的互斥性。
    若需要累積計數，請在外層使用 .lock 檔案保護。
    """
    import tempfile
    dirpath = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dirpath, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=dirpath, suffix=".tmp", delete=False
        ) as tf:
            tmp_path = tf.name
            json.dump(data, tf, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
        tmp_path = None  # 成功替換後清除引用，避免 finally 誤刪
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def atomic_write_lines(filepath: str, lines: list) -> None:
    """原子寫入多行文字檔案（write-to-temp + os.replace()）。

    與 atomic_write_json 相同的原子替換策略，但用於 JSONL 等
    逐行格式的檔案。每行自帶換行符或由呼叫者確保。

    Args:
        filepath: 目標檔案路徑
        lines: 字串列表，每個元素寫為一行（自動加換行符）
    """
    import tempfile
    dirpath = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dirpath, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=dirpath, suffix=".tmp", delete=False
        ) as tf:
            tmp_path = tf.name
            for line in lines:
                tf.write(line + "\n")
        os.replace(tmp_path, filepath)
        tmp_path = None
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
