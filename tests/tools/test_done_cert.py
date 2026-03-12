"""
tests/tools/test_done_cert.py — done_cert TDD（P5-A）

覆蓋重點：
  - issue_cert 簽發（含 hash 計算）
  - verify_done_cert 正常 / 缺失 / hash 不符 / schema 未通過
  - verify_all_certs 批次驗證
  - cleanup_stale_certs 過期清理
  - 串流讀取 _file_hash 大檔案防 OOM
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.agent_pool.done_cert import (  # noqa: E402
    _file_hash,
    cleanup_stale_certs,
    issue_cert,
    verify_all_certs,
    verify_done_cert,
)


# ─── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def cert_dir(tmp_path):
    """隔離的 done-certs 目錄"""
    d = tmp_path / "done-certs"
    d.mkdir()
    return d


@pytest.fixture()
def result_file(tmp_path):
    """假結果 JSON 檔"""
    f = tmp_path / "result.json"
    f.write_text(json.dumps({"status": "ok", "items": [1, 2, 3]}), encoding="utf-8")
    return f


# ─── _file_hash ──────────────────────────────────────────────────────────────

class TestFileHash:
    def test_returns_16_char_hex(self, result_file):
        h = _file_hash(result_file)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("hello", encoding="utf-8")
        assert _file_hash(f1) == _file_hash(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")
        assert _file_hash(f1) != _file_hash(f2)

    def test_large_file_chunked_reading(self, tmp_path):
        """確認大檔案不會 OOM（串流讀取）"""
        large = tmp_path / "large.bin"
        # 256KB — 超過一個 chunk
        large.write_bytes(b"A" * 262144)
        h = _file_hash(large)
        assert len(h) == 16


# ─── issue_cert ──────────────────────────────────────────────────────────────

class TestIssueCert:
    def test_creates_cert_file(self, tmp_path, result_file):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            cert = issue_cert("task-001", 2, "web_search", result_file)

        cert_path = tmp_path / "done-certs" / "task-001.json"
        assert cert_path.exists()
        saved = json.loads(cert_path.read_text(encoding="utf-8"))
        assert saved["task_id"] == "task-001"

    def test_cert_contains_required_fields(self, tmp_path, result_file):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            cert = issue_cert("task-002", 2, "kb_import", result_file)

        assert cert["task_id"] == "task-002"
        assert cert["phase"] == 2
        assert cert["worker_type"] == "kb_import"
        assert cert["schema_valid"] is True
        assert cert["result_hash"] is not None
        assert "issued_at" in cert

    def test_cert_with_schema_invalid(self, tmp_path, result_file):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            cert = issue_cert("task-003", 2, "web_search", result_file, schema_valid=False)

        assert cert["schema_valid"] is False

    def test_nonexistent_result_file_hash_is_none(self, tmp_path):
        nonexistent = tmp_path / "missing.json"
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            cert = issue_cert("task-004", 2, "web_search", nonexistent)

        assert cert["result_hash"] is None


# ─── verify_done_cert ────────────────────────────────────────────────────────

class TestVerifyDoneCert:
    def test_valid_cert_returns_true(self, tmp_path, result_file):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            issue_cert("task-v1", 2, "web_search", result_file)
            ok, reason = verify_done_cert("task-v1")

        assert ok is True
        assert reason == "ok"

    def test_missing_cert_returns_false(self, tmp_path):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            ok, reason = verify_done_cert("nonexistent-task")

        assert ok is False
        assert "不存在" in reason

    def test_schema_invalid_cert_returns_false(self, tmp_path, result_file):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            issue_cert("task-v2", 2, "web_search", result_file, schema_valid=False)
            ok, reason = verify_done_cert("task-v2")

        assert ok is False
        assert "schema" in reason

    def test_missing_result_file_returns_false(self, tmp_path, result_file):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            issue_cert("task-v3", 2, "web_search", result_file)
            result_file.unlink()  # 刪除結果檔案
            ok, reason = verify_done_cert("task-v3")

        assert ok is False
        assert "消失" in reason

    def test_tampered_result_file_returns_false(self, tmp_path, result_file):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "done-certs"):
            issue_cert("task-v4", 2, "web_search", result_file)
            # 篡改結果檔案
            result_file.write_text(json.dumps({"status": "tampered"}), encoding="utf-8")
            ok, reason = verify_done_cert("task-v4")

        assert ok is False
        assert "hash" in reason or "篡改" in reason

    def test_corrupted_cert_json_returns_false(self, tmp_path):
        cert_dir = tmp_path / "done-certs"
        cert_dir.mkdir()
        (cert_dir / "bad-task.json").write_text("NOT VALID JSON", encoding="utf-8")

        with patch("tools.agent_pool.done_cert.CERT_DIR", cert_dir):
            ok, reason = verify_done_cert("bad-task")

        assert ok is False


# ─── verify_all_certs ────────────────────────────────────────────────────────

class TestVerifyAllCerts:
    def test_empty_dir_returns_zero(self, tmp_path):
        cert_dir = tmp_path / "done-certs"
        cert_dir.mkdir()
        with patch("tools.agent_pool.done_cert.CERT_DIR", cert_dir):
            result = verify_all_certs()

        assert result["total"] == 0
        assert result["passed"] == 0

    def test_nonexistent_dir_returns_zero(self, tmp_path):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "none"):
            result = verify_all_certs()
        assert result["total"] == 0

    def test_mixed_valid_invalid_certs(self, tmp_path, result_file):
        cert_dir = tmp_path / "done-certs"
        with patch("tools.agent_pool.done_cert.CERT_DIR", cert_dir):
            issue_cert("valid-1", 2, "web_search", result_file)
            issue_cert("invalid-1", 2, "web_search", result_file, schema_valid=False)
            summary = verify_all_certs()

        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1


# ─── cleanup_stale_certs ─────────────────────────────────────────────────────

class TestCleanupStaleCerts:
    def test_removes_old_certs(self, tmp_path, result_file):
        cert_dir = tmp_path / "done-certs"
        cert_dir.mkdir()

        old_cert = cert_dir / "old-task.json"
        old_cert.write_text("{}", encoding="utf-8")
        # 設定 mtime 為 2 小時前
        old_time = time.time() - 7200
        import os
        os.utime(old_cert, (old_time, old_time))

        with patch("tools.agent_pool.done_cert.CERT_DIR", cert_dir):
            result = cleanup_stale_certs(max_age_hours=1)

        assert "old-task.json" in result["removed"]
        assert not old_cert.exists()

    def test_preserves_fresh_certs(self, tmp_path):
        cert_dir = tmp_path / "done-certs"
        cert_dir.mkdir()

        fresh_cert = cert_dir / "fresh-task.json"
        fresh_cert.write_text("{}", encoding="utf-8")
        # mtime 預設為 now，不需修改

        with patch("tools.agent_pool.done_cert.CERT_DIR", cert_dir):
            result = cleanup_stale_certs(max_age_hours=24)

        assert "fresh-task.json" not in result["removed"]
        assert fresh_cert.exists()

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        with patch("tools.agent_pool.done_cert.CERT_DIR", tmp_path / "none"):
            result = cleanup_stale_certs()
        assert result["removed"] == []
        assert result["errors"] == []
