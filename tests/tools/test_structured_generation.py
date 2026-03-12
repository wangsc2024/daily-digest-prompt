"""
tests/tools/test_structured_generation.py — Structured Generation（P4-B）TDD

覆蓋重點（15 個測試）：
  - validate_relay_response：
      - summarize / translate：純字串直接包裝，不驗證 schema
      - classify：有效 JSON（含 labels）、缺少 labels → schema_violation
      - extract：有效 JSON（含 extracted）、缺少 extracted → schema_violation
      - 非 JSON 字串 → schema_violation
      - dict 直接傳入（非字串）
  - _validate_schema：
      - 必填欄位缺失報錯、非 dict 報錯
  - llm_classifier.py 的 classify_with_retry 邏輯（透過 mock）
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, call

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.llm_router import validate_relay_response, _validate_schema, SchemaViolationError  # noqa: E402


# ── validate_relay_response ────────────────────────────────────────────────────

class TestValidateRelayResponseSummarize:
    def test_summarize_string_wrapped(self):
        result = validate_relay_response("summarize", "一句話摘要")
        assert result == {"result": "一句話摘要"}

    def test_translate_string_wrapped(self):
        result = validate_relay_response("translate", "The quick brown fox")
        assert result == {"result": "The quick brown fox"}

    def test_summarize_no_schema_violation_key(self):
        result = validate_relay_response("summarize", "test")
        assert "schema_violation" not in result

    def test_unknown_mode_treats_as_passthrough(self):
        """未知 mode 不在 schemas 中，當作 summarize 包裝"""
        result = validate_relay_response("unknown_mode", "raw text")
        assert result == {"result": "raw text"}


class TestValidateRelayResponseClassify:
    def test_valid_classify_json(self):
        raw = json.dumps({"labels": ["AI", "技術"], "confidence": 0.95})
        result = validate_relay_response("classify", raw)
        assert result["labels"] == ["AI", "技術"]
        assert "schema_violation" not in result

    def test_classify_missing_labels_schema_violation(self):
        raw = json.dumps({"confidence": 0.9})  # 缺少 labels
        with pytest.raises(SchemaViolationError, match="classify"):
            validate_relay_response("classify", raw)

    def test_classify_invalid_json_schema_violation(self):
        with pytest.raises(SchemaViolationError):
            validate_relay_response("classify", "not json at all {{{")

    def test_classify_dict_input_valid(self):
        """直接傳 dict（非字串）也應正常處理"""
        raw = {"labels": ["test"], "confidence": 0.8}
        result = validate_relay_response("classify", raw)
        assert result["labels"] == ["test"]

    def test_classify_empty_labels_still_valid(self):
        """labels 欄位存在但為空陣列仍算合法"""
        raw = json.dumps({"labels": []})
        result = validate_relay_response("classify", raw)
        assert "schema_violation" not in result


class TestValidateRelayResponseExtract:
    def test_valid_extract_json(self):
        raw = json.dumps({"extracted": {"title": "test", "score": 9}})
        result = validate_relay_response("extract", raw)
        assert result["extracted"]["title"] == "test"
        assert "schema_violation" not in result

    def test_extract_missing_extracted_schema_violation(self):
        raw = json.dumps({"something_else": "value"})
        with pytest.raises(SchemaViolationError, match="extract"):
            validate_relay_response("extract", raw)

    def test_extract_non_json_schema_violation(self):
        with pytest.raises(SchemaViolationError):
            validate_relay_response("extract", "plain string result")

    def test_extract_mode_key_in_violation(self):
        """SchemaViolationError 應含 mode 屬性供診斷"""
        with pytest.raises(SchemaViolationError) as exc_info:
            validate_relay_response("extract", "invalid")
        assert exc_info.value.mode == "extract"


# ── _validate_schema ──────────────────────────────────────────────────────────

class TestValidateSchema:
    def test_valid_data_no_raise(self):
        schema = {"required": ["labels"]}
        _validate_schema({"labels": ["a"]}, schema)  # 不應拋例外

    def test_missing_required_raises(self):
        schema = {"required": ["labels"]}
        with pytest.raises(ValueError, match="labels"):
            _validate_schema({"confidence": 0.9}, schema)

    def test_non_dict_raises_type_error(self):
        schema = {"required": ["labels"]}
        with pytest.raises(TypeError):
            _validate_schema("not a dict", schema)

    def test_empty_required_always_passes(self):
        schema = {"required": []}
        _validate_schema({}, schema)  # 不應拋例外


# ── classify_with_retry（llm_classifier 邏輯測試）────────────────────────────

class TestClassifyWithRetry:
    """
    透過 mock 測試 llm_classifier.classify_with_retry 的重試邏輯。
    若 llm_classifier 不存在，自動跳過（tools 層選擇性依賴）。
    """

    @pytest.fixture(autouse=True)
    def import_classifier(self):
        try:
            import tools.llm_classifier as mod
            self.mod = mod
        except ImportError:
            pytest.skip("tools.llm_classifier 尚未安裝")

    def test_valid_first_attempt_no_retry(self):
        valid_resp = json.dumps({"task_type": "en_to_zh", "confidence": 0.95})
        with patch.object(self.mod, "_call_groq_classify", return_value=valid_resp) as mock_call:
            result = self.mod.classify_with_retry("翻譯這篇英文", ["en_to_zh", "news_summary"])
        assert result["task_type"] == "en_to_zh"
        assert mock_call.call_count == 1

    def test_invalid_first_attempt_triggers_retry(self):
        bad_resp = "not valid json"
        valid_resp = json.dumps({"task_type": "en_to_zh", "confidence": 0.8})
        responses = [bad_resp, valid_resp]
        with patch.object(self.mod, "_call_groq_classify", side_effect=responses):
            result = self.mod.classify_with_retry("翻譯這篇英文", ["en_to_zh", "news_summary"])
        assert result["task_type"] == "en_to_zh"

    def test_max_retry_exhausted_returns_fallback(self):
        with patch.object(self.mod, "_call_groq_classify", return_value="bad json"):
            result = self.mod.classify_with_retry(
                "unknown input", ["en_to_zh"], max_retries=2
            )
        assert result.get("fallback") is True
        assert result["confidence"] == 0.0
