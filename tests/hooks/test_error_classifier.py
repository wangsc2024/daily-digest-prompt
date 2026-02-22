#!/usr/bin/env python3
"""Tests for hooks/error_classifier.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'hooks'))

from error_classifier import (
    ErrorCategory, RetryIntent, classify, extract_http_status, get_backoff_config
)


class TestExtractHttpStatus:
    def test_standard_http_response(self):
        assert extract_http_status("HTTP/1.1 200 OK") == 200

    def test_status_429(self):
        assert extract_http_status("HTTP/2 429 Too Many Requests") == 429

    def test_status_500(self):
        assert extract_http_status("HTTP/1.1 500 Internal Server Error") == 500

    def test_json_status_field(self):
        assert extract_http_status('{"status": 403, "error": "forbidden"}') == 403

    def test_redirect_chain_returns_last(self):
        text = "HTTP/1.1 301 Moved\r\nHTTP/1.1 200 OK"
        assert extract_http_status(text) == 200

    def test_no_status(self):
        assert extract_http_status("some regular output") is None

    def test_empty_string(self):
        assert extract_http_status("") is None

    def test_none_input(self):
        assert extract_http_status(None) is None


class TestClassify:
    def test_401_terminal_stop(self):
        cat, intent = classify("HTTP/1.1 401 Unauthorized")
        assert cat == ErrorCategory.TERMINAL
        assert intent == RetryIntent.STOP

    def test_403_terminal_stop(self):
        cat, intent = classify("HTTP/1.1 403 Forbidden")
        assert cat == ErrorCategory.TERMINAL
        assert intent == RetryIntent.STOP

    def test_404_not_found_skip(self):
        cat, intent = classify("HTTP/1.1 404 Not Found")
        assert cat == ErrorCategory.NOT_FOUND
        assert intent == RetryIntent.SKIP

    def test_429_transient_retry_later(self):
        cat, intent = classify("HTTP/2 429 Too Many Requests")
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_LATER

    def test_500_transient_retry_always(self):
        cat, intent = classify("HTTP/1.1 500 Internal Server Error")
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_ALWAYS

    def test_502_transient(self):
        cat, intent = classify("HTTP/1.1 502 Bad Gateway")
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_ALWAYS

    def test_503_transient(self):
        cat, intent = classify("HTTP/1.1 503 Service Unavailable")
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_ALWAYS

    def test_timeout_transient(self):
        cat, intent = classify("curl: (28) Connection timed out after 30000 milliseconds")
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_ALWAYS

    def test_connection_refused_transient(self):
        cat, intent = classify("ECONNREFUSED: connection refused")
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_ALWAYS

    def test_unknown_4xx_terminal(self):
        cat, intent = classify("HTTP/1.1 418 I'm a teapot")
        assert cat == ErrorCategory.TERMINAL
        assert intent == RetryIntent.STOP

    def test_unknown_5xx_transient(self):
        cat, intent = classify("HTTP/1.1 504 Gateway Timeout")
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_ALWAYS

    def test_exit_code_137_oom(self):
        cat, intent = classify("", exit_code=137)
        assert cat == ErrorCategory.TRANSIENT
        assert intent == RetryIntent.RETRY_ALWAYS

    def test_exit_code_1_unknown(self):
        cat, intent = classify("", exit_code=1)
        assert cat == ErrorCategory.UNKNOWN
        assert intent == RetryIntent.RETRY_ONCE

    def test_unknown_error(self):
        cat, intent = classify("something went wrong", exit_code=0)
        assert cat == ErrorCategory.UNKNOWN
        assert intent == RetryIntent.RETRY_ONCE


class TestBackoffConfig:
    def test_returns_dict(self):
        config = get_backoff_config()
        assert isinstance(config, dict)
        assert "base_seconds" in config
        assert "max_seconds" in config
        assert "multiplier" in config
