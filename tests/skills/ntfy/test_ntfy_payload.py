"""Tests for NtfyPayload — 通知酬載構建與驗證。"""
import json

import pytest
from ntfy_client import NtfyPayload


class TestNtfyPayloadToDict:
    """Tests for NtfyPayload.to_dict()."""

    def test_to_dict_basic_fields(self):
        """to_dict should include required fields."""
        payload = NtfyPayload(title="Test", message="Hello", topic="mytopic")
        d = payload.to_dict()
        assert d["title"] == "Test"
        assert d["message"] == "Hello"
        assert d["topic"] == "mytopic"
        assert d["priority"] == 3

    def test_to_dict_with_tags(self):
        """to_dict should include tags when non-empty."""
        payload = NtfyPayload(title="T", message="M", tags=["warning", "robot"])
        d = payload.to_dict()
        assert d["tags"] == ["warning", "robot"]

    def test_to_dict_no_tags_key_when_empty(self):
        """to_dict should omit tags key when tags list is empty."""
        payload = NtfyPayload(title="T", message="M", tags=[])
        d = payload.to_dict()
        assert "tags" not in d

    def test_to_dict_custom_priority(self):
        """to_dict should reflect custom priority."""
        payload = NtfyPayload(title="T", message="M", priority=5)
        assert payload.to_dict()["priority"] == 5


class TestNtfyPayloadToJson:
    """Tests for NtfyPayload.to_json()."""

    def test_to_json_is_valid_json(self):
        """to_json should produce parseable JSON."""
        payload = NtfyPayload(title="T", message="M")
        parsed = json.loads(payload.to_json())
        assert parsed["title"] == "T"

    def test_to_json_preserves_chinese(self):
        """to_json should preserve Chinese characters without escaping."""
        payload = NtfyPayload(title="✅ 任務完成", message="摘要組裝成功")
        json_str = payload.to_json()
        assert "任務完成" in json_str  # ensure_ascii=False
        assert "摘要組裝成功" in json_str


class TestNtfyPayloadValidation:
    """Tests for NtfyPayload.validate()."""

    def test_valid_payload_returns_no_errors(self):
        """Valid payload should pass validation."""
        payload = NtfyPayload(title="Valid Title", message="Valid message", priority=3)
        assert payload.validate() == []
        assert payload.is_valid() is True

    def test_empty_title_fails(self):
        """Empty title should fail validation."""
        payload = NtfyPayload(title="", message="OK", priority=3)
        errors = payload.validate()
        assert any("title" in e for e in errors)

    def test_whitespace_only_title_fails(self):
        """Whitespace-only title should fail validation."""
        payload = NtfyPayload(title="   ", message="OK")
        assert not payload.is_valid()

    def test_title_over_50_chars_fails(self):
        """Title longer than 50 chars should fail validation."""
        long_title = "A" * 51
        payload = NtfyPayload(title=long_title, message="OK")
        errors = payload.validate()
        assert any("50" in e for e in errors)

    def test_title_exactly_50_chars_passes(self):
        """Title of exactly 50 chars should pass."""
        payload = NtfyPayload(title="A" * 50, message="OK")
        assert payload.is_valid()

    def test_empty_message_fails(self):
        """Empty message should fail validation."""
        payload = NtfyPayload(title="T", message="")
        errors = payload.validate()
        assert any("message" in e for e in errors)

    def test_priority_out_of_range_fails(self):
        """Priority outside 1-5 should fail."""
        for bad_priority in (0, 6, -1, 10):
            payload = NtfyPayload(title="T", message="M", priority=bad_priority)
            errors = payload.validate()
            assert any("priority" in e for e in errors), f"priority={bad_priority} should fail"

    def test_priority_boundaries_pass(self):
        """Priority 1 and 5 should pass validation."""
        for p in (1, 2, 3, 4, 5):
            payload = NtfyPayload(title="T", message="M", priority=p)
            assert payload.is_valid(), f"priority={p} should be valid"

    def test_empty_topic_fails(self):
        """Empty topic should fail validation."""
        payload = NtfyPayload(title="T", message="M", topic="")
        errors = payload.validate()
        assert any("topic" in e for e in errors)
