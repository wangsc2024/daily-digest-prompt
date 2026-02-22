#!/usr/bin/env python3
"""
Loop Detection Service — 三層迴圈偵測。

靈感來源：Gemini CLI 的 loopDetectionService.ts
偵測 Agent session 中的重複行為，避免浪費 API 配額和 context window：
  - Tier 1: 工具呼叫 hash（相同 tool+input 重複 N 次）
  - Tier 2: 輸出內容重複（近似輸出重複 N 次）
  - Tier 3: 過度呼叫（session 工具呼叫數超標）

閾值從 config/timeouts.yaml 的 loop_detection 區段讀取。
"""
import hashlib
import json
import os


# 預設閾值（config/timeouts.yaml 不可用時使用）
DEFAULT_TOOL_HASH_THRESHOLD = 5
DEFAULT_TOOL_HASH_WINDOW = 20
DEFAULT_CONTENT_THRESHOLD = 3
DEFAULT_CONTENT_WINDOW = 10
DEFAULT_MAX_TURNS = {
    "digest": 80,
    "todoist": 150,
    "research": 100,
    "audit": 120,
    "default": 120,
}


def _load_config():
    """載入 config/timeouts.yaml 的 loop_detection 區段。"""
    try:
        import yaml
    except ImportError:
        return None

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    config_path = os.path.join(project_root, "config", "timeouts.yaml")

    if not os.path.isfile(config_path):
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("loop_detection")
    except Exception:
        return None


def _get_threshold(key, default):
    """取得配置值，失敗回傳預設值。"""
    config = _load_config()
    if config and key in config:
        return config[key]
    return default


def _hash_entry(tool_name: str, tool_input) -> str:
    """計算工具呼叫的 hash（SHA-256 前 16 字元）。"""
    content = json.dumps({"tool": tool_name, "input": tool_input},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def check_tool_call_loop(session_entries: list, new_entry: dict) -> dict | None:
    """Tier 1: 偵測相同 tool+input 的重複呼叫。

    Args:
        session_entries: 同 session 的歷史條目（含 _tool_hash 欄位）
        new_entry: 當前新條目

    Returns:
        偵測結果 dict 或 None（未偵測到迴圈）
    """
    threshold = _get_threshold("tool_hash_threshold", DEFAULT_TOOL_HASH_THRESHOLD)
    window = _get_threshold("tool_hash_window", DEFAULT_TOOL_HASH_WINDOW)

    new_hash = new_entry.get("_tool_hash", "")
    if not new_hash:
        return None

    # 取最近 N 筆條目的 hash
    recent = session_entries[-window:] if len(session_entries) > window else session_entries
    hash_count = sum(1 for e in recent if e.get("_tool_hash") == new_hash)

    if hash_count >= threshold:
        return {
            "type": "tool_hash",
            "repeat_count": hash_count + 1,  # +1 for new_entry
            "threshold": threshold,
            "tool": new_entry.get("tool", "unknown"),
            "hash": new_hash,
        }
    return None


def check_content_repetition(session_entries: list) -> dict | None:
    """Tier 2: 偵測輸出內容重複迴圈。

    Args:
        session_entries: 同 session 的歷史條目（含 summary 欄位）

    Returns:
        偵測結果 dict 或 None
    """
    threshold = _get_threshold("content_threshold", DEFAULT_CONTENT_THRESHOLD)
    window = _get_threshold("content_window", DEFAULT_CONTENT_WINDOW)

    recent = session_entries[-window:] if len(session_entries) > window else session_entries

    if len(recent) < threshold:
        return None

    # 取前 50 字元做 hash 比對
    prefix_hashes = []
    for entry in recent:
        summary = entry.get("summary", "")
        prefix = summary[:50] if summary else ""
        h = hashlib.sha256(prefix.encode("utf-8")).hexdigest()[:12]
        prefix_hashes.append(h)

    # 檢查是否有 hash 出現 >= threshold 次
    from collections import Counter
    counts = Counter(prefix_hashes)
    for h, count in counts.most_common(1):
        if count >= threshold:
            return {
                "type": "content_repetition",
                "repeat_count": count,
                "threshold": threshold,
            }
    return None


def check_excessive_turns(session_entries: list, agent_type: str = "default") -> dict | None:
    """Tier 3: 偵測工具呼叫次數超標。

    Args:
        session_entries: 同 session 的所有條目
        agent_type: Agent 類型（digest/todoist/research/audit）

    Returns:
        偵測結果 dict 或 None
    """
    config = _load_config()
    max_turns_config = DEFAULT_MAX_TURNS.copy()
    if config and "max_turns" in config:
        max_turns_config.update(config["max_turns"])

    max_turns = max_turns_config.get(agent_type, max_turns_config.get("default", 120))
    current = len(session_entries)

    # 80% 時 warning
    if current >= int(max_turns * 0.8):
        level = "block" if current >= max_turns else "warning"
        return {
            "type": "excessive_turns",
            "current_turns": current,
            "max_turns": max_turns,
            "level": level,
            "agent_type": agent_type,
        }
    return None


def run_all_checks(session_entries: list, new_entry: dict,
                   agent_type: str = "default") -> dict | None:
    """執行所有層級的迴圈偵測。

    Returns:
        第一個偵測到的結果，或 None
    """
    # Tier 1: 工具呼叫 hash
    result = check_tool_call_loop(session_entries, new_entry)
    if result:
        return result

    # Tier 2: 內容重複（每 10 次呼叫檢查一次以降低開銷）
    if len(session_entries) % 10 == 0:
        result = check_content_repetition(session_entries)
        if result:
            return result

    # Tier 3: 過度呼叫
    result = check_excessive_turns(session_entries, agent_type)
    if result:
        return result

    return None
