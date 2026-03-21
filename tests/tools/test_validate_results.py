#!/usr/bin/env python3
"""tests/tools/test_validate_results.py — validate_results.py 測試"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 確保 tools/ 與 hooks/ 在 path 上
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "hooks"))

from tools.validate_results import (  # noqa: E402
    _fallback_validate,
    find_result_files,
    load_schema,
    validate_file,
)


# ── Schema 載入 ───────────────────────────────────────────────


class TestLoadSchema:
    def test_loads_existing_schema(self):
        schema = load_schema()
        # 若 schema 存在，應包含 required 欄位
        if schema:
            assert "required" in schema
            assert "task_key" in schema["required"]

    def test_returns_empty_dict_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "tools.validate_results.SCHEMA_PATH", tmp_path / "nonexistent.json"
        )
        assert load_schema() == {}


# ── 檔案驗證 ──────────────────────────────────────────────────


class TestValidateFile:
    def test_valid_result_passes(self, tmp_path):
        data = {
            "agent": "todoist-auto-test_task",
            "task_key": "test_task",
            "status": "success",
            "summary": "測試通過",
        }
        f = tmp_path / "todoist-auto-test_task.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        schema = json.loads(
            (REPO_ROOT / "config/schemas/results-auto-task-schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = validate_file(f, schema)
        assert errors == []

    def test_missing_required_field_fails(self, tmp_path):
        data = {"agent": "todoist-auto-test_task"}  # 缺少 task_key, status
        f = tmp_path / "bad.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        schema = {"required": ["task_key", "status"]}
        errors = validate_file(f, schema)
        assert len(errors) > 0

    def test_invalid_json_returns_error(self, tmp_path):
        f = tmp_path / "broken.json"
        f.write_text("{invalid", encoding="utf-8")
        errors = validate_file(f, {"required": ["status"]})
        assert any("JSON" in e for e in errors)

    def test_empty_schema_passes_all(self, tmp_path):
        f = tmp_path / "any.json"
        f.write_text('{"foo": 1}', encoding="utf-8")
        assert validate_file(f, {}) == []


# ── Fallback 驗證 ────────────────────────────────────────────


class TestFallbackValidate:
    def test_all_required_present(self):
        schema = {"required": ["status", "task_key"]}
        data = {"status": "success", "task_key": "x"}
        assert _fallback_validate(data, schema) == []

    def test_missing_required_fields(self):
        schema = {"required": ["status", "task_key", "agent"]}
        data = {"status": "success"}
        errors = _fallback_validate(data, schema)
        assert len(errors) == 2
        assert any("task_key" in e for e in errors)
        assert any("agent" in e for e in errors)

    def test_empty_schema(self):
        assert _fallback_validate({"a": 1}, {}) == []


# ── 檔案搜尋 ─────────────────────────────────────────────────


class TestFindResultFiles:
    def test_returns_empty_for_nonexistent_dir(self, monkeypatch):
        monkeypatch.setattr(
            "tools.validate_results.RESULTS_DIR", Path("/nonexistent_dir_xyz")
        )
        assert find_result_files(None) == []

    def test_finds_files_in_dir(self, tmp_path):
        (tmp_path / "todoist-auto-foo.json").write_text("{}", encoding="utf-8")
        (tmp_path / "todoist-auto-bar.json").write_text("{}", encoding="utf-8")
        (tmp_path / "other.json").write_text("{}", encoding="utf-8")
        files = find_result_files(str(tmp_path))
        assert len(files) == 2

    def test_single_file_target(self, tmp_path):
        f = tmp_path / "single.json"
        f.write_text("{}", encoding="utf-8")
        files = find_result_files(str(f))
        assert len(files) == 1
        assert files[0] == f

    def test_nonexistent_single_file(self):
        assert find_result_files("/no/such/file.json") == []
