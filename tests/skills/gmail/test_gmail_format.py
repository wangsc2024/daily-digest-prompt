"""Tests for GmailClient formatting methods."""


class TestFormatMessages:
    """Tests for format_messages static method."""

    def test_format_empty_messages(self):
        """Empty message list should return '無未讀郵件'."""
        # Import here to avoid import errors if google libs not installed
        from skills.gmail.scripts.gmail_client import GmailClient

        result = GmailClient.format_messages([])
        assert result == "無未讀郵件"

    def test_format_single_message(self):
        """Single message should be formatted correctly."""
        from skills.gmail.scripts.gmail_client import GmailClient

        messages = [
            {
                "id": "msg1",
                "from": "John Doe <john@example.com>",
                "subject": "Test Subject",
                "date": "2026-02-12",
                "snippet": "This is a test email snippet",
                "labels": ["INBOX"],
            }
        ]

        result = GmailClient.format_messages(messages)

        assert "1 封未讀郵件" in result
        assert "John Doe" in result
        assert "Test Subject" in result
        assert "This is a test email snippet" in result

    def test_format_important_message(self):
        """Important message should have [重要] prefix."""
        from skills.gmail.scripts.gmail_client import GmailClient

        messages = [
            {
                "id": "msg1",
                "from": "Boss <boss@company.com>",
                "subject": "Urgent Matter",
                "date": "2026-02-12",
                "snippet": "Please respond ASAP",
                "labels": ["INBOX", "IMPORTANT"],
            }
        ]

        result = GmailClient.format_messages(messages)

        assert "[重要]" in result
        assert "Boss" in result

    def test_format_message_without_brackets(self):
        """Message without angle brackets in from should use email prefix."""
        from skills.gmail.scripts.gmail_client import GmailClient

        messages = [
            {
                "id": "msg1",
                "from": "noreply@service.com",
                "subject": "Notification",
                "date": "2026-02-12",
                "snippet": "Your order has shipped",
                "labels": ["INBOX"],
            }
        ]

        result = GmailClient.format_messages(messages)

        assert "noreply" in result
        assert "Notification" in result

    def test_format_multiple_messages(self):
        """Multiple messages should show count correctly."""
        from skills.gmail.scripts.gmail_client import GmailClient

        messages = [
            {
                "id": "msg1",
                "from": "User1 <user1@example.com>",
                "subject": "Subject 1",
                "date": "2026-02-12",
                "snippet": "Snippet 1",
                "labels": ["INBOX"],
            },
            {
                "id": "msg2",
                "from": "User2 <user2@example.com>",
                "subject": "Subject 2",
                "date": "2026-02-12",
                "snippet": "Snippet 2",
                "labels": ["INBOX"],
            },
            {
                "id": "msg3",
                "from": "User3 <user3@example.com>",
                "subject": "Subject 3",
                "date": "2026-02-12",
                "snippet": "Snippet 3",
                "labels": ["INBOX"],
            },
        ]

        result = GmailClient.format_messages(messages)

        assert "3 封未讀郵件" in result
        assert "User1" in result
        assert "User2" in result
        assert "User3" in result

    def test_format_message_with_empty_snippet(self):
        """Message with empty snippet should not cause error."""
        from skills.gmail.scripts.gmail_client import GmailClient

        messages = [
            {
                "id": "msg1",
                "from": "Test <test@example.com>",
                "subject": "No Content",
                "date": "2026-02-12",
                "snippet": "",
                "labels": ["INBOX"],
            }
        ]

        result = GmailClient.format_messages(messages)

        assert "No Content" in result
        # Empty snippet should not appear
        assert "摘要:" not in result or "摘要: ..." not in result

    def test_format_message_with_no_subject(self):
        """Message with missing subject should show default."""
        from skills.gmail.scripts.gmail_client import GmailClient

        messages = [
            {
                "id": "msg1",
                "from": "Test <test@example.com>",
                "subject": "",
                "date": "2026-02-12",
                "snippet": "Some content",
                "labels": ["INBOX"],
            }
        ]

        result = GmailClient.format_messages(messages)

        assert "(無主旨)" in result
