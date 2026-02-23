"""Tests for hooks/on_stop_alert.py — Session 結束告警邏輯測試。"""
import json
import os
import sys

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from on_stop_alert import (
    analyze_entries,
    build_alert_message,
    read_session_entries,
    write_session_summary,
    _rotate_logs,
)


# --- Fixtures ---

@pytest.fixture
def healthy_entries():
    """健康的日誌記錄（無錯誤、無攔截）。"""
    return [
        {"ts": "2026-02-16T08:00:00+08:00", "sid": "abc123", "tool": "Read",
         "event": "post", "summary": "test.md", "has_error": False, "tags": ["skill-read"]},
        {"ts": "2026-02-16T08:00:01+08:00", "sid": "abc123", "tool": "Bash",
         "event": "post", "summary": "curl ...", "has_error": False, "tags": ["api-call", "todoist"]},
        {"ts": "2026-02-16T08:00:02+08:00", "sid": "abc123", "tool": "Read",
         "event": "post", "summary": "cache/todoist.json", "has_error": False, "tags": ["cache-read"]},
    ]


@pytest.fixture
def entries_with_block():
    """含攔截事件的日誌記錄。"""
    return [
        {"ts": "2026-02-16T08:00:00+08:00", "sid": "abc123", "tool": "Bash",
         "event": "blocked", "reason": "禁止 nul 重導向", "summary": "echo > nul",
         "tags": ["blocked", "nul-guard"]},
        {"ts": "2026-02-16T08:00:01+08:00", "sid": "abc123", "tool": "Read",
         "event": "post", "summary": "test.md", "has_error": False, "tags": []},
    ]


@pytest.fixture
def entries_with_errors():
    """含錯誤事件的日誌記錄。"""
    return [
        {"ts": "2026-02-16T08:00:00+08:00", "sid": "abc123", "tool": "Bash",
         "event": "post", "summary": "curl ...", "has_error": True,
         "tags": ["api-call", "error"]},
        {"ts": "2026-02-16T08:00:01+08:00", "sid": "abc123", "tool": "Bash",
         "event": "post", "summary": "curl ...", "has_error": True,
         "tags": ["api-call", "error"]},
    ]


@pytest.fixture
def critical_entries():
    """嚴重告警等級的日誌（攔截 >=3）。"""
    return [
        {"ts": "2026-02-16T08:00:00+08:00", "sid": "abc123", "tool": "Bash",
         "event": "blocked", "reason": "nul redirect", "summary": "cmd1",
         "tags": ["blocked", "nul-guard"]},
        {"ts": "2026-02-16T08:00:01+08:00", "sid": "abc123", "tool": "Bash",
         "event": "blocked", "reason": "nul redirect", "summary": "cmd2",
         "tags": ["blocked", "nul-guard"]},
        {"ts": "2026-02-16T08:00:02+08:00", "sid": "abc123", "tool": "Write",
         "event": "blocked", "reason": "nul file", "summary": "nul",
         "tags": ["blocked", "nul-guard"]},
    ]


# --- Tests ---

class TestAnalyzeEntries:
    """日誌分析邏輯。"""

    def test_healthy_entries(self, healthy_entries):
        analysis = analyze_entries(healthy_entries)
        assert analysis["total_calls"] == 3
        assert analysis["blocked_count"] == 0
        assert analysis["error_count"] == 0
        assert analysis["api_calls"] == 1
        assert analysis["cache_reads"] == 1
        assert analysis["skill_reads"] == 1

    def test_entries_with_blocked(self, entries_with_block):
        analysis = analyze_entries(entries_with_block)
        assert analysis["blocked_count"] == 1
        assert "禁止 nul 重導向" in analysis["block_reasons"]

    def test_entries_with_errors(self, entries_with_errors):
        analysis = analyze_entries(entries_with_errors)
        assert analysis["error_count"] == 2
        assert "Bash" in analysis["error_tools"]
        assert analysis["error_tools"]["Bash"] == 2

    def test_empty_entries(self):
        analysis = analyze_entries([])
        assert analysis["total_calls"] == 0
        assert analysis["blocked_count"] == 0
        assert analysis["error_count"] == 0

    def test_tag_counts(self, healthy_entries):
        analysis = analyze_entries(healthy_entries)
        tag_counts = analysis["tag_counts"]
        assert isinstance(tag_counts, dict)

    def test_sub_agents_counted(self):
        entries = [
            {"ts": "2026-02-16T08:00:00+08:00", "sid": "abc", "tool": "Bash",
             "event": "post", "summary": "claude -p ...", "has_error": False,
             "tags": ["sub-agent"]},
        ]
        analysis = analyze_entries(entries)
        assert analysis["sub_agents"] == 1


