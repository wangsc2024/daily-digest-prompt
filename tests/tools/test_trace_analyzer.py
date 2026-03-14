"""
tests/tools/test_trace_analyzer.py — 根因分析（P3-B）TDD

覆蓋重點：
  - analyze_trace：健康 trace / 錯誤 trace / 根因分類
  - _classify_entry：規則命中
  - run_analysis：多檔聚合 / 過濾 trace_id
  - format_text_report：無錯誤 / 有錯誤輸出格式
"""
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.trace_analyzer import (  # noqa: E402
    _classify_entry,
    _infer_phase,
    analyze_trace,
    format_text_report,
    run_analysis,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_entry(**kwargs) -> dict:
    base = {
        "ts": "2026-03-11T10:00:00+08:00",
        "sid": "test-sid",
        "trace_id": "abc123",
        "phase": "phase2",
        "agent": "test-agent",
        "tool": "Bash",
        "event": "post",
        "has_error": False,
        "tags": [],
        "error_category": "success",
    }
    base.update(kwargs)
    return base


# ── _classify_entry ───────────────────────────────────────────────────────────

class TestClassifyEntry:
    def test_api_failure_rule(self):
        entry = _make_entry(has_error=True, tags=["api-call"])
        result = _classify_entry(entry)
        assert result is not None
        assert result["category"] == "api_failure"

    def test_phase2_failure_rule(self):
        entry = _make_entry(has_error=True, phase="phase2")
        result = _classify_entry(entry)
        assert result is not None
        assert result["category"] in ("api_failure", "phase2_failure", "script_error")

    def test_loop_detected_rule(self):
        entry = _make_entry(has_error=False, tags=["loop-suspected"])
        result = _classify_entry(entry)
        assert result is not None
        assert result["category"] == "loop_detected"

    def test_hook_blocked_rule(self):
        entry = _make_entry(has_error=False, tags=["blocked"])
        result = _classify_entry(entry)
        assert result is not None
        assert result["category"] == "hook_blocked"

    def test_no_error_no_match(self):
        entry = _make_entry(has_error=False, tags=["normal"])
        result = _classify_entry(entry)
        assert result is None


# ── _infer_phase ──────────────────────────────────────────────────────────────

class TestInferPhase:
    def test_single_phase(self):
        entries = [_make_entry(phase="phase1"), _make_entry(phase="phase1")]
        assert _infer_phase(entries) == ["phase1"]

    def test_multiple_phases_sorted(self):
        entries = [_make_entry(phase="phase3"), _make_entry(phase="phase1"), _make_entry(phase="phase2")]
        assert _infer_phase(entries) == ["phase1", "phase2", "phase3"]

    def test_empty_phase_excluded(self):
        entries = [_make_entry(phase=""), _make_entry(phase="phase2")]
        assert _infer_phase(entries) == ["phase2"]


# ── analyze_trace ─────────────────────────────────────────────────────────────

class TestAnalyzeTrace:
    def test_healthy_trace(self):
        entries = [_make_entry(has_error=False) for _ in range(5)]
        result = analyze_trace("abc123", entries)
        assert result["category"] == "healthy"
        assert result["error_count"] == 0
        assert result["trace_id"] == "abc123"

    def test_error_trace_detected(self):
        entries = [
            _make_entry(has_error=False),
            _make_entry(has_error=True, tags=["api-call"]),
        ]
        result = analyze_trace("abc123", entries)
        assert result["error_count"] == 1
        assert result["category"] == "api_failure"
        assert result["root_cause"] != ""
        assert result["suggested_fix"] != ""

    def test_loop_trace_detected(self):
        entries = [_make_entry(has_error=False, tags=["loop-suspected"])]
        result = analyze_trace("abc123", entries)
        assert result["category"] == "loop_detected"
        assert result["error_count"] == 1

    def test_error_entries_capped_at_5(self):
        entries = [_make_entry(has_error=True) for _ in range(10)]
        result = analyze_trace("abc123", entries)
        assert len(result["error_entries"]) <= 5

    def test_total_entries_count(self):
        entries = [_make_entry() for _ in range(7)]
        result = analyze_trace("abc123", entries)
        assert result["total_entries"] == 7


# ── run_analysis ──────────────────────────────────────────────────────────────

class TestRunAnalysis:
    def _make_jsonl(self, tmp_path: Path, filename: str, entries: list[dict]) -> Path:
        f = tmp_path / filename
        with open(f, "w", encoding="utf-8") as fp:
            for e in entries:
                fp.write(json.dumps(e, ensure_ascii=False) + "\n")
        return f

    def test_returns_summary_structure(self, tmp_path):
        log_dir = tmp_path / "structured"
        log_dir.mkdir()
        self._make_jsonl(log_dir, f"{date.today().isoformat()}.jsonl", [
            _make_entry(trace_id="t1", has_error=False),
            _make_entry(trace_id="t1", has_error=False),
        ])
        with patch("tools.trace_analyzer.LOG_DIR", log_dir):
            report = run_analysis(days=1)
        assert "total_traces" in report
        assert "error_traces" in report
        assert "healthy_traces" in report
        assert "top_issues" in report
        assert "traces" in report

    def test_empty_log_dir(self, tmp_path):
        log_dir = tmp_path / "no_logs"
        log_dir.mkdir()
        with patch("tools.trace_analyzer.LOG_DIR", log_dir):
            report = run_analysis(days=1)
        assert report["total_traces"] == 0
        assert report["error_traces"] == 0

    def test_trace_id_filter(self, tmp_path):
        log_dir = tmp_path / "structured"
        log_dir.mkdir()
        self._make_jsonl(log_dir, f"{date.today().isoformat()}.jsonl", [
            _make_entry(trace_id="t1", has_error=True, tags=["api-call"]),
            _make_entry(trace_id="t2", has_error=False),
        ])
        with patch("tools.trace_analyzer.LOG_DIR", log_dir):
            report = run_analysis(days=1, trace_id_filter="t1")
        assert report["total_traces"] == 1
        assert report["traces"][0]["trace_id"] == "t1"

    def test_entries_without_trace_id_skipped(self, tmp_path):
        log_dir = tmp_path / "structured"
        log_dir.mkdir()
        self._make_jsonl(log_dir, f"{date.today().isoformat()}.jsonl", [
            _make_entry(trace_id=""),   # 無 trace_id，應跳過
            _make_entry(trace_id="t1"),
        ])
        with patch("tools.trace_analyzer.LOG_DIR", log_dir):
            report = run_analysis(days=1)
        assert report["total_traces"] == 1

    def test_top_issues_sorted_by_count(self, tmp_path):
        log_dir = tmp_path / "structured"
        log_dir.mkdir()
        entries = (
            [_make_entry(trace_id=f"t{i}", has_error=True, tags=["api-call"]) for i in range(3)]
            + [_make_entry(trace_id="t_loop", has_error=False, tags=["loop-suspected"])]
        )
        self._make_jsonl(log_dir, f"{date.today().isoformat()}.jsonl", entries)
        with patch("tools.trace_analyzer.LOG_DIR", log_dir):
            report = run_analysis(days=1)
        if report["top_issues"]:
            assert report["top_issues"][0]["count"] >= report["top_issues"][-1]["count"]


# ── format_text_report ────────────────────────────────────────────────────────

class TestFormatTextReport:
    def test_no_issues_shows_ok(self):
        report = {
            "analyzed_days": 3,
            "total_traces": 5,
            "error_traces": 0,
            "healthy_traces": 5,
            "top_issues": [],
            "traces": [],
        }
        text = format_text_report(report)
        assert "無異常" in text

    def test_issues_listed(self):
        report = {
            "analyzed_days": 3,
            "total_traces": 5,
            "error_traces": 2,
            "healthy_traces": 3,
            "top_issues": [
                {"category": "api_failure", "count": 2,
                 "root_cause": "外部 API 呼叫失敗", "suggested_fix": "確認 API"},
            ],
            "traces": [
                {"trace_id": "abc123", "error_count": 2,
                 "affected_phases": ["phase2"], "category": "api_failure",
                 "root_cause": "外部 API 呼叫失敗"},
            ],
        }
        text = format_text_report(report)
        assert "api_failure" in text
        assert "外部 API" in text
