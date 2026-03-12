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
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LLM_ROUTER_CONFIG_PATH = REPO_ROOT / "config" / "llm-router.yaml"

_config_cache: dict | None = None


def _load_llm_router_config() -> dict:
    """載入 llm-router.yaml，失敗時回傳空 dict。"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        import yaml
        with open(LLM_ROUTER_CONFIG_PATH, encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    except (ImportError, FileNotFoundError, Exception):
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
    """取得知識庫 API base URL（目前固定 localhost:3000）。"""
    return "http://localhost:3000"


def reset_cache() -> None:
    """清除配置快取（用於測試）。"""
    global _config_cache
    _config_cache = None
