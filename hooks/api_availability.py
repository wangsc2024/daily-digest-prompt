#!/usr/bin/env python3
"""
API Availability Tracker — Circuit Breaker + 跨 Session 健康追蹤。

靈感來源：Gemini CLI 的 modelAvailabilityService.ts
追蹤每個 API 來源的健康狀態，實現 Circuit Breaker 模式：
  - closed: 正常運作
  - open: 連續失敗超過閾值，跳過呼叫改用快取
  - half_open: cooldown 到期後試探性呼叫一次

狀態持久化到 state/api-health.json，跨 session 保留。
"""
import json
import os
from datetime import datetime, timedelta


# 預設 Circuit Breaker 設定
DEFAULT_FAILURE_THRESHOLD = 3      # 連續失敗 N 次後開啟 circuit
DEFAULT_COOLDOWN_MINUTES = 30      # open 狀態持續時間
DEFAULT_HALF_OPEN_MAX_TRIES = 1    # half_open 最多試 N 次

# 支援的 API 來源
API_SOURCES = ["todoist", "pingtung-news", "hackernews", "knowledge", "gmail", "ntfy"]


def _state_file_path():
    """取得 state/api-health.json 路徑。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, "state", "api-health.json")


def _default_source_state():
    """建立預設的來源健康狀態。"""
    return {
        "last_success": None,
        "last_failure": None,
        "consecutive_failures": 0,
        "circuit_state": "closed",
        "cooldown_until": None,
    }


def load_health() -> dict:
    """載入 API 健康狀態，檔案不存在時初始化。"""
    path = _state_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 確保所有來源都有記錄
            for source in API_SOURCES:
                if source not in data:
                    data[source] = _default_source_state()
            return data
        except (json.JSONDecodeError, OSError):
            pass

    # 初始化
    return {source: _default_source_state() for source in API_SOURCES}


def save_health(health: dict):
    """持久化 API 健康狀態。"""
    path = _state_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(health, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def check_circuit(source: str, health: dict = None) -> dict:
    """檢查指定來源的 circuit 狀態。

    Returns:
        dict with keys: should_skip (bool), circuit_state, reason
    """
    if health is None:
        health = load_health()

    state = health.get(source, _default_source_state())
    circuit = state.get("circuit_state", "closed")
    now = datetime.utcnow().isoformat()

    if circuit == "closed":
        return {"should_skip": False, "circuit_state": "closed", "reason": None}

    if circuit == "open":
        cooldown_until = state.get("cooldown_until")
        if cooldown_until and now >= cooldown_until:
            # Cooldown 到期，轉為 half_open
            state["circuit_state"] = "half_open"
            save_health(health)
            return {
                "should_skip": False,
                "circuit_state": "half_open",
                "reason": "cooldown expired, trying once",
            }
        return {
            "should_skip": True,
            "circuit_state": "open",
            "reason": f"circuit open until {cooldown_until}",
        }

    if circuit == "half_open":
        # half_open 允許一次嘗試
        return {
            "should_skip": False,
            "circuit_state": "half_open",
            "reason": "probing",
        }

    return {"should_skip": False, "circuit_state": circuit, "reason": None}


def record_success(source: str, health: dict = None) -> dict:
    """記錄 API 呼叫成功。"""
    if health is None:
        health = load_health()

    if source not in health:
        health[source] = _default_source_state()

    state = health[source]
    state["last_success"] = datetime.utcnow().isoformat()
    state["consecutive_failures"] = 0
    state["circuit_state"] = "closed"
    state["cooldown_until"] = None

    save_health(health)
    return health


def record_failure(source: str, health: dict = None,
                   failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
                   cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES) -> dict:
    """記錄 API 呼叫失敗，必要時開啟 circuit。"""
    if health is None:
        health = load_health()

    if source not in health:
        health[source] = _default_source_state()

    state = health[source]
    state["last_failure"] = datetime.utcnow().isoformat()
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1

    # 判斷是否開啟 circuit
    if state["consecutive_failures"] >= failure_threshold:
        state["circuit_state"] = "open"
        cooldown_end = datetime.utcnow() + timedelta(minutes=cooldown_minutes)
        state["cooldown_until"] = cooldown_end.isoformat()
    elif state.get("circuit_state") == "half_open":
        # half_open 探測失敗，重新開啟
        state["circuit_state"] = "open"
        cooldown_end = datetime.utcnow() + timedelta(minutes=cooldown_minutes)
        state["cooldown_until"] = cooldown_end.isoformat()

    save_health(health)
    return health


def update_from_session_results(session_entries: list):
    """從 session 的 JSONL 條目更新所有 API 來源的健康狀態。

    Args:
        session_entries: 本 session 的 JSONL 日誌條目列表
    """
    health = load_health()

    # 按來源分組 API 呼叫
    source_results = {}  # source -> {"success": int, "error": int}
    for entry in session_entries:
        tags = entry.get("tags", [])
        if "api-call" not in tags:
            continue

        has_error = entry.get("has_error", False)
        error_category = entry.get("error_category", "")

        for source in API_SOURCES:
            if source in tags:
                if source not in source_results:
                    source_results[source] = {"success": 0, "error": 0}
                if has_error or error_category in ("terminal", "transient"):
                    source_results[source]["error"] += 1
                else:
                    source_results[source]["success"] += 1

    # 更新健康狀態
    for source, results in source_results.items():
        if results["success"] > 0 and results["error"] == 0:
            record_success(source, health)
        elif results["error"] > 0:
            record_failure(source, health)

    return health


def get_health_summary(health: dict = None) -> dict:
    """取得所有 API 來源的健康摘要。"""
    if health is None:
        health = load_health()

    summary = {}
    for source in API_SOURCES:
        state = health.get(source, _default_source_state())
        summary[source] = {
            "circuit_state": state.get("circuit_state", "closed"),
            "consecutive_failures": state.get("consecutive_failures", 0),
            "last_success": state.get("last_success"),
        }
    return summary
