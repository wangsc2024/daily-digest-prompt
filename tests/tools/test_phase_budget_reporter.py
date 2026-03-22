"""
tests/tools/test_phase_budget_reporter.py — ADR-035 per-phase 預算查核 TDD

覆蓋重點：
  - check_phase_budget：未超限 / 超 phase_limit / 超 trace warn / 超 trace suspend
  - token-usage.json 不存在時 graceful fallback
  - format_phase_summary：有/無記錄的輸出格式
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.phase_budget_reporter import (  # noqa: E402
    check_phase_budget,
    format_phase_summary,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token_usage(
    phase: str = "phase1",
    phase_tokens: float = 0.0,
    trace_id: str = "abc123def456",
    trace_tokens: float = 0.0,
    phase_breakdown: dict | None = None,
) -> dict:
    """建立假的 token-usage.json 結構（schema v3）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "schema_version": 3,
        "daily": {
            today: {
                "estimated_tokens": phase_tokens + trace_tokens,
                "tool_calls": 100,
                "input_chars": 1000,
                "output_chars": 5000,
                "phases": {
                    phase: {"estimated_tokens": phase_tokens, "tool_calls": 50},
                },
                "traces": {
                    trace_id[:12]: {
                        "start_time": datetime.now().isoformat(),
                        "total_tokens": trace_tokens,
                        "phase_breakdown": phase_breakdown or {},
                    }
                },
            }
        },
        "updated": datetime.now().isoformat(),
    }


def _make_budget_config(
    phase1_limit: int = 500_000,
    trace_warn: int = 3_000_000,
    trace_suspend: int = 8_000_000,
) -> dict:
    """建立假的 budget.yaml 結構。"""
    return {
        "phase_budget": {
            "phase1": phase1_limit,
            "phase2": 2_000_000,
            "phase3": 200_000,
            "phase2_auto": 800_000,
        },
        "trace_budget": {
            "warn_threshold": trace_warn,
            "suspend_threshold": trace_suspend,
        },
    }


# ── check_phase_budget ────────────────────────────────────────────────────────

