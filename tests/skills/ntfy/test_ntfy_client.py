"""Tests for NtfyClient — 通知 payload 構建與格式化。"""
import pytest
from ntfy_client import NtfyClient, NtfyPayload


class TestNtfyClientInit:
    """Tests for NtfyClient initialization."""

    def test_default_topic(self, monkeypatch):
        """Client should use NTFY_TOPIC env var or default 'wangsc2025'."""
        monkeypatch.delenv("NTFY_TOPIC", raising=False)
        client = NtfyClient()
        assert client.topic == "wangsc2025"

    def test_topic_from_env(self, monkeypatch):
        """Client should read topic from NTFY_TOPIC environment variable."""
        monkeypatch.setenv("NTFY_TOPIC", "my_topic")
        client = NtfyClient()
        assert client.topic == "my_topic"

    def test_explicit_topic_overrides_env(self, monkeypatch):
        """Explicit topic should take precedence over env var."""
        monkeypatch.setenv("NTFY_TOPIC", "env_topic")
        client = NtfyClient(topic="explicit_topic")
        assert client.topic == "explicit_topic"

    def test_notification_url(self):
        """notification_url should return base_url/topic."""
        client = NtfyClient(topic="test_topic", base_url="https://ntfy.sh")
        assert client.notification_url() == "https://ntfy.sh/test_topic"

    def test_base_url_trailing_slash_stripped(self):
        """Trailing slash in base_url should be stripped."""
        client = NtfyClient(topic="t", base_url="https://ntfy.sh/")
        assert client.notification_url() == "https://ntfy.sh/t"


class TestBuildPayload:
    """Tests for NtfyClient.build_payload()."""

    def test_build_payload_basic(self):
        """build_payload should return NtfyPayload with given fields."""
        client = NtfyClient(topic="test")
        payload = client.build_payload("Hello", "World", priority=4)
        assert isinstance(payload, NtfyPayload)
        assert payload.title == "Hello"
        assert payload.message == "World"
        assert payload.priority == 4
        assert payload.topic == "test"

    def test_build_payload_default_priority(self):
        """build_payload should use priority=3 by default."""
        client = NtfyClient(topic="test")
        payload = client.build_payload("T", "M")
        assert payload.priority == 3

    def test_build_payload_with_tags(self):
        """build_payload should pass tags through."""
        client = NtfyClient(topic="test")
        payload = client.build_payload("T", "M", tags=["success", "robot"])
        assert "success" in payload.tags
        assert "robot" in payload.tags

    def test_build_payload_no_tags_by_default(self):
        """build_payload without tags should have empty tags list."""
        client = NtfyClient(topic="test")
        payload = client.build_payload("T", "M")
        assert payload.tags == []


class TestTruncateTitle:
    """Tests for NtfyClient.truncate_title()."""

    def test_short_title_unchanged(self):
        """Title within limit should not be truncated."""
        client = NtfyClient()
        assert client.truncate_title("Short") == "Short"

    def test_exactly_50_chars_unchanged(self):
        """Title of exactly 50 chars should not be truncated."""
        title = "A" * 50
        client = NtfyClient()
        assert client.truncate_title(title) == title

    def test_over_50_chars_truncated(self):
        """Title over 50 chars should be truncated with ellipsis."""
        client = NtfyClient()
        long_title = "A" * 60
        result = client.truncate_title(long_title)
        assert len(result) == 50
        assert result.endswith("…")

    def test_custom_max_len(self):
        """truncate_title should respect custom max_len."""
        client = NtfyClient()
        result = client.truncate_title("Hello World", max_len=5)
        assert len(result) == 5
        assert result.endswith("…")


class TestFormatAgentNotification:
    """Tests for NtfyClient.format_agent_notification()."""

    def test_success_status_emoji(self):
        """Success status should include ✅ emoji."""
        client = NtfyClient(topic="test")
        payload = client.format_agent_notification("todoist", "success", "3 tasks done")
        assert "✅" in payload.title
        assert "success" in payload.tags

    def test_failed_status_emoji_and_priority(self):
        """Failed status should include ❌ and raise priority to 4."""
        client = NtfyClient(topic="test")
        payload = client.format_agent_notification("arch_evolution", "failed", "Timeout")
        assert "❌" in payload.title
        assert payload.priority >= 4

    def test_partial_status_emoji(self):
        """Partial status should include ⚠️ emoji."""
        client = NtfyClient(topic="test")
        payload = client.format_agent_notification("self_heal", "partial", "Some steps failed")
        assert "⚠️" in payload.title

    def test_robot_tag_always_present(self):
        """robot tag should always be present in agent notifications."""
        client = NtfyClient(topic="test")
        payload = client.format_agent_notification("any_agent", "success", "done")
        assert "robot" in payload.tags

    def test_long_agent_name_title_truncated(self):
        """Very long agent name should result in truncated title (≤50 chars)."""
        client = NtfyClient(topic="test")
        long_name = "a" * 60
        payload = client.format_agent_notification(long_name, "success", "done")
        assert len(payload.title) <= 50

    def test_payload_is_valid(self):
        """Generated payload should pass validation."""
        client = NtfyClient(topic="wangsc2025")
        payload = client.format_agent_notification("todoist", "success", "Done")
        assert payload.is_valid(), f"Validation errors: {payload.validate()}"


class TestFormatDailyDigestNotification:
    """Tests for NtfyClient.format_daily_digest_notification()."""

    def test_task_count_in_title(self):
        """Title should include task count."""
        client = NtfyClient(topic="test")
        payload = client.format_daily_digest_notification(5, 3, [])
        assert "5" in payload.title

    def test_completed_count_in_message(self):
        """Message should show completed/total when completed > 0."""
        client = NtfyClient(topic="test")
        payload = client.format_daily_digest_notification(5, 3, [])
        assert "3/5" in payload.message

    def test_headlines_in_message(self):
        """Headlines should appear in message."""
        client = NtfyClient(topic="test")
        payload = client.format_daily_digest_notification(2, 1, ["AI 新聞", "屏東頭條"])
        assert "AI 新聞" in payload.message
        assert "屏東頭條" in payload.message

    def test_max_3_headlines_shown(self):
        """Only first 3 headlines should appear in message."""
        client = NtfyClient(topic="test")
        headlines = ["H1", "H2", "H3", "H4", "H5"]
        payload = client.format_daily_digest_notification(1, 0, headlines)
        assert "H4" not in payload.message
        assert "H5" not in payload.message

    def test_daily_tag_present(self):
        """daily tag should be present."""
        client = NtfyClient(topic="test")
        payload = client.format_daily_digest_notification(1, 0, [])
        assert "daily" in payload.tags
