"""
tests/tools/test_llm_classifier.py — LLM 元分類器 TDD（P3-A）

覆蓋重點：
  - validate_classifier_output：合法 / 缺欄位 / task_type 不在列表 / confidence 範圍
  - build_classifier_prompt：retry 前綴、task_type 列表動態注入
  - classify_with_retry：Groq 可用 / 不可用 / schema 不符觸發重試 / 達到上限降級
  - classify dry_run 模式
"""
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.llm_classifier import (  # noqa: E402
    build_classifier_prompt,
    classify,
    classify_with_retry,
    validate_classifier_output,
)

VALID_TYPES = ["news_summary", "en_to_zh", "research_synthesis", "policy_analysis"]


# ─── validate_classifier_output ──────────────────────────────────────────────

class TestValidateClassifierOutput:
    def test_valid_json_string_passes(self):
        raw = json.dumps({"task_type": "en_to_zh", "confidence": 0.92})
        result = validate_classifier_output(raw, VALID_TYPES)
        assert result["task_type"] == "en_to_zh"
        assert result["confidence"] == pytest.approx(0.92)

    def test_valid_dict_passes(self):
        result = validate_classifier_output(
            {"task_type": "news_summary", "confidence": 0.8}, VALID_TYPES
        )
        assert result["task_type"] == "news_summary"

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="JSON"):
            validate_classifier_output("NOT JSON", VALID_TYPES)

    def test_missing_task_type_raises(self):
        raw = json.dumps({"confidence": 0.9})
        with pytest.raises(ValueError, match="task_type"):
            validate_classifier_output(raw, VALID_TYPES)

    def test_missing_confidence_raises(self):
        raw = json.dumps({"task_type": "en_to_zh"})
        with pytest.raises(ValueError, match="confidence"):
            validate_classifier_output(raw, VALID_TYPES)

    def test_unknown_task_type_raises(self):
        raw = json.dumps({"task_type": "unknown_xyz", "confidence": 0.5})
        with pytest.raises(ValueError, match="不在合法列表"):
            validate_classifier_output(raw, VALID_TYPES)

    def test_confidence_out_of_range_raises(self):
        raw = json.dumps({"task_type": "en_to_zh", "confidence": 1.5})
        with pytest.raises(ValueError, match="confidence"):
            validate_classifier_output(raw, VALID_TYPES)

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            validate_classifier_output(json.dumps([1, 2, 3]), VALID_TYPES)


# ─── build_classifier_prompt ─────────────────────────────────────────────────

class TestBuildClassifierPrompt:
    def test_contains_task_types(self):
        prompt = build_classifier_prompt("翻譯這段文字", VALID_TYPES)
        for t in VALID_TYPES:
            assert t in prompt

    def test_contains_user_input(self):
        prompt = build_classifier_prompt("測試輸入 XYZ", VALID_TYPES)
        assert "測試輸入 XYZ" in prompt

    def test_first_attempt_no_retry_prefix(self):
        prompt = build_classifier_prompt("test", VALID_TYPES, retry_count=0)
        assert "重試" not in prompt

    def test_retry_count_adds_prefix(self):
        prompt = build_classifier_prompt("test", VALID_TYPES, retry_count=1)
        assert "重試 1" in prompt

    def test_prompt_instructs_pure_json(self):
        prompt = build_classifier_prompt("test", VALID_TYPES)
        assert "JSON" in prompt


# ─── classify_with_retry ─────────────────────────────────────────────────────

class TestClassifyWithRetry:
    def test_success_on_first_attempt(self):
        raw_response = json.dumps({"task_type": "en_to_zh", "confidence": 0.9})
        with patch("tools.llm_classifier._call_groq_classify", return_value=raw_response):
            result = classify_with_retry("Translate this", VALID_TYPES)

        assert result["task_type"] == "en_to_zh"
        assert result.get("fallback") is None

    def test_groq_unavailable_returns_fallback(self):
        with patch("tools.llm_classifier._call_groq_classify",
                   side_effect=urllib.error.URLError("refused")):
            result = classify_with_retry("test", VALID_TYPES)

        assert result["task_type"] == "research_synthesis"
        assert result["fallback"] is True
        assert "不可用" in result["error"]

    def test_bad_format_retries_up_to_max(self):
        call_count = {"n": 0}

        def bad_output(*args, **kwargs):
            call_count["n"] += 1
            return "NOT JSON"

        with patch("tools.llm_classifier._call_groq_classify", side_effect=bad_output):
            result = classify_with_retry("test", VALID_TYPES, max_retries=2)

        assert call_count["n"] == 3  # 1 首次 + 2 重試
        assert result["fallback"] is True

    def test_succeeds_on_second_attempt(self):
        attempts = {"n": 0}

        def sometimes_good(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return "INVALID"
            return json.dumps({"task_type": "news_summary", "confidence": 0.7})

        with patch("tools.llm_classifier._call_groq_classify", side_effect=sometimes_good):
            result = classify_with_retry("news article", VALID_TYPES, max_retries=2)

        assert result["task_type"] == "news_summary"
        assert result.get("fallback") is None

    def test_custom_fallback_task_type(self):
        with patch("tools.llm_classifier._call_groq_classify",
                   side_effect=urllib.error.URLError("refused")):
            result = classify_with_retry(
                "test", VALID_TYPES, fallback_task_type="policy_analysis"
            )
        assert result["task_type"] == "policy_analysis"


# ─── classify（主函數）──────────────────────────────────────────────────────

class TestClassify:
    def test_dry_run_returns_dry_run_true(self):
        result = classify("任意輸入", dry_run=True)
        assert result["dry_run"] is True
        assert result["confidence"] == 0.0
        assert "valid_task_types" in result

    def test_dry_run_includes_valid_task_types_from_yaml(self):
        result = classify("test", dry_run=True)
        assert isinstance(result["valid_task_types"], list)
        assert len(result["valid_task_types"]) > 0
