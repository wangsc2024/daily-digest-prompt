"""Tests for hooks/query_logs.py - 結構化日誌查詢工具測試。

覆蓋範圍：
- load_entries: JSONL 解析、日期篩選、空行/損壞行處理
- load_session_summaries: session-summary.jsonl 解析、cutoff 過濾
- print_summary: 空資料、工具分布、標籤頻率
- print_cache_audit: API 來源一致性（應與 hook_utils.API_SOURCE_PATTERNS 一致）
- print_sessions: 空資料、格式化輸出
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from query_logs import (
    load_entries,
    load_session_summaries,
    print_summary,
    print_cache_audit,
    print_sessions,
)


class TestLoadEntries:
    """JSONL 日誌載入測試。"""

    def test_load_from_today(self, tmp_path):
        """載入今日的 JSONL 檔案。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{today}.jsonl"
        entries_data = [
            {"ts": "2026-02-25T08:00:00+08:00", "tool": "Bash", "tags": ["api-call"]},
            {"ts": "2026-02-25T08:01:00+08:00", "tool": "Read", "tags": ["skill-read"]},
        ]
        log_file.write_text(
            "\n".join(json.dumps(e) for e in entries_data) + "\n",
            encoding="utf-8"
        )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_entries(1)
        assert len(result) == 2
        assert result[0]["tool"] == "Bash"
        assert result[0]["_date"] == today

    def test_load_multiple_days(self, tmp_path):
        """載入多天的 JSONL 檔案。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        for i in range(3):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            log_file = log_dir / f"{date}.jsonl"
            log_file.write_text(
                json.dumps({"ts": f"day-{i}", "tool": "Bash", "tags": []}) + "\n",
                encoding="utf-8"
            )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_entries(3)
        assert len(result) == 3

    def test_skip_empty_lines(self, tmp_path):
        """跳過空行。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{today}.jsonl"
        log_file.write_text(
            '{"tool": "Bash"}\n\n\n{"tool": "Read"}\n',
            encoding="utf-8"
        )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_entries(1)
        assert len(result) == 2

    def test_skip_corrupted_json_lines(self, tmp_path):
        """跳過損壞的 JSON 行（不中斷）。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{today}.jsonl"
        log_file.write_text(
            '{"tool": "Bash"}\n{invalid json}\n{"tool": "Read"}\n',
            encoding="utf-8"
        )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_entries(1)
        assert len(result) == 2

    def test_no_log_files(self, tmp_path):
        """無日誌檔案時回傳空列表。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_entries(1)
        assert result == []

    def test_nonexistent_log_dir(self, tmp_path):
        """日誌目錄不存在時回傳空列表。"""
        with patch("query_logs.LOG_DIR", str(tmp_path / "nonexistent")):
            result = load_entries(1)
        assert result == []


class TestLoadSessionSummaries:
    """Session 摘要載入測試。"""

    def test_load_recent_sessions(self, tmp_path):
        """載入近期的 session 摘要。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        summary_file = log_dir / "session-summary.jsonl"
        now = datetime.now().astimezone()
        sessions = [
            {"ts": now.isoformat(), "total_calls": 50, "status": "healthy"},
            {"ts": (now - timedelta(hours=2)).isoformat(), "total_calls": 30, "status": "warning"},
        ]
        summary_file.write_text(
            "\n".join(json.dumps(s) for s in sessions) + "\n",
            encoding="utf-8"
        )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_session_summaries(1)
        assert len(result) == 2
        assert result[0]["total_calls"] == 50

    def test_filter_old_sessions(self, tmp_path):
        """過濾超過時限的 session 摘要。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        summary_file = log_dir / "session-summary.jsonl"
        now = datetime.now().astimezone()
        sessions = [
            {"ts": now.isoformat(), "total_calls": 50, "status": "healthy"},
            {"ts": (now - timedelta(days=10)).isoformat(), "total_calls": 30, "status": "old"},
        ]
        summary_file.write_text(
            "\n".join(json.dumps(s) for s in sessions) + "\n",
            encoding="utf-8"
        )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_session_summaries(7)
        assert len(result) == 1
        assert result[0]["status"] == "healthy"

    def test_no_summary_file(self, tmp_path):
        """無 summary 檔案時回傳空列表。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_session_summaries(1)
        assert result == []

    def test_skip_corrupted_lines(self, tmp_path):
        """跳過損壞的 session 記錄行。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        summary_file = log_dir / "session-summary.jsonl"
        now = datetime.now().astimezone()
        summary_file.write_text(
            json.dumps({"ts": now.isoformat(), "status": "ok"}) + "\n{bad}\n",
            encoding="utf-8"
        )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            result = load_session_summaries(1)
        assert len(result) == 1


