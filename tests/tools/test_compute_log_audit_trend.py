"""Tests for tools/compute_log_audit_trend.py"""
import json
from datetime import date
from pathlib import Path

from tools.compute_log_audit_trend import DayPoint, build_series, compute_trend


def _daily(obj: dict) -> dict:
    return {"daily": obj, "total": {}, "failure_taxonomy": {}, "schema_version": 2, "updated": ""}


def test_build_series_skips_missing_days(tmp_path: Path):
    stats = tmp_path / "failure-stats.json"
    stats.write_text(
        json.dumps(
            _daily(
                {
                    "2026-03-18": {"phase_failure": 6},
                    "2026-03-20": {"phase_failure": 21},
                    "2026-03-21": {"phase_failure": 2},
                }
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = json.loads(stats.read_text(encoding="utf-8"))
    series = build_series(raw["daily"], end=date(2026, 3, 21), window_days=7)
    assert [p.date for p in series] == ["2026-03-18", "2026-03-20", "2026-03-21"]
    assert series[-1].phase_failure == 2


def test_worsening_last_higher_than_prior():
    series = [DayPoint("2026-03-21", 2), DayPoint("2026-03-22", 14)]
    out = compute_trend(series)
    assert out["short_term_vs_prior"] == "worsening"
    assert "不得描述為「改善中」" in out["summary_zh"]
    assert "惡化" in out["summary_zh"]


def test_improving_last_lower_than_prior():
    series = [DayPoint("2026-03-19", 8), DayPoint("2026-03-20", 21), DayPoint("2026-03-21", 2)]
    out = compute_trend(series)
    assert out["short_term_vs_prior"] == "improving"
    assert "改善" in out["summary_zh"]
    assert out["peak"]["value"] == 21


def test_peak_tie_prefers_later_date():
    series = [DayPoint("2026-03-18", 5), DayPoint("2026-03-20", 21), DayPoint("2026-03-22", 21)]
    out = compute_trend(series)
    assert out["peak"]["date"] == "2026-03-22"
    assert out["short_term_vs_prior"] == "stable"


def test_single_day_insufficient():
    out = compute_trend([DayPoint("2026-03-21", 2)])
    assert out["short_term_vs_prior"] == "n/a"
    assert "單日" in out["summary_zh"]
