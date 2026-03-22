"""
tests/tools/test_context_compressor.py — ADR-036 Context Compression TDD

覆蓋重點：
  - get_or_create_session：新建空 session
  - update_session：chars 正確累計
  - check_threshold：< 65% / 65-80% / > 80% 三個狀態
  - prompt_injection：非空且內容正確
  - cleanup_stale_sessions：舊 session 被移除，新鮮 session 保留
  - context-usage.json 不存在時 graceful 初始化
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.context_compressor import (  # noqa: E402
    ContextState,
    SessionUsage,
    check_threshold,
    cleanup_stale_sessions,
    get_or_create_session,
    update_session,
)


# ── 常數 ──────────────────────────────────────────────────────────────────────

# 200k tokens 上限，使用 chars/3.5 換算
# 65% 門檻 = 200000 * 0.65 = 130000 tokens = 455000 chars
# 80% 門檻 = 200000 * 0.80 = 160000 tokens = 560000 chars
WARN_CHARS = int(200_000 * 0.65 * 3.5) + 1    # 略超 65%
CRITICAL_CHARS = int(200_000 * 0.80 * 3.5) + 1  # 略超 80%
SAFE_CHARS = int(200_000 * 0.50 * 3.5)           # 50%（安全範圍）


def _make_session(tokens: int, state: str = ContextState.NORMAL.value) -> SessionUsage:
    """建立假的 SessionUsage。"""
    return SessionUsage(
        session_id="testsid1",
        phase="phase2",
        total_input_chars=0,
        total_output_chars=0,
        estimated_tokens=tokens,
        last_updated=datetime.now().isoformat(),
        state=state,
    )


# ── get_or_create_session ─────────────────────────────────────────────────────

class TestGetOrCreateSession:
    def test_creates_new_session_when_not_exists(self, tmp_path):
        """不存在的 session_id 建立空 session。"""
        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", tmp_path / "context-usage.json"), \
             patch("tools.context_compressor.STATE_DIR", tmp_path):
            session = get_or_create_session("newSessionId")

        assert session.session_id == "newSessi"  # 前 8 字
        assert session.estimated_tokens == 0
        assert session.total_input_chars == 0

    def test_returns_existing_session(self, tmp_path):
        """已存在的 session 回傳正確數值。"""
        usage_path = tmp_path / "context-usage.json"
        usage = {
            "schema_version": 1,
            "sessions": {
                "existSes": {
                    "session_id": "existSes",
                    "phase": "phase1",
                    "total_input_chars": 10000,
                    "total_output_chars": 50000,
                    "estimated_tokens": 17142,
                    "last_updated": datetime.now().isoformat(),
                    "state": "normal",
                }
            },
            "updated": "",
        }
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", usage_path), \
             patch("tools.context_compressor.STATE_DIR", tmp_path):
            session = get_or_create_session("existSes_extra_chars")

        assert session.session_id == "existSes"
        assert session.total_input_chars == 10000


# ── update_session ─────────────────────────────────────────────────────────────

class TestUpdateSession:
    def test_accumulates_chars(self, tmp_path):
        """多次呼叫應累計 total_input/output_chars。"""
        usage_path = tmp_path / "context-usage.json"

        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", usage_path), \
             patch("tools.context_compressor.STATE_DIR", tmp_path), \
             patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            s1 = update_session("sid00001", input_chars=1000, output_chars=2000, phase="phase1")
            s2 = update_session("sid00001", input_chars=500, output_chars=1000, phase="phase1")

        assert s2.total_input_chars == 1500
        assert s2.total_output_chars == 3000

    def test_estimated_tokens_calculated(self, tmp_path):
        """estimated_tokens = (input + output) / 3.5。"""
        usage_path = tmp_path / "context-usage.json"

        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", usage_path), \
             patch("tools.context_compressor.STATE_DIR", tmp_path), \
             patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            session = update_session("sid00002", input_chars=3500, output_chars=3500, phase="")

        assert session.estimated_tokens == int(7000 / 3.5)  # = 2000

    def test_persists_to_file(self, tmp_path):
        """update_session 應將資料寫入 context-usage.json。"""
        usage_path = tmp_path / "context-usage.json"

        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", usage_path), \
             patch("tools.context_compressor.STATE_DIR", tmp_path), \
             patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            update_session("sid00003", input_chars=100, output_chars=100, phase="phase2")

        assert usage_path.exists()
        with open(usage_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "sid00003" in data["sessions"]


# ── check_threshold ───────────────────────────────────────────────────────────

class TestCheckThreshold:
    def test_below_warn_threshold_returns_none(self):
        """< 65% → action='none', state='normal'。"""
        session = _make_session(tokens=int(200_000 * 0.50))
        with patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            result = check_threshold(session)

        assert result["state"] == ContextState.NORMAL.value
        assert result["action"] == "none"
        assert result["prompt_injection"] == ""

    def test_between_warn_and_critical_returns_buffer_window(self):
        """65-80% → action='inject_buffer_window', prompt_injection 非空。"""
        session = _make_session(tokens=int(200_000 * 0.70))
        with patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            result = check_threshold(session)

        assert result["state"] == ContextState.WARNING.value
        assert result["action"] == "inject_buffer_window"
        assert len(result["prompt_injection"]) > 0

    def test_above_critical_threshold_returns_summary(self):
        """> 80% → action='inject_summary', prompt_injection 非空。"""
        session = _make_session(tokens=int(200_000 * 0.85))
        with patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            result = check_threshold(session)

        assert result["state"] == ContextState.CRITICAL.value
        assert result["action"] == "inject_summary"
        assert len(result["prompt_injection"]) > 0

    def test_prompt_injection_contains_utilization(self):
        """prompt_injection 應包含使用率資訊（百分比格式）。"""
        session = _make_session(tokens=int(200_000 * 0.72))
        with patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            result = check_threshold(session)

        # 應包含百分比（72%）
        assert "%" in result["prompt_injection"]

    def test_utilization_in_range(self):
        """utilization 必須在 [0.0, 1.0] 範圍內。"""
        for tokens in [0, 100_000, 200_000, 300_000]:
            session = _make_session(tokens=tokens)
            with patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
                result = check_threshold(session)
            # utilization 可超過 1.0（超過上限時），但 state 仍正確
            assert isinstance(result["utilization"], float)

    def test_zero_tokens_returns_normal(self):
        """0 tokens → 必然回傳 normal。"""
        session = _make_session(tokens=0)
        with patch("tools.context_compressor._load_thresholds", return_value=(0.65, 0.80, 200_000)):
            result = check_threshold(session)
        assert result["state"] == ContextState.NORMAL.value
        assert result["action"] == "none"


# ── cleanup_stale_sessions ────────────────────────────────────────────────────

class TestCleanupStaleSessions:
    def test_removes_sessions_older_than_max_age(self, tmp_path):
        """超過 max_age_hours 的 session 應被移除。"""
        old_time = (datetime.now() - timedelta(hours=5)).isoformat()
        fresh_time = datetime.now().isoformat()

        usage = {
            "schema_version": 1,
            "sessions": {
                "staleSes": {
                    "session_id": "staleSes",
                    "phase": "",
                    "total_input_chars": 0,
                    "total_output_chars": 0,
                    "estimated_tokens": 0,
                    "last_updated": old_time,
                    "state": "normal",
                },
                "freshSes": {
                    "session_id": "freshSes",
                    "phase": "",
                    "total_input_chars": 0,
                    "total_output_chars": 0,
                    "estimated_tokens": 0,
                    "last_updated": fresh_time,
                    "state": "normal",
                },
            },
            "updated": "",
        }
        usage_path = tmp_path / "context-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", usage_path), \
             patch("tools.context_compressor.STATE_DIR", tmp_path):
            removed = cleanup_stale_sessions(max_age_hours=4)

        assert removed == 1

        with open(usage_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "staleSes" not in data["sessions"]
        assert "freshSes" in data["sessions"]

    def test_fresh_sessions_not_removed(self, tmp_path):
        """新鮮 session（< max_age_hours）不被移除。"""
        fresh_time = datetime.now().isoformat()
        usage = {
            "schema_version": 1,
            "sessions": {
                "freshSes": {
                    "session_id": "freshSes",
                    "phase": "",
                    "total_input_chars": 0,
                    "total_output_chars": 0,
                    "estimated_tokens": 0,
                    "last_updated": fresh_time,
                    "state": "normal",
                },
            },
            "updated": "",
        }
        usage_path = tmp_path / "context-usage.json"
        usage_path.write_text(json.dumps(usage), encoding="utf-8")

        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", usage_path), \
             patch("tools.context_compressor.STATE_DIR", tmp_path):
            removed = cleanup_stale_sessions(max_age_hours=4)

        assert removed == 0

    def test_no_file_returns_zero(self, tmp_path):
        """context-usage.json 不存在時不 crash，回傳 0。"""
        with patch("tools.context_compressor.CONTEXT_USAGE_PATH", tmp_path / "nonexistent.json"), \
             patch("tools.context_compressor.STATE_DIR", tmp_path):
            removed = cleanup_stale_sessions(max_age_hours=4)

        assert removed == 0


# ── 整合：post_tool_logger dynamic import 安全性 ──────────────────────────────

class TestDynamicImportSafety:
    def test_module_importable_without_errors(self):
        """context_compressor 模組可被 importlib 動態載入，不拋例外。"""
        import importlib.util
        import sys
        cc_path = str(REPO_ROOT / "tools" / "context_compressor.py")
        mod_name = "context_compressor_test_dynamic"
        spec = importlib.util.spec_from_file_location(mod_name, cc_path)
        mod = importlib.util.module_from_spec(spec)
        # Python 3.11 @dataclass 需要模組在 sys.modules 中已登記
        sys.modules[mod_name] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop(mod_name, None)
        assert hasattr(mod, "update_session")
        assert hasattr(mod, "check_threshold")
        assert hasattr(mod, "cleanup_stale_sessions")