class TestBuildAlertMessage:
    """告警訊息建置。"""

    def test_healthy_returns_none(self, healthy_entries):
        analysis = analyze_entries(healthy_entries)
        result = build_alert_message(analysis)
        assert result is None

    def test_warning_on_single_block(self, entries_with_block):
        analysis = analyze_entries(entries_with_block)
        result = build_alert_message(analysis)
        assert result is not None
        severity, title, message = result
        assert severity == "warning"
        assert "警告" in title
        assert "攔截" in message

    def test_warning_on_errors(self, entries_with_errors):
        analysis = analyze_entries(entries_with_errors)
        result = build_alert_message(analysis)
        assert result is not None
        severity, title, message = result
        assert severity == "warning"
        assert "錯誤" in message

    def test_critical_on_3_blocks(self, critical_entries):
        analysis = analyze_entries(critical_entries)
        result = build_alert_message(analysis)
        assert result is not None
        severity, title, message = result
        assert severity == "critical"
        assert "嚴重" in title

    def test_critical_on_5_errors(self):
        entries = [
            {"ts": "2026-02-16T08:00:00+08:00", "sid": "abc", "tool": "Bash",
             "event": "post", "summary": f"cmd{i}", "has_error": True,
             "tags": ["error"]}
            for i in range(5)
        ]
        analysis = analyze_entries(entries)
        result = build_alert_message(analysis)
        severity, _, _ = result
        assert severity == "critical"

    def test_message_contains_stats(self, entries_with_block):
        analysis = analyze_entries(entries_with_block)
        _, _, message = build_alert_message(analysis)
        assert "工具呼叫:" in message
        assert "攔截:" in message


class TestReadSessionEntries:
    """Session 隔離的日誌讀取。"""

    def test_reads_matching_session(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)

        entries = [
            {"ts": "2026-02-16T08:00:00", "sid": "abc123abc1", "tool": "Read",
             "event": "post", "tags": []},
            {"ts": "2026-02-16T08:00:01", "sid": "xyz789xyz7", "tool": "Bash",
             "event": "post", "tags": []},
            {"ts": "2026-02-16T08:00:02", "sid": "abc123abc1", "tool": "Write",
             "event": "post", "tags": []},
        ]
        with open(log_dir / "2026-02-16.jsonl", "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        result = read_session_entries("2026-02-16", "abc123abc1")
        assert len(result) == 2
        assert all(e["sid"] == "abc123abc1" for e in result)

    def test_returns_empty_for_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = read_session_entries("2026-02-16", "abc123")
        assert result == []


class TestWriteSessionSummary:
    """Session 摘要寫入。"""

    def test_writes_summary(self, tmp_path, monkeypatch, healthy_entries):
        monkeypatch.chdir(tmp_path)
        analysis = analyze_entries(healthy_entries)
        write_session_summary(analysis, alert_sent=False, severity="healthy",
                              session_id="test123")

        summary_file = tmp_path / "logs" / "structured" / "session-summary.jsonl"
        assert summary_file.exists()

        with open(summary_file, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["total_calls"] == 3
        assert entry["status"] == "healthy"
        assert entry["alert_sent"] is False
        assert entry["sid"] == "test123"[:12]


class TestRotateLogs:
    """日誌輪替。"""

    def test_removes_old_logs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)

        # 建立一個 10 天前的日誌（應被清除）
        old_file = log_dir / "2026-01-01.jsonl"
        old_file.write_text("{}\n")

        # 建立一個今天的日誌（應保留）
        from datetime import datetime, timedelta
        today_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        today_file.write_text("{}\n")

        _rotate_logs(retention_days=7)

        assert not old_file.exists()
        assert today_file.exists()

    def test_trims_old_session_summaries(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)

        # 使用相對日期確保測試不受執行日期影響
        from datetime import datetime, timedelta
        today = datetime.now()
        old_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        recent_date = today.strftime("%Y-%m-%d")

        summary_file = log_dir / "session-summary.jsonl"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": f"{old_date}T08:00:00+08:00", "status": "healthy"}) + "\n")
            f.write(json.dumps({"ts": f"{recent_date}T08:00:00+08:00", "status": "healthy"}) + "\n")

        _rotate_logs(retention_days=7)

        with open(summary_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        # 舊的應被移除，新的應保留
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["ts"].startswith(recent_date)
