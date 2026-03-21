#!/usr/bin/env python3
"""
tools/config_loader.py — 集中配置載入器

消除硬編碼 endpoint 值，提供單一真相來源。
所有 tools/*.py 應透過此模組取得 Groq Relay / KB API 等 endpoint。

使用方式：
    from tools.config_loader import get_groq_endpoint, get_kb_api_base

設計原則：
    - 零新依賴（使用已有的 pyyaml）
    - 讀取失敗時回傳合理預設值（向後相容）
    - 配置只載入一次（module-level cache）
"""
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LLM_ROUTER_CONFIG_PATH = REPO_ROOT / "config" / "llm-router.yaml"

_config_cache: dict | None = None
_config_cache_lock = threading.RLock()


def _load_llm_router_config() -> dict:
    """載入 llm-router.yaml，失敗時回傳空 dict。執行緒安全。"""
    global _config_cache
    with _config_cache_lock:
        if _config_cache is not None:
            return _config_cache
        try:
            import yaml
            with open(LLM_ROUTER_CONFIG_PATH, encoding="utf-8") as f:
                _config_cache = yaml.safe_load(f) or {}
        except (ImportError, FileNotFoundError):
            _config_cache = {}
        except Exception as e:
            import sys
            print(f"[config_loader] 配置載入警告：{e}", file=sys.stderr)
            _config_cache = {}
        return _config_cache


def get_groq_endpoint() -> str:
    """取得 Groq Relay endpoint（來自 llm-router.yaml providers.groq.endpoint）。"""
    config = _load_llm_router_config()
    return (
        config.get("providers", {})
        .get("groq", {})
        .get("endpoint", "http://localhost:3002/groq/chat")
    )


def get_groq_health_endpoint() -> str:
    """取得 Groq Relay health check endpoint。"""
    config = _load_llm_router_config()
    return (
        config.get("providers", {})
        .get("groq", {})
        .get("health_check", "http://localhost:3002/groq/health")
    )


def get_groq_model() -> str:
    """取得 Groq 預設模型名稱。"""
    config = _load_llm_router_config()
    return (
        config.get("providers", {})
        .get("groq", {})
        .get("model", "llama-3.1-8b-instant")
    )


def get_groq_timeout() -> int:
    """取得 Groq 請求超時秒數。"""
    config = _load_llm_router_config()
    return (
        config.get("providers", {})
        .get("groq", {})
        .get("timeout_s", 20)
    )


def get_kb_api_base() -> str:
    """取得知識庫 API base URL（從 dependencies.yaml 讀取，fallback localhost:3000）。"""
    try:
        import yaml
        dep_path = REPO_ROOT / "config" / "dependencies.yaml"
        with open(dep_path, encoding="utf-8") as f:
            deps = yaml.safe_load(f) or {}
        return (
            deps.get("skills", {})
            .get("knowledge_query", {})
            .get("api", {})
            .get("base_url", "http://localhost:3000")
        )
    except Exception:
        return "http://localhost:3000"


def _load_yaml_file(path: Path) -> dict:
    """載入任意 YAML 檔案，失敗時回傳空 dict。"""
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_budget_config() -> dict:
    """取得 Token 預算配置（來自 budget.yaml）。"""
    return _load_yaml_file(REPO_ROOT / "config" / "budget.yaml")


def get_daily_budget_limits() -> dict:
    """取得每日預算限額（claude_tokens, groq_calls, warn/suspend threshold）。"""
    cfg = get_budget_config()
    defaults = {
        "claude_tokens": 20_000_000,
        "groq_calls": 100,
        "warn_threshold": 0.80,
        "suspend_threshold": 1.20,
    }
    return {**defaults, **cfg.get("daily_budget", {})}


def get_ntfy_config() -> dict:
    """取得 ntfy 通知配置（來自 notification.yaml）。"""
    return _load_yaml_file(REPO_ROOT / "config" / "notification.yaml")


def get_ntfy_topic() -> str:
    """取得 ntfy 預設 topic。"""
    cfg = get_ntfy_config()
    return cfg.get("default_topic", "wangsc2025")


def get_ntfy_service_url() -> str:
    """取得 ntfy 服務 URL。"""
    cfg = get_ntfy_config()
    return cfg.get("service_url", "https://ntfy.sh")


def get_slo_config() -> dict:
    """取得 SLO 配置（來自 slo.yaml）。"""
    return _load_yaml_file(REPO_ROOT / "config" / "slo.yaml")


def get_slo_list() -> list:
    """取得 SLO 定義列表。"""
    cfg = get_slo_config()
    return cfg.get("slos", [])


def get_slo_budget_policy() -> dict:
    """取得 SLO Error Budget 政策。"""
    cfg = get_slo_config()
    defaults = {"postmortem_trigger_pct": 20, "freeze_threshold_pct": 25}
    return {**defaults, **cfg.get("budget_policy", {})}


def reset_cache() -> None:
    """清除配置快取（用於測試）。執行緒安全。"""
    global _config_cache
    with _config_cache_lock:
        _config_cache = None