class TestCheckPhaseBudget:
    def test_no_usage_file_graceful_fallback(self, tmp_path):
        """token-usage.json 不存在時，回傳全 False 且不 crash。"""
        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", tmp_path / "nonexistent.json"), \
             patch("tools.phase_budget_reporter._load_budget_config", return_value=_make_budget_config()):
            result = check_phase_budget("phase1", "trace123")

        assert result["warn_phase"] is False
        assert result["warn_trace"] is False
        assert result["suspend_trace"] is False
        assert result["phase_tokens"] == 0.0
        assert result["trace_tokens"] == 0.0

    def test_within_limit_returns_no_warn(self, tmp_path):
        """未超限時，warn_phase = False。"""
        usage = _make_token_usage(phase="phase1", phase_tokens=100_000, trace_tokens=500_000)
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config(phase1_limit=500_000)):
            result = check_phase_budget("phase1", "abc123def456")

        assert result["warn_phase"] is False
        assert result["phase_tokens"] == 100_000.0

    def test_phase_tokens_exceed_80pct_triggers_warn_phase(self, tmp_path):
        """phase_tokens ≥ 80% of phase_limit → warn_phase=True。"""
        usage = _make_token_usage(phase="phase1", phase_tokens=420_000)  # 84% of 500k
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config(phase1_limit=500_000)):
            result = check_phase_budget("phase1", "abc123def456")

        assert result["warn_phase"] is True

    def test_trace_tokens_exceed_warn_threshold(self, tmp_path):
        """trace_tokens ≥ trace_warn_threshold → warn_trace=True。"""
        usage = _make_token_usage(trace_tokens=3_500_000)
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config(trace_warn=3_000_000)):
            result = check_phase_budget("phase1", "abc123def456")

        assert result["warn_trace"] is True
        assert result["suspend_trace"] is False

    def test_trace_tokens_exceed_suspend_threshold(self, tmp_path):
        """trace_tokens ≥ trace_suspend_threshold → suspend_trace=True。"""
        usage = _make_token_usage(trace_tokens=9_000_000)
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config(trace_suspend=8_000_000)):
            result = check_phase_budget("phase1", "abc123def456")

        assert result["suspend_trace"] is True
        assert result["warn_trace"] is True  # suspend implies warn

    def test_result_contains_required_fields(self, tmp_path):
        """回傳 dict 包含所有必要欄位。"""
        usage = _make_token_usage()
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config()):
            result = check_phase_budget("phase2", "trace_abc_123")

        required_keys = [
            "phase", "trace_id", "phase_tokens", "phase_limit",
            "phase_utilization", "trace_tokens", "trace_warn_limit",
            "trace_suspend_limit", "trace_utilization",
            "warn_phase", "warn_trace", "suspend_trace", "checked_at",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_phase_utilization_calculation(self, tmp_path):
        """phase_utilization = phase_tokens / phase_limit。"""
        usage = _make_token_usage(phase="phase1", phase_tokens=250_000)
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config(phase1_limit=500_000)):
            result = check_phase_budget("phase1", "abc123def456")

        assert abs(result["phase_utilization"] - 0.5) < 0.01

    def test_unknown_phase_uses_fallback_limit(self, tmp_path):
        """未知 phase 名稱使用預設 limit，不 crash。"""
        usage = _make_token_usage(phase="phase_unknown")
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config()):
            result = check_phase_budget("phase_unknown", "abc123")

        assert isinstance(result["phase_limit"], int)
        assert result["phase_limit"] > 0

    def test_schema_v2_without_phases_field_graceful(self, tmp_path):
        """舊 schema（無 phases/traces 欄位）向後相容，回傳 tokens=0。"""
        today = datetime.now().strftime("%Y-%m-%d")
        usage_v2 = {
            "schema_version": 2,
            "daily": {
                today: {
                    "estimated_tokens": 500_000,
                    "tool_calls": 100,
                    "input_chars": 1000,
                    "output_chars": 5000,
                    # 無 phases / traces 欄位
                }
            },
            "updated": datetime.now().isoformat(),
        }
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage_v2), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config()):
            result = check_phase_budget("phase1", "abc123")

        assert result["phase_tokens"] == 0.0
        assert result["trace_tokens"] == 0.0
        assert result["warn_phase"] is False


# ── format_phase_summary ──────────────────────────────────────────────────────

class TestFormatPhaseSummary:
    def test_no_trace_record_returns_graceful_message(self, tmp_path):
        """trace_id 無對應記錄時，回傳提示訊息而非 crash。"""
        today = datetime.now().strftime("%Y-%m-%d")
        usage = {"daily": {today: {}}, "updated": ""}
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config()):
            summary = format_phase_summary("nonexistent_trace")

        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_with_trace_record_shows_totals(self, tmp_path):
        """有 trace 記錄時，摘要包含 total_tokens。"""
        trace_id = "abc123def456"
        usage = _make_token_usage(
            trace_id=trace_id,
            trace_tokens=1_500_000,
            phase_breakdown={"phase1": 500_000, "phase2": 1_000_000},
        )
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config()):
            summary = format_phase_summary(trace_id)

        assert "1,500,000" in summary or "1500000" in summary or "1.5" in summary

    def test_exceeding_warn_threshold_shows_warning(self, tmp_path):
        """超過 warn_threshold 時，摘要包含警告文字。"""
        trace_id = "abc123def456"
        usage = _make_token_usage(trace_id=trace_id, trace_tokens=4_000_000)
        usage_path = tmp_path / "token-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.phase_budget_reporter.TOKEN_USAGE_PATH", usage_path), \
             patch("tools.phase_budget_reporter._load_budget_config",
                   return_value=_make_budget_config(trace_warn=3_000_000)):
            summary = format_phase_summary(trace_id)

        # 應包含警告符號或百分比提示
        assert "⚠" in summary or "%" in summary
