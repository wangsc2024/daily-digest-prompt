"""
tests/tools/test_validate_relay.py — P4-B Structured Generation 驗證

覆蓋重點：
  - validate_relay_response：summarize/translate 純字串包裝
  - classify：合法 JSON / 缺欄位 / 非 JSON → SchemaViolationError
  - extract：合法 JSON / 缺 extracted 欄位 → SchemaViolationError
  - _validate_schema：必填欄位檢查
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.llm_router import validate_relay_response, _validate_schema, SchemaViolationError  # noqa: E402


# ─── validate_relay_response — summarize / translate（純字串）──────────────

class TestSummarizeTranslatePaths:
    @pytest.mark.parametrize("mode", ["summarize", "translate"])
    def test_string_result_wrapped(self, mode):
        result = validate_relay_response(mode, "這是摘要文字")
        assert result == {"result": "這是摘要文字"}

    @pytest.mark.parametrize("mode", ["summarize", "translate"])
    def test_dict_result_wrapped(self, mode):
        result = validate_relay_response(mode, {"some": "dict"})
        assert result == {"result": {"some": "dict"}}

    def test_unknown_mode_treated_as_string(self):
        result = validate_relay_response("unknown_mode", "output")
        assert result == {"result": "output"}


# ─── validate_relay_response — classify ──────────────────────────────────────

class TestClassifyMode:
    def test_valid_classify_json_string(self):
        raw = json.dumps({"labels": ["AI", "技術"], "confidence": 0.9})
        result = validate_relay_response("classify", raw)
        assert result == {"labels": ["AI", "技術"], "confidence": 0.9}

    def test_valid_classify_dict(self):
        data = {"labels": ["新聞"], "confidence": 0.8}
        result = validate_relay_response("classify", data)
        assert result["labels"] == ["新聞"]

    def test_classify_missing_labels_raises_schema_violation(self):
        raw = json.dumps({"confidence": 0.9})  # 缺少 labels
        with pytest.raises(SchemaViolationError, match="classify"):
            validate_relay_response("classify", raw)

    def test_classify_non_json_string_raises_schema_violation(self):
        with pytest.raises(SchemaViolationError) as exc_info:
            validate_relay_response("classify", "NOT JSON AT ALL")
        assert exc_info.value.mode == "classify"
        assert exc_info.value.raw_result == "NOT JSON AT ALL"

    def test_classify_non_dict_json_raises_schema_violation(self):
        with pytest.raises(SchemaViolationError):
            validate_relay_response("classify", json.dumps([1, 2, 3]))


# ─── validate_relay_response — extract ───────────────────────────────────────

class TestExtractMode:
    def test_valid_extract_json(self):
        raw = json.dumps({"extracted": {"name": "Claude", "version": "3"}})
        result = validate_relay_response("extract", raw)
        assert result["extracted"]["name"] == "Claude"

    def test_extract_missing_extracted_raises_schema_violation(self):
        raw = json.dumps({"data": "something"})  # 缺少 extracted
        with pytest.raises(SchemaViolationError) as exc_info:
            validate_relay_response("extract", raw)
        assert exc_info.value.mode == "extract"

    def test_extract_non_json_raises_schema_violation(self):
        with pytest.raises(SchemaViolationError):
            validate_relay_response("extract", "plain text")


# ─── _validate_schema ────────────────────────────────────────────────────────

class TestValidateSchema:
    def test_all_required_fields_present_passes(self):
        schema = {"required": ["a", "b"]}
        _validate_schema({"a": 1, "b": 2}, schema)  # 不拋例外

    def test_missing_field_raises_value_error(self):
        schema = {"required": ["a", "b"]}
        with pytest.raises(ValueError, match="b"):
            _validate_schema({"a": 1}, schema)

    def test_non_dict_raises_type_error(self):
        with pytest.raises(TypeError):
            _validate_schema([1, 2, 3], {"required": ["a"]})

    def test_no_required_field_always_passes(self):
        _validate_schema({}, {"required": []})
        _validate_schema({}, {})
