"""
tests/tools/test_score_research_quality.py — 研究品質評分工具測試

覆蓋重點：
  - 5 維度評分函數的邊界案例
  - score_result() 完整流程（含 placeholder 跳過）
  - update_quality_file() 30 天滾動窗口
  - 低分告警機制
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import __path__ as _  # noqa: F401 — ensure tools is importable

# 匯入待測模組前先設定 monkeypatch-friendly 的路徑
import tools  # noqa: F811
score_mod_path = REPO_ROOT / "tools" / "score-research-quality.py"

# 因為檔名含連字號，需用 importlib 匯入
import importlib.util
spec = importlib.util.spec_from_file_location("score_research_quality", score_mod_path)
srq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srq)

score_source_count = srq.score_source_count
score_source_diversity = srq.score_source_diversity
score_kb_novelty = srq.score_kb_novelty
score_output_depth = srq.score_output_depth
score_tool_utilization = srq.score_tool_utilization
score_result = srq.score_result
update_quality_file = srq.update_quality_file
LOW_SCORE_THRESHOLD = srq.LOW_SCORE_THRESHOLD


# ─── score_source_count ──────────────────────────────────────────────────────

class TestScoreSourceCount:
    def test_no_urls_returns_zero(self):
        assert score_source_count("純文字無連結") == 0

    def test_one_url_returns_8(self):
        assert score_source_count("見 https://example.com 說明") == 8

    def test_three_urls_returns_15(self):
        text = "https://a.com https://b.com https://c.com"
        assert score_source_count(text) == 15

    def test_five_unique_urls_returns_25(self):
        text = " ".join(f"https://site{i}.com" for i in range(5))
        assert score_source_count(text) == 25

    def test_duplicate_urls_counted_once(self):
        text = "https://a.com https://a.com https://a.com"
        assert score_source_count(text) == 8  # 1 unique


# ─── score_source_diversity ──────────────────────────────────────────────────

class TestScoreSourceDiversity:
    def test_no_urls_returns_zero(self):
        assert score_source_diversity("沒有連結") == 0

    def test_single_domain_returns_5(self):
        assert score_source_diversity("https://example.com/a https://example.com/b") == 5

    def test_two_domains_returns_12(self):
        text = "https://example.com/a https://other.org/b"
        assert score_source_diversity(text) == 12

    def test_three_domains_returns_20(self):
        text = "https://a.com https://b.org https://c.net"
        assert score_source_diversity(text) == 20


# ─── score_output_depth ──────────────────────────────────────────────────────

class TestScoreOutputDepth:
    @pytest.mark.parametrize("length,expected", [
        (0, 0),
        (100, 0),
        (200, 5),
        (500, 10),
        (800, 15),
        (1500, 20),
        (5000, 20),
    ])
    def test_length_boundaries(self, length, expected):
        text = "x" * length
        assert score_output_depth(text) == expected


# ─── score_tool_utilization ──────────────────────────────────────────────────

class TestScoreToolUtilization:
    def test_no_tools_no_urls_returns_zero(self):
        assert score_tool_utilization({"output": "純文字"}) == 0

    def test_url_in_output_returns_10(self):
        assert score_tool_utilization({"output": "來源 https://example.com"}) == 10

    def test_web_tool_calls_returns_10(self):
        data = {"tool_calls": [{"name": "WebSearch"}], "output": "text"}
        assert score_tool_utilization(data) == 10

    def test_url_in_result_field(self):
        assert score_tool_utilization({"result": "see https://x.com"}) == 10


# ─── score_kb_novelty ────────────────────────────────────────────────────────

class TestScoreKbNovelty:
    def test_no_registry_returns_15(self, tmp_path):
        with patch.object(srq, "REGISTRY_PATH", tmp_path / "nonexistent.json"):
            assert score_kb_novelty("新主題內容", "test_key") == 15

    def test_empty_registry_returns_25(self, tmp_path):
        registry_path = tmp_path / "registry.json"
        registry_path.write_text(json.dumps({"entries": []}), encoding="utf-8")
        with patch.object(srq, "REGISTRY_PATH", registry_path):
            assert score_kb_novelty("完全新主題", "test_key") == 25

    def test_high_overlap_returns_low_score(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat()
        entries = [
            {"task_type": "test_key", "timestamp": now, "topic": "人工智慧 機器學習 深度學習 LLM"},
        ]
        registry_path = tmp_path / "registry.json"
        registry_path.write_text(
            json.dumps({"entries": entries}), encoding="utf-8"
        )
        with patch.object(srq, "REGISTRY_PATH", registry_path):
            # 使用大量重疊詞彙
            result = score_kb_novelty("人工智慧與機器學習的深度學習研究 LLM 大型語言模型", "test_key")
            assert result <= 15  # 有重疊，不應得滿分


# ─── score_result — 完整流程 ─────────────────────────────────────────────────

class TestScoreResult:
    def _make_result_file(self, tmp_path, data, name="todoist-auto-test_task.json"):
        p = tmp_path / name
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def test_successful_scoring(self, tmp_path):
        data = {
            "status": "success",
            "output": "深度研究報告 " * 100 + " https://a.com https://b.org https://c.net",
        }
        path = self._make_result_file(tmp_path, data)
        with patch.object(srq, "REGISTRY_PATH", tmp_path / "no-registry.json"):
            record = score_result(path)

        assert record["task_key"] == "test_task"
        assert record["score"] > 0
        assert "dimensions" in record
        assert "timestamp" in record

    def test_placeholder_status_skipped(self, tmp_path):
        for status in ("running", "incomplete", "error", "failed"):
            data = {"status": status, "output": "x" * 1000}
            path = self._make_result_file(tmp_path, data, f"todoist-auto-skip_{status}.json")
            record = score_result(path)
            assert record == {}

    def test_nonexistent_file_returns_empty(self, tmp_path):
        record = score_result(tmp_path / "nonexistent.json")
        assert record == {}

    def test_low_score_triggers_alert(self, tmp_path):
        data = {"status": "success", "output": "短"}  # 極短輸出，無來源
        path = self._make_result_file(tmp_path, data)
        with patch.object(srq, "REGISTRY_PATH", tmp_path / "no-registry.json"):
            record = score_result(path)

        assert record["alert"] is True
        assert record["score"] < LOW_SCORE_THRESHOLD

    def test_task_key_extracted_from_filename(self, tmp_path):
        data = {"status": "success", "output": "content " * 50}
        path = self._make_result_file(tmp_path, data, "todoist-auto-shurangama.json")
        with patch.object(srq, "REGISTRY_PATH", tmp_path / "no-registry.json"):
            record = score_result(path)

        assert record["task_key"] == "shurangama"


# ─── update_quality_file ─────────────────────────────────────────────────────

class TestUpdateQualityFile:
    def test_creates_new_quality_file(self, tmp_path):
        quality_path = tmp_path / "research-quality.json"
        record = {
            "task_key": "test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": 75,
            "dimensions": {},
        }
        with patch.object(srq, "QUALITY_PATH", quality_path):
            result = update_quality_file(record)

        assert quality_path.exists()
        assert result["summary"]["test"]["avg"] == 75.0
        assert result["summary"]["test"]["count"] == 1

    def test_appends_to_existing(self, tmp_path):
        quality_path = tmp_path / "research-quality.json"
        now = datetime.now(timezone.utc).isoformat()
        existing = {
            "entries": [{"task_key": "test", "timestamp": now, "score": 60}],
        }
        quality_path.write_text(json.dumps(existing), encoding="utf-8")

        record = {"task_key": "test", "timestamp": now, "score": 80, "dimensions": {}}
        with patch.object(srq, "QUALITY_PATH", quality_path):
            result = update_quality_file(record)

        assert result["summary"]["test"]["count"] == 2
        assert result["summary"]["test"]["avg"] == 70.0

    def test_rolling_window_removes_old_entries(self, tmp_path):
        quality_path = tmp_path / "research-quality.json"
        old_ts = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        recent_ts = datetime.now(timezone.utc).isoformat()
        existing = {
            "entries": [
                {"task_key": "old", "timestamp": old_ts, "score": 50},
                {"task_key": "recent", "timestamp": recent_ts, "score": 90},
            ],
        }
        quality_path.write_text(json.dumps(existing), encoding="utf-8")

        record = {"task_key": "new", "timestamp": recent_ts, "score": 85, "dimensions": {}}
        with patch.object(srq, "QUALITY_PATH", quality_path):
            result = update_quality_file(record)

        # old entry should be removed (>30 days)
        task_keys = [e["task_key"] for e in result["entries"]]
        assert "old" not in task_keys
        assert "recent" in task_keys
        assert "new" in task_keys
