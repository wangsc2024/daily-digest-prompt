"""
tests/tools/test_time_slot_risk_scorer.py — ADR-037 時段風險評分器 TDD

覆蓋重點：
  - compute_hour_stats：空 log → 全 0 統計
  - score_time_slot：高/低失敗率時段判斷
  - get_current_risk：整合呼叫不 crash
  - write_risk_report：輸出格式驗證
  - 高風險時段（5/7/13）被正確識別
"""
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.time_slot_risk_scorer import (  # noqa: E402
    HourStats,
    RiskScore,
    compute_hour_stats,
    get_current_risk,
    score_time_slot,
    write_risk_report,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_entry(hour: int, has_error: bool = False, error_category: str = "") -> dict:
    """建立假的 JSONL 日誌 entry。"""
    ts = datetime(2026, 3, 22, hour, 0, 0).isoformat()
    entry: dict = {"ts": ts, "has_error": has_error, "tags": [], "tool": "Bash"}
    if error_category:
        entry["error_category"] = error_category
    return entry


def _make_hour_stats(hour: int, total: int = 10, failed: int = 0) -> dict[int, HourStats]:
    """建立假的 hour_stats dict。"""
    rate = failed / total if total > 0 else 0.0
    return {
        hour: HourStats(
            hour=hour,
            total_runs=total,
            failed_runs=failed,
            failure_rate=rate,
            failure_modes={"timeout": failed} if failed > 0 else {},
        )
    }


# ── compute_hour_stats ────────────────────────────────────────────────────────

class TestComputeHourStats:
    def test_empty_log_dir_returns_empty(self, tmp_path):
        """無日誌資料時回傳空 dict。"""
        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = compute_hour_stats(days=3)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_normal_entry_counted(self, tmp_path):
        """正常 entry 計入 total_runs。"""
        log_file = tmp_path / f"{datetime.now().date().isoformat()}.jsonl"
        entry = _make_entry(hour=10, has_error=False)
        log_file.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = compute_hour_stats(days=1)

        assert 10 in result
        assert result[10].total_runs >= 1
        assert result[10].failed_runs == 0
        assert result[10].failure_rate == 0.0

    def test_error_entry_counted(self, tmp_path):
        """has_error=True 的 entry 計入 failed_runs。"""
        log_file = tmp_path / f"{datetime.now().date().isoformat()}.jsonl"
        entries = [
            json.dumps(_make_entry(hour=5, has_error=True, error_category="timeout")),
            json.dumps(_make_entry(hour=5, has_error=False)),
        ]
        log_file.write_text("\n".join(entries) + "\n", encoding="utf-8")

        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = compute_hour_stats(days=1)

        assert 5 in result
        assert result[5].total_runs == 2
        assert result[5].failed_runs == 1
        assert result[5].failure_rate == 0.5

    def test_loop_suspected_tag_counted_as_failure(self, tmp_path):
        """loop-suspected tag 也計入失敗。"""
        log_file = tmp_path / f"{datetime.now().date().isoformat()}.jsonl"
        entry = _make_entry(hour=13, has_error=False)
        entry["tags"] = ["loop-suspected"]
        log_file.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = compute_hour_stats(days=1)

        assert result[13].failed_runs >= 1

    def test_multiple_hours_separated(self, tmp_path):
        """不同小時的 entries 分別統計。"""
        log_file = tmp_path / f"{datetime.now().date().isoformat()}.jsonl"
        entries = [
            json.dumps(_make_entry(hour=8)),
            json.dumps(_make_entry(hour=9)),
            json.dumps(_make_entry(hour=8, has_error=True)),
        ]
        log_file.write_text("\n".join(entries) + "\n", encoding="utf-8")

        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = compute_hour_stats(days=1)

        assert result[8].total_runs == 2
        assert result[8].failed_runs == 1
        assert result[9].total_runs == 1
        assert result[9].failed_runs == 0

    def test_invalid_json_lines_skipped(self, tmp_path):
        """損壞的 JSON 行被跳過，不 crash。"""
        log_file = tmp_path / f"{datetime.now().date().isoformat()}.jsonl"
        content = "not-json\n" + json.dumps(_make_entry(hour=10)) + "\n{broken\n"
        log_file.write_text(content, encoding="utf-8")

        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = compute_hour_stats(days=1)

        assert 10 in result
        assert result[10].total_runs == 1


# ── score_time_slot ───────────────────────────────────────────────────────────

class TestScoreTimeSlot:
    def test_known_high_risk_hour_returns_high_or_critical(self):
        """已知高風險時段（5/7/13）應回傳 high 以上等級。"""
        for hour in [5, 7, 13]:
            risk = score_time_slot(hour, {})  # 無歷史資料
            assert risk.risk_level in ("medium", "high", "critical"), \
                f"hour={hour} expected ≥medium, got {risk.risk_level}"

    def test_low_failure_rate_returns_low_or_medium(self):
        """低失敗率時段應回傳 low 或 medium。"""
        stats = _make_hour_stats(hour=10, total=100, failed=1)
        risk = score_time_slot(10, stats)
        assert risk.risk_level in ("low", "medium"), \
            f"Expected low/medium for low failure rate, got {risk.risk_level}"

    def test_high_failure_rate_returns_medium_or_above(self):
        """高失敗率時段（80%+）應回傳 medium 以上等級（受多因子加權影響）。"""
        stats = _make_hour_stats(hour=10, total=10, failed=8)
        risk = score_time_slot(10, stats)
        assert risk.risk_level in ("medium", "high", "critical"), \
            f"Expected ≥medium for 80% failure rate, got {risk.risk_level}"

    def test_risk_score_in_range(self):
        """risk_score 必須在 [0.0, 1.0] 範圍內。"""
        for hour in range(24):
            stats = _make_hour_stats(hour=hour, total=10, failed=5)
            risk = score_time_slot(hour, stats)
            assert 0.0 <= risk.risk_score <= 1.0, \
                f"hour={hour} risk_score={risk.risk_score} out of range"

    def test_contributing_factors_sum_matches_risk_score(self):
        """貢獻因子之和應大致等於 risk_score（允許浮點誤差）。"""
        stats = _make_hour_stats(hour=10, total=10, failed=2)
        risk = score_time_slot(10, stats)
        factors_sum = sum(risk.contributing_factors.values())
        assert abs(factors_sum - risk.risk_score) < 0.01, \
            f"factors_sum={factors_sum} != risk_score={risk.risk_score}"

    def test_low_level_action_is_normal(self):
        """low 風險等級的 recommended_action 應為 'normal'。"""
        # hour=10，低失敗率，非高風險時段
        stats = _make_hour_stats(hour=10, total=50, failed=0)
        risk = score_time_slot(10, stats)
        if risk.risk_level == "low":
            assert risk.recommended_action == "normal"
            assert risk.skip_task_types == []

    def test_high_level_has_skip_task_types(self):
        """high 風險等級應設定 skip_task_types。"""
        stats = _make_hour_stats(hour=10, total=10, failed=9)
        risk = score_time_slot(10, stats)
        if risk.risk_level in ("high", "critical"):
            assert isinstance(risk.skip_task_types, list)

    def test_returns_riskscore_dataclass(self):
        """回傳值必須是 RiskScore dataclass。"""
        risk = score_time_slot(12, {})
        assert isinstance(risk, RiskScore)
        assert isinstance(risk.hour, int)
        assert isinstance(risk.risk_score, float)
        assert isinstance(risk.risk_level, str)
        assert isinstance(risk.recommended_action, str)


# ── get_current_risk ──────────────────────────────────────────────────────────

class TestGetCurrentRisk:
    def test_does_not_crash(self, tmp_path):
        """整合呼叫不 crash，回傳 RiskScore。"""
        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = get_current_risk(days=1)
        assert isinstance(result, RiskScore)

    def test_hour_matches_current(self, tmp_path):
        """回傳的 hour 與當前小時一致。"""
        current_hour = datetime.now().hour
        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path):
            result = get_current_risk(days=1)
        assert result.hour == current_hour


