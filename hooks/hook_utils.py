#!/usr/bin/env python3
"""
Hook 共用工具模組 — 提供 YAML 配置載入與結構化日誌記錄。

所有 PreToolUse guard 共用此模組，避免重複實作。
"""
import json
import os
from datetime import datetime


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


def load_yaml_rules(section_key, fallback_rules):
    """載入 YAML 配置中指定區段的規則，失敗時回傳 fallback。

    Args:
        section_key: YAML 頂層鍵名（如 "bash_rules"、"write_rules"）
        fallback_rules: YAML 不可用時的預設規則清單
    """
    config_path = find_config_path()
    if config_path is None:
        return fallback_rules

    try:
        import yaml
    except ImportError:
        return fallback_rules

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        rules = config.get(section_key)
        if not isinstance(rules, list) or not rules:
            return fallback_rules
        return rules
    except Exception:
        return fallback_rules


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
    import sys
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def output_decision(decision, reason=None):
    """輸出 Hook 決策 JSON 並結束。"""
    import sys
    result = {"decision": decision}
    if reason:
        result["reason"] = reason
    print(json.dumps(result))
    sys.exit(0)
