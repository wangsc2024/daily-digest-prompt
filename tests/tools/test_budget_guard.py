"""
tests/tools/test_budget_guard.py — 預算治理（P4-C）TDD

覆蓋重點（12 個測試）：
  - check_budget：允許通過、80% 警告閾值、100% 暫停閾值
  - provider 分流：groq（呼叫次數）vs claude（token 數）
  - 配置/用量檔案缺失時的向後相容（允許通過）
  - 多 provider 計算（groq_calls vs estimated_tokens）
  - get_status 結構驗證
"""
import json
import sys
from pathlib import Path
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.budget_guard import check_budget, get_status  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_config(claude_tokens=5_000_000, groq_calls=100,
                 warn_threshold=0.80, suspend_threshold=1.00) -> dict:
    return {
        "daily_budget": {
            "claude_tokens": claude_tokens,
            "groq_calls": groq_calls,
            "warn_threshold": warn_threshold,
            "suspend_threshold": suspend_threshold,
        }
    }


def _make_usage(today: str, estimated_tokens=0, groq_calls=0) -> dict:
    return {
        "daily": {
            today: {
                "estimated_tokens": estimated_tokens,
                "groq_calls": groq_calls,
            }
        }
    }


# ── check_budget ──────────────────────────────────────────────────────────────

class TestCheckBudget:
    def _patch_both(self, config: dict, usage: dict):
        """回傳同時 patch 配置 + 用量的 context manager pair"""
        return (
            patch("tools.budget_guard._load_budget_config", return_value=config),
            patch("tools.budget_guard.TOKEN_USAGE",
                  new_callable=lambda: type("_FakePath", (), {
                      "read_text": staticmethod(lambda **_: json.dumps(usage))
                  })),
        )

    def test_allowed_under_threshold(self):
        today = date.today().isoformat()
        config = _make_config(claude_tokens=1_000_000)
        usage = _make_usage(today, estimated_tokens=100_000)  # 10%

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.return_value = json.dumps(usage)
            result = check_budget("research_synthesis", "claude", estimated_tokens=1000)

        assert result["allowed"] is True
        assert result["utilization"] < 1.0

    def test_suspended_at_100_percent_claude(self):
        today = date.today().isoformat()
        config = _make_config(claude_tokens=1_000_000)
        # 已使用 999_000，再加 50_000 → 超過 100%
        usage = _make_usage(today, estimated_tokens=999_000)

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.return_value = json.dumps(usage)
            result = check_budget("research_synthesis", "claude", estimated_tokens=50_000)

        assert result["allowed"] is False
        assert result["reason"] == "daily_budget_exhausted"
        assert result["utilization"] >= 1.0

    def test_suspended_at_100_percent_groq(self):
        today = date.today().isoformat()
        config = _make_config(groq_calls=100)
        usage = _make_usage(today, groq_calls=100)  # 已達上限

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.return_value = json.dumps(usage)
            result = check_budget("en_to_zh", "groq")

        assert result["allowed"] is False
        assert result["reason"] == "daily_budget_exhausted"

    def test_warn_threshold_triggers_notification(self):
        today = date.today().isoformat()
        config = _make_config(groq_calls=100, warn_threshold=0.50, suspend_threshold=1.00)
        usage = _make_usage(today, groq_calls=80)  # 80/100 = 80% > warn(50%)

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path, \
             patch("tools.budget_guard._send_budget_warning") as mock_warn:
            mock_path.read_text.return_value = json.dumps(usage)
            result = check_budget("en_to_zh", "groq")

        assert result["allowed"] is True
        mock_warn.assert_called_once()

    def test_below_warn_no_notification(self):
        today = date.today().isoformat()
        config = _make_config(groq_calls=100, warn_threshold=0.80)
        usage = _make_usage(today, groq_calls=10)  # 10% < warn

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path, \
             patch("tools.budget_guard._send_budget_warning") as mock_warn:
            mock_path.read_text.return_value = json.dumps(usage)
            check_budget("en_to_zh", "groq")

        mock_warn.assert_not_called()

    def test_groq_uses_call_count_not_tokens(self):
        """groq provider 計算呼叫次數（1次），不使用 estimated_tokens"""
        today = date.today().isoformat()
        config = _make_config(groq_calls=10)
        usage = _make_usage(today, groq_calls=0)

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.return_value = json.dumps(usage)
            # estimated_tokens=999_999 不應影響 groq 計算
            result = check_budget("en_to_zh", "groq", estimated_tokens=999_999)

        # groq_calls=0+1=1，1/10=10%，應允許
        assert result["allowed"] is True
        assert result["utilization"] == pytest.approx(0.1)

    def test_claude_uses_token_count(self):
        """claude provider 用 estimated_tokens 累計"""
        today = date.today().isoformat()
        config = _make_config(claude_tokens=1_000)
        usage = _make_usage(today, estimated_tokens=900)

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.return_value = json.dumps(usage)
            result = check_budget("research_synthesis", "claude", estimated_tokens=200)

        # (900+200)/1000 = 1.1 → suspended
        assert result["allowed"] is False

    def test_missing_config_allows_through(self):
        """配置檔缺失時，向後相容（允許通過）"""
        with patch("tools.budget_guard._load_budget_config",
                   side_effect=FileNotFoundError("config missing")):
            result = check_budget("news_summary", "groq")

        assert result["allowed"] is True
        assert result["utilization"] == 0.0

    def test_missing_usage_file_allows_through(self):
        """用量檔案缺失時，允許通過"""
        config = _make_config()
        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.side_effect = FileNotFoundError
            result = check_budget("news_summary", "groq")

        assert result["allowed"] is True

    def test_no_usage_today_starts_at_zero(self):
        """今日無用量記錄時，從 0 開始計算"""
        today = date.today().isoformat()
        config = _make_config(groq_calls=100)
        usage = {"daily": {}}  # 無今日記錄

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.return_value = json.dumps(usage)
            result = check_budget("en_to_zh", "groq")

        assert result["allowed"] is True
        assert result["utilization"] == pytest.approx(0.01)  # 1/100


# ── get_status ────────────────────────────────────────────────────────────────

class TestGetStatus:
    def test_status_structure(self):
        today = date.today().isoformat()
        config = _make_config(claude_tokens=5_000_000, groq_calls=100)
        usage = _make_usage(today, estimated_tokens=1_000_000, groq_calls=30)

        with patch("tools.budget_guard._load_budget_config", return_value=config), \
             patch("tools.budget_guard.TOKEN_USAGE") as mock_path:
            mock_path.read_text.return_value = json.dumps(usage)
            status = get_status()

        assert "claude_tokens" in status
        assert "groq_calls" in status
        assert "used" in status["claude_tokens"]
        assert "limit" in status["claude_tokens"]
        assert "utilization" in status["claude_tokens"]

    def test_status_fallback_on_error(self):
        """get_status 在任何錯誤下都應回傳合法結構"""
        with patch("tools.budget_guard._load_budget_config",
                   side_effect=Exception("broken")):
            status = get_status()

        # 應回傳 fallback 結構（不崩潰）
        assert isinstance(status, dict)
