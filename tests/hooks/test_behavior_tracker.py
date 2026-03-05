"""Tests for hooks/behavior_tracker.py — Instinct Lite 行為模式採集器測試。

覆蓋範圍：
  1. _sanitize_summary: 敏感資訊消毒（Auth header/Token header/ENV 變數）
  2. _compute_signature: 簽名穩定性（去除動態部分 UUID/date/timestamp）
  3. track(): 新模式建立、信心遞增、MAX_PATTERNS 溢位淘汰、靜默失敗
  4. _load_patterns / _save_patterns: 檔案 I/O 容錯（JSON 損壞/檔案缺失）
  5. _cleanup_stale: 過期模式清理
  6. report(): CLI 報告輸出
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from behavior_tracker import (
    _sanitize_summary,
    _compute_signature,
    _load_patterns,
    _save_patterns,
    _cleanup_stale,
    track,
    report,
    MAX_PATTERNS,
    DECAY_DAYS,
    CONFIDENCE_INCREMENT,
    CONFIDENCE_MAX,
    CONFIDENCE_INITIAL,
)


# ============================================
# _sanitize_summary 敏感資訊消毒
# ============================================

class TestSanitizeSummary:
    """摘要消毒函數測試。"""

    def test_redact_bearer_token(self):
        """Authorization: Bearer token 應被消毒。"""
        summary = 'curl -H "Authorization: Bearer abc123secret456def" https://api.example.com'
        result = _sanitize_summary(summary)
        assert "abc123secret456def" not in result
        assert "<REDACTED>" in result
        assert "Bearer" in result

    def test_redact_basic_auth(self):
        """Authorization: Basic token 應被消毒。"""
        summary = 'curl -H "Authorization: Basic dXNlcjpwYXNz" https://example.com'
        result = _sanitize_summary(summary)
        assert "dXNlcjpwYXNz" not in result
        assert "<REDACTED>" in result

    def test_redact_x_api_token(self):
        """X-Api-Token header 應被消毒。"""
        summary = 'curl -H "X-Api-Token: my_secret_value" https://api.todoist.com'
        result = _sanitize_summary(summary)
        assert "my_secret_value" not in result
        assert "<REDACTED>" in result

    def test_redact_x_api_key(self):
        """X-Api-Key header 應被消毒。"""
        summary = "curl -H 'X-Api-Key: sk-abc123' https://api.openai.com"
        result = _sanitize_summary(summary)
        assert "sk-abc123" not in result
        assert "<REDACTED>" in result

    def test_redact_x_custom_secret(self):
        """X-Custom-Secret header 應被消毒。"""
        summary = 'curl -H "X-Custom-Secret: very_secret" https://example.com'
        result = _sanitize_summary(summary)
        assert "very_secret" not in result
        assert "<REDACTED>" in result

    def test_redact_env_var_todoist_token(self):
        """$TODOIST_API_TOKEN 環境變數值應被消毒。"""
        summary = "curl -H auth $TODOIST_API_TOKEN abc123xyz789"
        result = _sanitize_summary(summary)
        assert "abc123xyz789" not in result
        assert "<REDACTED>" in result

    def test_redact_env_var_with_equals(self):
        """$SECRET_KEY=value 形式應被消毒。"""
        summary = "$SECRET_KEY=my_secret_value some_command"
        result = _sanitize_summary(summary)
        assert "my_secret_value" not in result
        assert "<REDACTED>" in result

    def test_redact_powershell_env_var(self):
        """$env:API_KEY 形式應被消毒。"""
        summary = "$env:API_KEY sk-abc123def456"
        result = _sanitize_summary(summary)
        assert "sk-abc123def456" not in result
        assert "<REDACTED>" in result

    def test_preserve_non_sensitive_content(self):
        """不含敏感內容的摘要應原樣通過。"""
        summary = "git push origin main --force"
        result = _sanitize_summary(summary)
        assert result == summary

    def test_preserve_url_in_summary(self):
        """URL 結構不應被破壞。"""
        summary = 'curl -H "Authorization: Bearer secret" https://api.todoist.com/api/v1/tasks'
        result = _sanitize_summary(summary)
        assert "https://api.todoist.com/api/v1/tasks" in result

    def test_case_insensitive(self):
        """消毒應不區分大小寫。"""
        summary = 'curl -H "AUTHORIZATION: bearer MyToken" https://example.com'
        result = _sanitize_summary(summary)
        assert "MyToken" not in result

    def test_file_path_not_affected(self):
        """一般檔案路徑不應被影響。"""
        summary = "D:/Source/daily-digest-prompt/skills/SKILL_INDEX.md"
        result = _sanitize_summary(summary)
        assert result == summary

    def test_empty_summary(self):
        """空摘要應回傳空字串。"""
        result = _sanitize_summary("")
        assert result == ""


# ============================================
# _compute_signature 簽名穩定性
# ============================================

class TestComputeSignature:
    """簽名計算函數測試。"""

    def test_uses_sha256(self):
        """簽名應使用 SHA-256（12 位 hex）。"""
        sig = _compute_signature("Bash", "echo hello")
        assert len(sig) == 12
        assert all(c in "0123456789abcdef" for c in sig)

    def test_deterministic(self):
        """相同輸入應產生相同簽名。"""
        sig1 = _compute_signature("Read", "skills/todoist/SKILL.md")
        sig2 = _compute_signature("Read", "skills/todoist/SKILL.md")
        assert sig1 == sig2

    def test_different_tools_different_sigs(self):
        """不同工具的簽名應不同。"""
        sig1 = _compute_signature("Read", "test.json")
        sig2 = _compute_signature("Write", "test.json")
        assert sig1 != sig2

    def test_normalizes_uuid(self):
        """UUID 前綴（8-4 hex 片段）應被正規化為 <uuid>。"""
        sig1 = _compute_signature("Bash", "file-12345678-abcd.json")
        sig2 = _compute_signature("Bash", "file-87654321-ef01.json")
        assert sig1 == sig2

    def test_normalizes_date(self):
        """日期應被正規化。"""
        sig1 = _compute_signature("Bash", "log-2026-03-04.jsonl")
        sig2 = _compute_signature("Bash", "log-2026-02-28.jsonl")
        assert sig1 == sig2

    def test_normalizes_timestamp(self):
        """時間戳應被正規化。"""
        sig1 = _compute_signature("Bash", "task_1709555123456.json")
        sig2 = _compute_signature("Bash", "task_1709555999999.json")
        assert sig1 == sig2

    def test_not_md5(self):
        """確認使用 SHA-256 而非 MD5。"""
        import hashlib
        tool = "Bash"
        summary = "echo hello"
        sig = _compute_signature(tool, summary)
        sha256_sig = hashlib.sha256(f"{tool}:{summary}".encode()).hexdigest()[:12]
        assert sig == sha256_sig

    def test_long_summary_truncated(self):
        """超過 120 字元的摘要在計算前被截斷。"""
        sig1 = _compute_signature("Bash", "x" * 120)
        sig2 = _compute_signature("Bash", "x" * 120 + "extra")
        assert sig1 == sig2


# ============================================
# _load_patterns / _save_patterns I/O 容錯
# ============================================

class TestLoadSavePatterns:
    """模式檔案的讀寫容錯。"""

    def test_load_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        """檔案不存在時應回傳空結構。"""
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", str(tmp_path / "nonexistent.json"))
        data = _load_patterns()
        assert data["version"] == 1
        assert data["patterns"] == {}
        assert data["last_cleanup"] is None

    def test_load_returns_empty_on_corrupt_json(self, tmp_path, monkeypatch):
        """JSON 損壞時應回傳空結構。"""
        corrupt_file = tmp_path / "corrupt.json"
        corrupt_file.write_text("{ invalid json", encoding="utf-8")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", str(corrupt_file))
        data = _load_patterns()
        assert data["version"] == 1
        assert data["patterns"] == {}

    def test_save_and_reload_roundtrip(self, tmp_path, monkeypatch):
        """存檔後重新載入應保持資料一致。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        original = {
            "version": 1,
            "patterns": {"sig1": {"tool": "Bash", "count": 5, "confidence": 0.3}},
            "last_cleanup": "2026-03-04T00:00:00+08:00"
        }
        _save_patterns(original)
        loaded = _load_patterns()
        assert loaded == original

    def test_save_creates_parent_directory(self, tmp_path, monkeypatch):
        """寫入時應自動建立不存在的父目錄。"""
        filepath = str(tmp_path / "sub" / "deep" / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)
        _save_patterns({"version": 1, "patterns": {}, "last_cleanup": None})
        assert os.path.exists(filepath)


