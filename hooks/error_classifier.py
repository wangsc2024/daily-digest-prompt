#!/usr/bin/env python3
"""
Error Classifier — 4 類錯誤分類引擎。

靈感來源：Gemini CLI 的 errorClassification.ts
將工具輸出中的錯誤分為 4 類，並指派重試意圖：
  - TERMINAL: 401/403 → 停止（認證失敗、權限不足）
  - TRANSIENT: 429/500/502/503/timeout → 重試（暫時性故障）
  - NOT_FOUND: 404 → 跳過（資源不存在）
  - UNKNOWN: 未知 → 重試一次

錯誤模式定義在 config/error-patterns.yaml，不可用時回退至內建預設值。
"""
import os
import re
from enum import Enum


class ErrorCategory(Enum):
    TERMINAL = "terminal"
    TRANSIENT = "transient"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


class RetryIntent(Enum):
    STOP = "stop"
    RETRY_ALWAYS = "retry_always"
    RETRY_ONCE = "retry_once"
    RETRY_LATER = "retry_later"
    SKIP = "skip"


# 內建預設值（config/error-patterns.yaml 不可用時使用）
FALLBACK_HTTP_STATUS_MAP = {
    401: {"category": "terminal", "intent": "stop"},
    403: {"category": "terminal", "intent": "stop"},
    404: {"category": "not_found", "intent": "skip"},
    429: {"category": "transient", "intent": "retry_later"},
    500: {"category": "transient", "intent": "retry_always"},
    502: {"category": "transient", "intent": "retry_always"},
    503: {"category": "transient", "intent": "retry_always"},
}

FALLBACK_CLI_EXIT_CODES = {
    1: {"category": "unknown", "intent": "retry_once"},
    137: {"category": "transient", "intent": "retry_always"},  # OOM killed
    143: {"category": "transient", "intent": "retry_always"},  # SIGTERM
}

FALLBACK_BACKOFF = {
    "base_seconds": 30,
    "max_seconds": 300,
    "multiplier": 2,
    "jitter_max": 15,
}

# HTTP 狀態碼提取正則
HTTP_STATUS_PATTERN = re.compile(r"HTTP/[\d.]+\s+(\d{3})")
# curl 錯誤碼提取
CURL_ERROR_PATTERN = re.compile(r"curl:\s*\((\d+)\)")
# 逾時關鍵字
TIMEOUT_PATTERNS = [
    re.compile(r"timed?\s*out", re.IGNORECASE),
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"ETIMEDOUT", re.IGNORECASE),
    re.compile(r"ECONNREFUSED", re.IGNORECASE),
]
# 連線失敗
CONNECTION_PATTERNS = [
    re.compile(r"connection\s+refused", re.IGNORECASE),
    re.compile(r"ECONNRESET", re.IGNORECASE),
    re.compile(r"ENOTFOUND", re.IGNORECASE),
    re.compile(r"network\s+(?:error|unreachable)", re.IGNORECASE),
]


def _load_config():
    """載入 config/error-patterns.yaml，失敗回傳 None。"""
    try:
        import yaml
    except ImportError:
        return None

    # 從 hooks/ 上層推算 config/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    config_path = os.path.join(project_root, "config", "error-patterns.yaml")

    if not os.path.isfile(config_path):
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _get_http_status_map():
    """取得 HTTP 狀態碼對映表。"""
    config = _load_config()
    if config and "http_status_map" in config:
        return {int(k): v for k, v in config["http_status_map"].items()}
    return FALLBACK_HTTP_STATUS_MAP


def _get_cli_exit_codes():
    """取得 CLI 結束碼對映表。"""
    config = _load_config()
    if config and "cli_exit_codes" in config:
        return {int(k): v for k, v in config["cli_exit_codes"].items()}
    return FALLBACK_CLI_EXIT_CODES


def get_backoff_config():
    """取得退避配置。"""
    config = _load_config()
    if config and "backoff" in config:
        return config["backoff"]
    return FALLBACK_BACKOFF


def extract_http_status(text: str) -> int | None:
    """從工具輸出提取 HTTP 狀態碼。"""
    if not text:
        return None
    # 搜尋最後一個 HTTP 狀態碼（處理重導向情境）
    matches = HTTP_STATUS_PATTERN.findall(text[:5000])
    if matches:
        return int(matches[-1])
    # 備援：搜尋裸狀態碼模式 (e.g., "status": 429)
    bare_match = re.search(r'"status":\s*(\d{3})', text[:5000])
    if bare_match:
        return int(bare_match.group(1))
    return None


def classify(tool_output: str, exit_code: int = 0) -> tuple:
    """分類錯誤並回傳 (ErrorCategory, RetryIntent)。

    Args:
        tool_output: 工具的標準輸出/錯誤
        exit_code: CLI 結束碼（0 = 成功）

    Returns:
        (ErrorCategory, RetryIntent) 元組
    """
    # 1. 嘗試從 HTTP 狀態碼分類
    http_status = extract_http_status(tool_output)
    if http_status:
        status_map = _get_http_status_map()
        if http_status in status_map:
            mapping = status_map[http_status]
            return (
                ErrorCategory(mapping["category"]),
                RetryIntent(mapping["intent"]),
            )
        # 4xx 未列出的視為 terminal
        if 400 <= http_status < 500:
            return ErrorCategory.TERMINAL, RetryIntent.STOP
        # 5xx 未列出的視為 transient
        if 500 <= http_status < 600:
            return ErrorCategory.TRANSIENT, RetryIntent.RETRY_ALWAYS

    # 2. 檢查逾時/連線失敗模式
    if tool_output:
        text_sample = tool_output[:3000]
        for pattern in TIMEOUT_PATTERNS:
            if pattern.search(text_sample):
                return ErrorCategory.TRANSIENT, RetryIntent.RETRY_ALWAYS
        for pattern in CONNECTION_PATTERNS:
            if pattern.search(text_sample):
                return ErrorCategory.TRANSIENT, RetryIntent.RETRY_ALWAYS

    # 3. 嘗試從 CLI 結束碼分類
    if exit_code != 0:
        exit_map = _get_cli_exit_codes()
        if exit_code in exit_map:
            mapping = exit_map[exit_code]
            return (
                ErrorCategory(mapping["category"]),
                RetryIntent(mapping["intent"]),
            )

    # 4. 預設：未知錯誤，重試一次
    return ErrorCategory.UNKNOWN, RetryIntent.RETRY_ONCE


def classify_for_source(tool_output: str, source: str) -> dict:
    """分類錯誤並回傳適合寫入 JSONL 的 dict。

    Args:
        tool_output: 工具輸出
        source: API 來源名稱（todoist, hackernews 等）

    Returns:
        dict with error_category, retry_intent, http_status, source
    """
    category, intent = classify(tool_output)
    http_status = extract_http_status(tool_output)

    return {
        "error_category": category.value,
        "retry_intent": intent.value,
        "http_status": http_status,
        "source": source,
    }