class TestPrintSummary:
    """print_summary 輸出測試。"""

    def test_empty_entries(self, capsys):
        """空資料應印出提示訊息。"""
        print_summary([], 1)
        output = capsys.readouterr().out
        assert "無結構化日誌" in output

    def test_with_entries(self, capsys):
        """有資料時應印出工具分布和標籤頻率。"""
        entries = [
            {"tool": "Bash", "tags": ["api-call", "todoist"], "has_error": False, "event": "post", "_date": "2026-02-25"},
            {"tool": "Read", "tags": ["skill-read"], "has_error": False, "event": "post", "_date": "2026-02-25"},
            {"tool": "Bash", "tags": ["api-call", "hackernews"], "has_error": True, "event": "post", "_date": "2026-02-25"},
        ]
        print_summary(entries, 1)
        output = capsys.readouterr().out
        assert "工具分布" in output
        assert "Bash" in output
        assert "標籤頻率" in output
        assert "關鍵指標" in output

    def test_blocked_entries_shown(self, capsys):
        """攔截事件應顯示詳情。"""
        entries = [
            {"tool": "Bash", "tags": ["blocked"], "has_error": False, "event": "blocked",
             "reason": "nul redirect blocked", "ts": "2026-02-25T08:00:00", "_date": "2026-02-25"},
        ]
        print_summary(entries, 1)
        output = capsys.readouterr().out
        assert "攔截詳情" in output

    def test_error_entries_shown(self, capsys):
        """錯誤事件應顯示詳情（前 5 筆）。"""
        entries = [
            {"tool": "Bash", "tags": ["error"], "has_error": True, "event": "post",
             "summary": "curl failed with 500", "ts": "2026-02-25T08:00:00", "_date": "2026-02-25"},
        ]
        print_summary(entries, 1)
        output = capsys.readouterr().out
        assert "錯誤詳情" in output


class TestPrintCacheAudit:
    """print_cache_audit 快取審計測試。"""

    def test_cache_audit_sources_match_api_source_patterns(self):
        """快取審計的來源清單應與 hook_utils.API_SOURCE_PATTERNS 一致。"""
        from hook_utils import API_SOURCE_PATTERNS
        # query_logs.py 中 hardcoded 的來源清單
        hardcoded_sources = ["todoist", "pingtung-news", "hackernews", "knowledge", "gmail"]
        api_pattern_keys = list(API_SOURCE_PATTERNS.keys())

        # ntfy 在 API_SOURCE_PATTERNS 中但不在快取審計中（ntfy 不需要快取）
        cacheable_sources = [s for s in api_pattern_keys if s != "ntfy"]
        assert set(hardcoded_sources) == set(cacheable_sources), (
            f"query_logs.py 的來源清單 {hardcoded_sources} 與 "
            f"API_SOURCE_PATTERNS 的可快取來源 {cacheable_sources} 不一致"
        )

    def test_cache_audit_output(self, capsys):
        """快取審計應正確顯示各來源狀態。"""
        entries = [
            {"tool": "Bash", "tags": ["api-call", "todoist"], "event": "post"},
            {"tool": "Read", "tags": ["cache-read", "todoist"], "event": "post"},
        ]
        print_cache_audit(entries)
        output = capsys.readouterr().out
        assert "快取審計" in output
        assert "todoist" in output

    def test_cache_bypass_detection(self, capsys):
        """偵測快取繞過（有 API 呼叫但無快取讀取）。"""
        entries = [
            {"tool": "Bash", "tags": ["api-call", "hackernews"], "event": "post"},
            {"tool": "Bash", "tags": ["api-call", "hackernews"], "event": "post"},
        ]
        print_cache_audit(entries)
        output = capsys.readouterr().out
        # hackernews 有 API 呼叫但無快取讀取 → 應顯示「繞過」
        assert "繞過" in output

    def test_no_activity_status(self, capsys):
        """無活動的來源應顯示「無活動」。"""
        entries = []  # 無任何記錄
        print_cache_audit(entries)
        output = capsys.readouterr().out
        assert "無活動" in output


class TestPrintSessions:
    """print_sessions 輸出測試。"""

    def test_no_sessions(self, capsys, tmp_path):
        """無 session 記錄應印出提示。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        with patch("query_logs.LOG_DIR", str(log_dir)):
            print_sessions(1)
        output = capsys.readouterr().out
        assert "無 session 記錄" in output

    def test_with_sessions(self, capsys, tmp_path):
        """有 session 記錄時應顯示表格。"""
        log_dir = tmp_path / "logs" / "structured"
        log_dir.mkdir(parents=True)
        summary_file = log_dir / "session-summary.jsonl"
        now = datetime.now().astimezone()
        summary_file.write_text(
            json.dumps({
                "ts": now.isoformat(),
                "total_calls": 42,
                "api_calls": 10,
                "cache_reads": 5,
                "blocked": 0,
                "errors": 0,
                "alert_sent": False,
                "status": "healthy",
            }) + "\n",
            encoding="utf-8"
        )
        with patch("query_logs.LOG_DIR", str(log_dir)):
            print_sessions(1)
        output = capsys.readouterr().out
        assert "session 記錄" in output
        assert "healthy" in output
