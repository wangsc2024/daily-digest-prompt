"""
tests/tools/test_llm_router.py — LLM Router TDD（P1-B）

覆蓋重點：
  - routing_rules mapping lookup（O(1) dict，非 list 遍歷）
  - Groq / Claude 分流邏輯
  - Groq relay 離線降級（fallback_skipped）
  - 未知 task_type 預設 Claude
  - dry_run 模式
  - budget_suspended 路徑
  - update_token_usage 寫入 schema v2 欄位
"""
import json
import sys
import types
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 確保 REPO_ROOT 在 sys.path 中
REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.llm_router import match_rule, route, update_token_usage  # noqa: E402


# ─── fixtures ────────────────────────────────────────────────────────────────

MINIMAL_CONFIG = {
    "providers": {
        "groq": {
            "endpoint": "http://localhost:3002/groq/chat",
            "model": "llama-3.1-8b-instant",
        }
    },
    "routing_rules": {
        "news_summary": {
            "provider": "groq",
            "groq_mode": "summarize",
            "max_tokens": 200,
        },
        "en_to_zh": {
            "provider": "groq",
            "mode": "translate",
            "groq_mode": "translate",
            "max_tokens": 500,
        },
        "research_synthesis": {
            "provider": "claude",
            "rationale": "需要複雜推理+長上下文",
        },
        "policy_analysis": {
            "provider": "claude",
            "rationale": "需要深度語境理解",
        },
    },
    "fallback": {
        "groq_unavailable": {
            "action": "skip_and_log",
        }
    },
}


@pytest.fixture()
def fake_usage_file(tmp_path):
    """提供隔離的 token-usage.json，不污染真實 state/"""
    p = tmp_path / "token-usage.json"
    p.write_text(
        json.dumps({"schema_version": 2, "daily": {}}), encoding="utf-8"
    )
    return p


# ─── match_rule 單元測試 ──────────────────────────────────────────────────────

class TestMatchRule:
    def test_known_groq_task_returns_rule(self):
        rule = match_rule(MINIMAL_CONFIG, "news_summary")
        assert rule is not None
        assert rule["provider"] == "groq"

    def test_known_claude_task_returns_rule(self):
        rule = match_rule(MINIMAL_CONFIG, "research_synthesis")
        assert rule is not None
        assert rule["provider"] == "claude"

    def test_unknown_task_returns_none(self):
        rule = match_rule(MINIMAL_CONFIG, "totally_unknown_task")
        assert rule is None

    def test_mapping_format_o1_lookup(self):
        """確認是 dict lookup，不是 list 遍歷"""
        config = {
            "routing_rules": {
                "task_a": {"provider": "groq"},
                "task_b": {"provider": "claude"},
            }
        }
        assert match_rule(config, "task_a")["provider"] == "groq"
        assert match_rule(config, "task_b")["provider"] == "claude"

    def test_empty_routing_rules_returns_none(self):
        assert match_rule({"routing_rules": {}}, "any") is None

    def test_missing_routing_rules_returns_none(self):
        assert match_rule({}, "any") is None


# ─── route — dry_run 測試 ─────────────────────────────────────────────────────

class TestRouteDryRun:
    def _route_with_config(self, task_type, dry_run=True):
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG):
            with patch("tools.llm_router._check_budget", return_value=None):
                return route(task_type, "test content", dry_run=dry_run)

    def test_groq_dry_run_returns_provider_and_rule(self):
        result = self._route_with_config("news_summary")
        assert result["provider"] == "groq"
        assert result["dry_run"] is True
        assert "rule" in result

    def test_claude_dry_run_returns_provider_claude(self):
        result = self._route_with_config("research_synthesis")
        assert result["provider"] == "claude"
        assert result["dry_run"] is True

    def test_unknown_task_dry_run_falls_back_to_claude(self):
        result = self._route_with_config("unknown_xyz")
        assert result["provider"] == "claude"
        assert result.get("use_claude") is True
        assert "未在 routing_rules 中定義" in result.get("rationale", "")


# ─── route — Groq 成功路徑 ───────────────────────────────────────────────────

class TestRouteGroqSuccess:
    def test_groq_success_returns_result(self, fake_usage_file):
        relay_response = {"result": "快速的棕色狐狸", "cached": False, "model": "llama-3.1-8b-instant"}

        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=None), \
             patch("tools.llm_router.call_groq_relay", return_value=relay_response), \
             patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            result = route("en_to_zh", "The quick brown fox", dry_run=False)

        assert result["provider"] == "groq"
        assert result["result"] == "快速的棕色狐狸"
        assert result["cached"] is False
        assert result["task_type"] == "en_to_zh"

    def test_groq_prefers_groq_mode_over_mode(self, fake_usage_file):
        """groq_mode 欄位優先於 mode 欄位"""
        captured = {}

        def fake_relay(endpoint, mode, content, max_tokens):
            captured["mode"] = mode
            return {"result": "ok", "cached": False}

        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=None), \
             patch("tools.llm_router.call_groq_relay", side_effect=fake_relay), \
             patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            route("en_to_zh", "test", dry_run=False)

        # en_to_zh 有 groq_mode=translate，應用 translate
        assert captured["mode"] == "translate"


