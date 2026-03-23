"""tests/tools/test_collect_system_data.py — collect_system_data.py 單元測試"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import collect_system_data as csd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_dirs(tmp_path):
    """建立模擬目錄結構。"""
    logs = tmp_path / "logs" / "structured"
    logs.mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    context = tmp_path / "context"
    context.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    tmp_out = tmp_path / "tmp"
    tmp_out.mkdir()
    return {
        "logs": logs, "state": state,
        "context": context, "config": config,
        "base": tmp_path, "tmp": tmp_out,
    }


# ---------------------------------------------------------------------------
# collect_jsonl_stats
# ---------------------------------------------------------------------------


class TestCollectJsonlStats:
    """測試 JSONL 日誌統計。"""

    def test_empty_logs_dir(self, mock_dirs):
        with patch.object(csd, "LOGS_DIR", mock_dirs["logs"]):
            stats = csd.collect_jsonl_stats()
        assert stats["total_calls"] == 0
        assert stats["data_available"] is False

    def test_basic_stats(self, mock_dirs):
        today = datetime.now()
        log_file = mock_dirs["logs"] / f"{today.strftime('%Y-%m-%d')}.jsonl"
        records = [
            {"tool": "Bash", "tags": ["info"], "output_len": 500},
            {"tool": "Read", "tags": ["skill-read"],
             "summary": "Read D:/Source/daily-digest-prompt/skills/todoist/SKILL.md", "output_len": 1000},
            {"tool": "Bash", "tags": ["blocked"], "event": "blocked", "output_len": 0},
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        with patch.object(csd, "LOGS_DIR", mock_dirs["logs"]), \
             patch.object(csd, "START_DATE", today - timedelta(days=1)), \
             patch.object(csd, "END_DATE", today + timedelta(days=1)):
            stats = csd.collect_jsonl_stats()

        assert stats["data_available"] is True
        assert stats["total_calls"] == 3
        assert stats["blocked_count"] == 1
        assert stats["block_rate"] == round(1 / 3, 4)
        assert stats["tool_distribution"]["Bash"] == 2
        assert stats["tool_distribution"]["Read"] == 1
        assert "todoist" in stats["unique_skills"]
        assert stats["skill_count"] == 1

    def test_research_exclusion(self, mock_dirs):
        """研究類任務的 output_len 不計入 avg_output_len。"""
        today = datetime.now()
        log_file = mock_dirs["logs"] / f"{today.strftime('%Y-%m-%d')}.jsonl"
        records = [
            {"tool": "Bash", "tags": ["info"], "output_len": 100,
             "cause_chain": {"task_key": "normal_task"}},
            {"tool": "Bash", "tags": ["info"], "output_len": 50000,
             "cause_chain": {"task_key": "ai_deep_research"}},
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        with patch.object(csd, "LOGS_DIR", mock_dirs["logs"]), \
             patch.object(csd, "RESEARCH_EXCLUDE_KEYS",
                          {"ai_deep_research", "tech_research"}), \
             patch.object(csd, "START_DATE", today - timedelta(days=1)), \
             patch.object(csd, "END_DATE", today + timedelta(days=1)):
            stats = csd.collect_jsonl_stats()

        assert stats["avg_output_len"] == 100  # 只計 normal_task
        assert stats["excluded_research_calls"] == 1

    def test_malformed_json_skipped(self, mock_dirs):
        today = datetime.now()
        log_file = mock_dirs["logs"] / f"{today.strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("not json\n")
            f.write(json.dumps({"tool": "X", "tags": ["info"]}) + "\n")

        with patch.object(csd, "LOGS_DIR", mock_dirs["logs"]), \
             patch.object(csd, "START_DATE", today - timedelta(days=1)), \
             patch.object(csd, "END_DATE", today + timedelta(days=1)):
            stats = csd.collect_jsonl_stats()

        assert stats["total_calls"] == 1


# ---------------------------------------------------------------------------
# collect_scheduler_stats
# ---------------------------------------------------------------------------


class TestCollectSchedulerStats:
    """測試 scheduler-state.json 統計。"""

    def test_missing_file(self, mock_dirs):
        with patch.object(csd, "STATE_DIR", mock_dirs["state"]):
            stats = csd.collect_scheduler_stats()
        assert stats["data_available"] is False
        assert stats["total_runs"] == 0

    def test_basic_scheduler_stats(self, mock_dirs):
        now = datetime.now()
        runs = [
            {"timestamp": (now - timedelta(hours=i)).isoformat(),
             "sections": {"phase1": "success", "phase2": "success"}}
            for i in range(3)
        ]
        # 加一個失敗的
        runs.append({
            "timestamp": (now - timedelta(hours=4)).isoformat(),
            "sections": {"phase1": "success", "phase2": "failed"},
        })
        state_file = mock_dirs["state"] / "scheduler-state.json"
        state_file.write_text(json.dumps({"runs": runs}), encoding="utf-8")

        with patch.object(csd, "STATE_DIR", mock_dirs["state"]), \
             patch.object(csd, "START_DATE", now - timedelta(days=7)), \
             patch.object(csd, "END_DATE", now + timedelta(days=1)):
            stats = csd.collect_scheduler_stats()

        assert stats["data_available"] is True
        assert stats["total_runs"] == 4
        assert stats["success_count"] == 3
        assert stats["failed_count"] == 1
        assert stats["success_rate"] == 0.75

    def test_empty_sections_counted_as_failure(self, mock_dirs):
        now = datetime.now()
        runs = [{"timestamp": now.isoformat(), "sections": {}}]
        state_file = mock_dirs["state"] / "scheduler-state.json"
        state_file.write_text(json.dumps({"runs": runs}), encoding="utf-8")

        with patch.object(csd, "STATE_DIR", mock_dirs["state"]), \
             patch.object(csd, "START_DATE", now - timedelta(days=1)), \
             patch.object(csd, "END_DATE", now + timedelta(days=1)):
            stats = csd.collect_scheduler_stats()

        assert stats["failed_count"] == 1


# ---------------------------------------------------------------------------
# collect_auto_task_stats
# ---------------------------------------------------------------------------


class TestCollectAutoTaskStats:
    """測試自動任務統計。"""

    def test_missing_file(self, mock_dirs):
        with patch.object(csd, "CONTEXT_DIR", mock_dirs["context"]):
            stats = csd.collect_auto_task_stats()
        assert stats["data_available"] is False

    def test_basic_task_stats(self, mock_dirs):
        data = {
            "tech_research_count": 2,
            "ai_deep_research_count": 3,
            "log_audit_count": 1,
            "write_version": 5,  # 不是 _count 欄位，應被忽略
        }
        (mock_dirs["context"] / "auto-tasks-today.json").write_text(
            json.dumps(data), encoding="utf-8")

        with patch.object(csd, "CONTEXT_DIR", mock_dirs["context"]):
            stats = csd.collect_auto_task_stats()

        assert stats["data_available"] is True
        assert stats["task_counts"]["tech_research"] == 2
        assert stats["task_counts"]["ai_deep_research"] == 3
        assert "write" not in stats["task_counts"]
        assert stats["fairness_score"] > 0  # stddev/mean

    def test_single_task_no_fairness(self, mock_dirs):
        """只有 1 個任務時，fairness_score 預設 0。"""
        data = {"log_audit_count": 5}
        (mock_dirs["context"] / "auto-tasks-today.json").write_text(
            json.dumps(data), encoding="utf-8")

        with patch.object(csd, "CONTEXT_DIR", mock_dirs["context"]):
            stats = csd.collect_auto_task_stats()

        assert stats["fairness_score"] == 0.0


# ---------------------------------------------------------------------------
# collect_research_stats
# ---------------------------------------------------------------------------


class TestCollectResearchStats:
    """測試研究註冊表統計。"""

    def test_missing_file(self, mock_dirs):
        with patch.object(csd, "CONTEXT_DIR", mock_dirs["context"]):
            stats = csd.collect_research_stats()
        assert stats["data_available"] is False

    def test_basic_research_stats(self, mock_dirs):
        now = datetime.now()
        entries = [
            {"topic": "AI Agent", "timestamp": now.isoformat()},
            {"topic": "AI Agent", "timestamp": (now - timedelta(days=1)).isoformat()},
            {"topic": "LLM Routing", "timestamp": (now - timedelta(days=2)).isoformat()},
            {"topic": "Old Topic", "timestamp": (now - timedelta(days=30)).isoformat()},
        ]
        (mock_dirs["context"] / "research-registry.json").write_text(
            json.dumps({"entries": entries}), encoding="utf-8")

        with patch.object(csd, "CONTEXT_DIR", mock_dirs["context"]), \
             patch.object(csd, "START_DATE", now - timedelta(days=6)), \
             patch.object(csd, "END_DATE", now + timedelta(days=1)):
            stats = csd.collect_research_stats()

        assert stats["data_available"] is True
        assert stats["unique_topics"] == 3
        assert stats["total_entries"] == 4
        assert stats["recent_topics"] == 3  # 3 within 7 days
        assert 0 < stats["diversity"] <= 1.0


# ---------------------------------------------------------------------------
# collect_behavior_stats
# ---------------------------------------------------------------------------


class TestCollectBehaviorStats:
    """測試行為模式統計。"""

    def test_missing_file(self, mock_dirs):
        with patch.object(csd, "CONTEXT_DIR", mock_dirs["context"]):
            stats = csd.collect_behavior_stats()
        assert stats["data_available"] is False

    def test_basic_behavior_stats(self, mock_dirs):
        data = {
            "patterns": {
                "p1": {"confidence": 0.8, "count": 10},
                "p2": {"confidence": 0.3, "count": 5},
                "p3": {"confidence": 0.6, "count": 8},
            }
        }
        (mock_dirs["context"] / "behavior-patterns.json").write_text(
            json.dumps(data), encoding="utf-8")

        with patch.object(csd, "CONTEXT_DIR", mock_dirs["context"]):
            stats = csd.collect_behavior_stats()

        assert stats["data_available"] is True
        assert stats["pattern_count"] == 3
        assert stats["high_confidence_count"] == 2  # p1(0.8) + p3(0.6)