# ============================================
# _cleanup_stale 過期模式清理
# ============================================

class TestCleanupStale:
    """過期模式的衰減清理。"""

    def test_removes_expired_patterns(self):
        """超過 DECAY_DAYS 的模式應被移除。"""
        old_date = (datetime.now().astimezone() - timedelta(days=DECAY_DAYS + 1)).isoformat()
        recent_date = datetime.now().astimezone().isoformat()

        data = {
            "version": 1,
            "patterns": {
                "old_sig": {"last_seen": old_date, "count": 1},
                "new_sig": {"last_seen": recent_date, "count": 5},
            },
            "last_cleanup": None
        }
        cleaned = _cleanup_stale(data)
        assert "old_sig" not in cleaned["patterns"]
        assert "new_sig" in cleaned["patterns"]

    def test_preserves_all_recent_patterns(self):
        """所有近期模式應全部保留。"""
        recent = datetime.now().astimezone().isoformat()
        data = {
            "version": 1,
            "patterns": {
                f"sig_{i}": {"last_seen": recent, "count": i}
                for i in range(10)
            },
            "last_cleanup": None
        }
        cleaned = _cleanup_stale(data)
        assert len(cleaned["patterns"]) == 10

    def test_updates_last_cleanup(self):
        """清理後應更新 last_cleanup 時間戳。"""
        data = {"version": 1, "patterns": {}, "last_cleanup": None}
        cleaned = _cleanup_stale(data)
        assert cleaned["last_cleanup"] is not None
        datetime.fromisoformat(cleaned["last_cleanup"])