# ─── route — Groq 離線降級 ───────────────────────────────────────────────────

class TestRouteGroqFallback:
    def test_url_error_returns_fallback_skipped(self, fake_usage_file):
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=None), \
             patch("tools.llm_router.call_groq_relay",
                   side_effect=urllib.error.URLError("Connection refused")), \
             patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            result = route("news_summary", "test", dry_run=False)

        assert result["provider"] == "fallback_skipped"
        assert result["action"] == "skip_and_log"
        assert "task_type" in result

    def test_unknown_exception_propagates(self, fake_usage_file):
        """未知異常（如 RuntimeError）不再被靜默吞掉，應向上傳播。"""
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=None), \
             patch("tools.llm_router.call_groq_relay",
                   side_effect=RuntimeError("unexpected")), \
             patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            with pytest.raises(RuntimeError, match="unexpected"):
                route("news_summary", "test", dry_run=False)

    def test_connection_error_returns_fallback_skipped(self, fake_usage_file):
        """已知的連線錯誤應被捕獲並降級。"""
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=None), \
             patch("tools.llm_router.call_groq_relay",
                   side_effect=ConnectionError("refused")), \
             patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            result = route("news_summary", "test", dry_run=False)

        assert result["provider"] == "fallback_skipped"


# ─── route — Claude 路徑 ─────────────────────────────────────────────────────

class TestRouteClaudePath:
    def test_claude_path_returns_use_claude_true(self, fake_usage_file):
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=None), \
             patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            result = route("research_synthesis", "deep analysis", dry_run=False)

        assert result["provider"] == "claude"
        assert result["use_claude"] is True
        assert result["task_type"] == "research_synthesis"

    def test_claude_path_includes_rationale(self, fake_usage_file):
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=None), \
             patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            result = route("research_synthesis", "test", dry_run=False)

        assert "rationale" in result
        assert len(result["rationale"]) > 0


# ─── route — 預算暫停路徑 ────────────────────────────────────────────────────

class TestRouteBudgetSuspended:
    def test_budget_block_returns_budget_suspended(self):
        budget_block = {
            "provider": "budget_suspended",
            "reason": "daily_budget_exhausted",
            "utilization": 1.05,
        }
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget", return_value=budget_block):
            result = route("news_summary", "test", dry_run=False)

        assert result["provider"] == "budget_suspended"
        assert result["reason"] == "daily_budget_exhausted"

    def test_dry_run_skips_budget_check(self):
        """dry_run 模式不觸發預算檢查"""
        with patch("tools.llm_router.load_config", return_value=MINIMAL_CONFIG), \
             patch("tools.llm_router._check_budget") as mock_budget:
            route("news_summary", "test", dry_run=True)

        mock_budget.assert_not_called()


# ─── update_token_usage ──────────────────────────────────────────────────────

class TestUpdateTokenUsage:
    def test_groq_call_increments_groq_calls(self, fake_usage_file):
        import datetime
        today = datetime.date.today().isoformat()

        with patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            update_token_usage("groq")

        data = json.loads(fake_usage_file.read_text(encoding="utf-8"))
        assert data["daily"][today]["groq_calls"] == 1

    def test_claude_call_increments_claude_calls(self, fake_usage_file):
        import datetime
        today = datetime.date.today().isoformat()

        with patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            update_token_usage("claude")

        data = json.loads(fake_usage_file.read_text(encoding="utf-8"))
        assert data["daily"][today]["claude_calls"] == 1

    def test_multiple_calls_accumulate(self, fake_usage_file):
        import datetime
        today = datetime.date.today().isoformat()

        with patch("tools.llm_router.TOKEN_USAGE_PATH", fake_usage_file):
            update_token_usage("groq")
            update_token_usage("groq")
            update_token_usage("claude")

        data = json.loads(fake_usage_file.read_text(encoding="utf-8"))
        assert data["daily"][today]["groq_calls"] == 2
        assert data["daily"][today]["claude_calls"] == 1

    def test_missing_file_does_not_raise(self):
        """TOKEN_USAGE_PATH 不存在時靜默忽略"""
        nonexistent = Path("/nonexistent/token-usage.json")
        with patch("tools.llm_router.TOKEN_USAGE_PATH", nonexistent):
            update_token_usage("groq")  # 不應拋出例外