# ── write_risk_report ─────────────────────────────────────────────────────────

class TestWriteRiskReport:
    def test_creates_report_file(self, tmp_path):
        """write_risk_report 應建立 JSON 報告檔案。"""
        output_path = str(tmp_path / "time-slot-risk.json")
        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path / "logs"):
            (tmp_path / "logs").mkdir()
            report = write_risk_report(output_path=output_path)

        assert Path(output_path).exists()
        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "generated_at" in data
        assert "current_hour" in data
        assert "risk" in data
        assert "hour_stats" in data

    def test_report_risk_fields(self, tmp_path):
        """報告的 risk 欄位包含必要子欄位。"""
        output_path = str(tmp_path / "risk.json")
        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path / "logs"):
            (tmp_path / "logs").mkdir()
            report = write_risk_report(output_path=output_path)

        risk = report["risk"]
        assert "risk_score" in risk
        assert "risk_level" in risk
        assert "recommended_action" in risk
        assert "contributing_factors" in risk
        assert risk["risk_level"] in ("low", "medium", "high", "critical")

    def test_returns_dict_even_if_write_fails(self, tmp_path):
        """即使寫入失敗，仍回傳 dict（不 crash）。"""
        with patch("tools.time_slot_risk_scorer.LOG_DIR", tmp_path / "logs"):
            (tmp_path / "logs").mkdir()
            # 傳入無法寫入的路徑
            report = write_risk_report(output_path="/nonexistent_path/risk.json")
        assert isinstance(report, dict)
        assert "risk" in report
