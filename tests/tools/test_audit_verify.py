"""
tests/tools/test_audit_verify.py — 審計日誌完整性驗證 TDD（P4-D）

覆蓋重點：
  - verify_log_file：正常鏈 / 斷鏈 / 輪轉標記重置 / hash 不符（篡改偵測）
  - verify_log_dir：空目錄 / 多檔案批次
  - _compute_entry_hash：排除 _hash 欄位計算
  - check_mission_alignment：backlog goal_id 統計
"""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.audit_verify import (  # noqa: E402
    _compute_entry_hash,
    check_mission_alignment,
    verify_log_dir,
    verify_log_file,
)


# ─── fixtures ────────────────────────────────────────────────────────────────

def make_valid_chain(tmp_path: Path, n: int = 3) -> Path:
    """建立 n 筆有效鏈式記錄的 JSONL 檔案。"""
    log_file = tmp_path / "test.jsonl"
    prev_hash = ""
    for i in range(n):
        entry = {"event": f"event_{i}", "_prev_hash": prev_hash}
        payload = {k: v for k, v in entry.items() if k != "_hash"}
        entry["_hash"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        prev_hash = entry["_hash"]
    return log_file


# ─── _compute_entry_hash ─────────────────────────────────────────────────────

class TestComputeEntryHash:
    def test_excludes_hash_field(self):
        entry = {"a": 1, "_hash": "should_be_ignored"}
        h = _compute_entry_hash(entry)
        assert len(h) == 16

    def test_same_content_same_hash(self):
        e1 = {"a": 1, "_prev_hash": "", "_hash": "old"}
        e2 = {"a": 1, "_prev_hash": "", "_hash": "different"}
        assert _compute_entry_hash(e1) == _compute_entry_hash(e2)

    def test_different_content_different_hash(self):
        e1 = {"a": 1, "_prev_hash": "x"}
        e2 = {"a": 2, "_prev_hash": "x"}
        assert _compute_entry_hash(e1) != _compute_entry_hash(e2)

    def test_returns_16_char_hex(self):
        h = _compute_entry_hash({"x": 1})
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


# ─── verify_log_file ─────────────────────────────────────────────────────────

class TestVerifyLogFile:
    def test_valid_chain_passes(self, tmp_path):
        log_file = make_valid_chain(tmp_path, n=5)
        result = verify_log_file(log_file)
        assert result["passed"] is True
        assert result["total"] == 5
        assert result["errors"] == []

    def test_tampered_entry_detected(self, tmp_path):
        log_file = make_valid_chain(tmp_path, n=3)
        # 修改第 2 行（行號 2）的內容
        lines = log_file.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[1])
        entry["event"] = "TAMPERED"
        lines[1] = json.dumps(entry, ensure_ascii=False)
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = verify_log_file(log_file)
        assert result["passed"] is False
        assert len(result["errors"]) > 0

    def test_entries_without_hash_skipped(self, tmp_path):
        """舊格式（無 _hash）的記錄跳過驗證，不視為錯誤"""
        log_file = tmp_path / "legacy.jsonl"
        log_file.write_text(
            json.dumps({"event": "old_format", "ts": "2026-01-01"}) + "\n",
            encoding="utf-8",
        )
        result = verify_log_file(log_file)
        assert result["passed"] is True

    def test_rotation_marker_resets_chain(self, tmp_path):
        """輪轉標記後的鏈從新起點開始，不視為斷鏈"""
        log_file = tmp_path / "rotated.jsonl"

        # 寫入兩筆正常記錄
        prev = ""
        for i in range(2):
            e = {"event": f"e{i}", "_prev_hash": prev}
            payload = {k: v for k, v in e.items() if k != "_hash"}
            e["_hash"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()[:16]
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(e) + "\n")
            prev = e["_hash"]

        # 輪轉標記（C3 格式）
        marker = {"_type": "rotation_marker", "_prev_hash": "", "_hash": "rotation001"}
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(marker) + "\n")

        # 新鏈（從 rotation001 開始）
        new_prev = "rotation001"
        e_new = {"event": "after_rotation", "_prev_hash": new_prev}
        payload = {k: v for k, v in e_new.items() if k != "_hash"}
        e_new["_hash"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(e_new) + "\n")

        result = verify_log_file(log_file)
        assert result["rotations"] == 1
        # 不應因輪轉而產生斷鏈錯誤（prev_hash 不符的錯誤）
        chain_errors = [e for e in result["errors"] if "_prev_hash 不符" in e]
        assert len(chain_errors) == 0

    def test_invalid_json_line_counted_as_error(self, tmp_path):
        log_file = tmp_path / "bad.jsonl"
        log_file.write_text("NOT JSON\n", encoding="utf-8")
        result = verify_log_file(log_file)
        assert len(result["errors"]) > 0


# ─── verify_log_dir ──────────────────────────────────────────────────────────

class TestVerifyLogDir:
    def test_nonexistent_dir_returns_all_passed_true(self, tmp_path):
        result = verify_log_dir(tmp_path / "nonexistent")
        assert result["all_passed"] is True
        assert result["files_checked"] == 0

    def test_empty_dir_returns_zero_files(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        result = verify_log_dir(log_dir)
        assert result["files_checked"] == 0
        assert result["all_passed"] is True

    def test_multiple_valid_files(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        for name in ["2026-01-01.jsonl", "2026-01-02.jsonl"]:
            (log_dir / name).write_text(
                json.dumps({"event": "x"}) + "\n", encoding="utf-8"
            )
        result = verify_log_dir(log_dir)
        assert result["files_checked"] == 2
        assert result["all_passed"] is True


# ─── check_mission_alignment ─────────────────────────────────────────────────

class TestCheckMissionAlignment:
    def test_returns_total_items(self, tmp_path):
        backlog = [
            {"id": "BL-001", "title": "test", "goal_id": "G01"},
            {"id": "BL-002", "title": "test2"},  # 無 goal_id
        ]
        with patch("tools.audit_verify.BACKLOG_PATH", tmp_path / "backlog.json"), \
             patch("tools.audit_verify.MISSION_PATH", tmp_path / "mission.yaml"):
            (tmp_path / "backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
            (tmp_path / "mission.yaml").write_text("goals: []", encoding="utf-8")
            result = check_mission_alignment()

        assert result["total_items"] == 2
        assert result["items_with_goal"] == 1
        assert result["items_without_goal"] == 1

    def test_missing_backlog_returns_error(self, tmp_path):
        with patch("tools.audit_verify.BACKLOG_PATH", tmp_path / "missing.json"), \
             patch("tools.audit_verify.MISSION_PATH", tmp_path / "mission.yaml"):
            result = check_mission_alignment()

        assert "error" in result
