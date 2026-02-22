#!/usr/bin/env python3
"""
Hook 共用工具模組 — 提供 YAML 配置載入與結構化日誌記錄。

所有 PreToolUse guard 共用此模組，避免重複實作。
"""
import json
import os
from datetime import datetime


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


# Priority order for rule sorting (Gemini CLI-inspired tiered policy engine)
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def resolve_active_rules(section_key, fallback_rules):
    """載入規則，依活動 preset 過濾，依優先級排序。

    Gemini CLI 啟發的分層策略引擎：
    - 從環境變數 DIGEST_SECURITY_LEVEL 讀取安全等級（預設 strict）
    - critical 優先級規則永遠不可被停用
    - 依優先級排序：critical > high > medium > low

    Args:
        section_key: YAML 頂層鍵名
        fallback_rules: 預設規則清單
    """
    rules = load_yaml_rules(section_key, fallback_rules)
    preset_name = os.environ.get("DIGEST_SECURITY_LEVEL", "strict")

    # 載入 preset 定義
    config_path = find_config_path()
    disabled_rules = set()
    if config_path:
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            presets = config.get("presets", {})
            preset = presets.get(preset_name, {})
            disabled_rules = set(preset.get("disabled_rules", []))
        except Exception:
            pass

    # 過濾規則（critical 規則永遠不可停用）
    filtered = []
    for rule in rules:
        rule_id = rule.get("id", "")
        priority = rule.get("priority", "high")

        if rule_id in disabled_rules and priority != "critical":
            continue  # 被 preset 停用且非 critical

        filtered.append(rule)

    # 依優先級排序
    filtered.sort(key=lambda r: PRIORITY_ORDER.get(r.get("priority", "high"), 1))

    return filtered


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
    # Distributed tracing support
    trace_id = os.environ.get("DIGEST_TRACE_ID", "")
    if trace_id:
        entry["trace_id"] = trace_id
    phase = os.environ.get("DIGEST_PHASE", "")
    if phase:
        entry["phase"] = phase
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