# ============================================
# track() 核心追蹤邏輯
# ============================================

class TestTrack:
    """track() 函數的完整追蹤行為。"""

    def test_creates_new_pattern(self, tmp_path, monkeypatch):
        """首次觀察到的模式應建立新記錄。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        track("Bash", "curl https://api.todoist.com", ["api-call", "todoist"])

        data = _load_patterns()
        assert len(data["patterns"]) == 1
        pattern = list(data["patterns"].values())[0]
        assert pattern["tool"] == "Bash"
        assert pattern["confidence"] == CONFIDENCE_INITIAL
        assert pattern["count"] == 1
        assert pattern["success_count"] == 1

    def test_increments_confidence_on_repeat(self, tmp_path, monkeypatch):
        """重複觀察應遞增信心分數。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        track("Read", "SKILL_INDEX.md", ["skill-index"])
        track("Read", "SKILL_INDEX.md", ["skill-index"])
        track("Read", "SKILL_INDEX.md", ["skill-index"])

        data = _load_patterns()
        pattern = list(data["patterns"].values())[0]
        assert pattern["count"] == 3
        expected_confidence = CONFIDENCE_INITIAL + CONFIDENCE_INCREMENT * 2
        assert abs(pattern["confidence"] - expected_confidence) < 0.001

    def test_confidence_capped_at_max(self, tmp_path, monkeypatch):
        """信心分數不應超過 CONFIDENCE_MAX。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        for _ in range(30):
            track("Bash", "git status", ["git"])

        data = _load_patterns()
        pattern = list(data["patterns"].values())[0]
        assert pattern["confidence"] <= CONFIDENCE_MAX

    def test_error_tracking(self, tmp_path, monkeypatch):
        """has_error=True 時 success_count 不應遞增。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        track("Bash", "curl https://failing-api.com", ["api-call"], has_error=True)

        data = _load_patterns()
        pattern = list(data["patterns"].values())[0]
        assert pattern["success_count"] == 0
        assert pattern["count"] == 1

    def test_io_tracking(self, tmp_path, monkeypatch):
        """應累積 input_len 和 output_len 統計。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        track("Read", "config.yaml", ["config"], input_len=100, output_len=500)
        track("Read", "config.yaml", ["config"], input_len=80, output_len=400)

        data = _load_patterns()
        pattern = list(data["patterns"].values())[0]
        assert pattern["total_input"] == 180
        assert pattern["total_output"] == 900

    def test_max_patterns_evicts_lowest_confidence(self, tmp_path, monkeypatch):
        """超過 MAX_PATTERNS 時應淘汰信心最低的模式。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)
        monkeypatch.setattr("behavior_tracker.MAX_PATTERNS", 3)

        # 建立 3 個不同模式（滿額）
        track("Bash", "cmd_a unique_alpha", ["tag_a"])
        track("Bash", "cmd_b unique_beta", ["tag_b"])
        track("Bash", "cmd_c unique_gamma", ["tag_c"])

        # 提升 cmd_b 和 cmd_c 的信心
        for _ in range(5):
            track("Bash", "cmd_b unique_beta", ["tag_b"])
            track("Bash", "cmd_c unique_gamma", ["tag_c"])

        # 新增第 4 個模式 — 應淘汰信心最低的 cmd_a
        track("Bash", "cmd_d unique_delta", ["tag_d"])

        data = _load_patterns()
        summaries = [p["summary_sample"] for p in data["patterns"].values()]
        assert not any("cmd_a" in s for s in summaries)
        assert len(data["patterns"]) == 3

    def test_silent_failure_on_exception(self, tmp_path, monkeypatch):
        """任何內部錯誤都不應拋出例外（靜默失敗原則）。"""
        monkeypatch.setattr("behavior_tracker._load_patterns",
                            lambda: (_ for _ in ()).throw(RuntimeError("test")))
        track("Bash", "any command", ["tag"])

    def test_sanitizes_summary_in_storage(self, tmp_path, monkeypatch):
        """儲存的 summary_sample 應已消毒。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        track("Bash", 'curl -H "Authorization: Bearer SECRET123" https://api.todoist.com', ["api-call"])

        data = _load_patterns()
        pattern = list(data["patterns"].values())[0]
        assert "SECRET123" not in pattern["summary_sample"]

    def test_tags_stored_with_dedup_and_limit(self, tmp_path, monkeypatch):
        """tags 應去重且最多 5 個。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        tags = ["api-call", "todoist", "api-call", "todoist", "team-mode", "phase1", "extra1", "extra2"]
        track("Bash", "curl https://api.todoist.com", tags)

        data = _load_patterns()
        pattern = list(data["patterns"].values())[0]
        assert len(pattern["tags"]) <= 5
        assert len(pattern["tags"]) == len(set(pattern["tags"]))

    def test_summary_sample_truncated_to_150(self, tmp_path, monkeypatch):
        """summary_sample 應截斷至 150 字元。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        track("Bash", "x" * 300, ["tag"])

        data = _load_patterns()
        pattern = list(data["patterns"].values())[0]
        assert len(pattern["summary_sample"]) <= 150


# ============================================
# report() CLI 輸出
# ============================================

class TestReport:
    """報告功能的正確輸出。"""

    def test_empty_patterns_message(self, tmp_path, monkeypatch, capsys):
        """無模式時應顯示提示訊息。"""
        filepath = str(tmp_path / "empty.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)
        report()
        captured = capsys.readouterr()
        assert "尚無行為模式記錄" in captured.out

    def test_report_with_data(self, tmp_path, monkeypatch, capsys):
        """有模式時應輸出統計報告。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        data = {
            "version": 1,
            "patterns": {
                "sig1": {
                    "tool": "Bash",
                    "summary_sample": "curl https://api.todoist.com",
                    "tags": ["api-call"],
                    "count": 10,
                    "confidence": 0.6,
                    "success_count": 9,
                    "first_seen": "2026-03-01T00:00:00+08:00",
                    "last_seen": "2026-03-04T00:00:00+08:00",
                    "total_input": 5000,
                    "total_output": 15000,
                },
                "sig2": {
                    "tool": "Read",
                    "summary_sample": "SKILL_INDEX.md",
                    "tags": ["skill-index"],
                    "count": 20,
                    "confidence": 0.8,
                    "success_count": 20,
                    "first_seen": "2026-03-01T00:00:00+08:00",
                    "last_seen": "2026-03-04T00:00:00+08:00",
                    "total_input": 1000,
                    "total_output": 30000,
                },
            },
            "last_cleanup": "2026-03-04T00:00:00+08:00"
        }
        _save_patterns(data)

        report()
        captured = capsys.readouterr()

        assert "共 2 個模式" in captured.out
        assert "高信心模式" in captured.out
        assert "Token 經濟概要" in captured.out
        assert "工具使用分布" in captured.out
        assert "Bash" in captured.out
        assert "Read" in captured.out

    def test_report_no_high_confidence(self, tmp_path, monkeypatch, capsys):
        """全部低信心模式時不應顯示高信心區塊。"""
        filepath = str(tmp_path / "patterns.json")
        monkeypatch.setattr("behavior_tracker.PATTERNS_FILE", filepath)

        data = {
            "version": 1,
            "patterns": {
                "sig1": {
                    "tool": "Bash",
                    "summary_sample": "ls",
                    "tags": [],
                    "count": 1,
                    "confidence": 0.1,
                    "success_count": 1,
                    "first_seen": "2026-03-04T00:00:00+08:00",
                    "last_seen": "2026-03-04T00:00:00+08:00",
                    "total_input": 10,
                    "total_output": 50,
                },
            },
            "last_cleanup": None
        }
        _save_patterns(data)

        report()
        captured = capsys.readouterr()
        assert "共 1 個模式" in captured.out
        assert "高信心模式" not in captured.out


# ============================================
# Constants 常量驗證
# ============================================

class TestConstants:
    """驗證常量值的合理性。"""

    def test_max_patterns_reasonable(self):
        assert 100 <= MAX_PATTERNS <= 10000

    def test_decay_days_reasonable(self):
        assert 7 <= DECAY_DAYS <= 90

    def test_confidence_range(self):
        assert 0 < CONFIDENCE_INITIAL < CONFIDENCE_MAX
        assert CONFIDENCE_MAX == 1.0
        assert CONFIDENCE_INCREMENT > 0

    def test_confidence_reachable(self):
        """INITIAL + 多次 INCREMENT 應能達到 MAX。"""
        steps = int((CONFIDENCE_MAX - CONFIDENCE_INITIAL) / CONFIDENCE_INCREMENT)
        assert steps > 0
        assert steps < 1000
