"""Tests for TodoistAPI formatting methods."""
import pytest
from datetime import datetime, timedelta
from todoist import TodoistAPI


class TestFormatTask:
    """Tests for format_task method."""

    def test_format_task_with_high_priority(self, mock_api_token, sample_task, monkeypatch):
        """High priority task should show red emoji."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_task(sample_task)

        assert "🔴" in result  # p1 = priority 4
        assert "測試任務" in result

    def test_format_task_with_low_priority(self, mock_api_token, monkeypatch):
        """Low priority task should show white emoji."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        task = {"content": "低優先級", "priority": 1}

        result = api.format_task(task)

        assert "⚪" in result
        assert "低優先級" in result

    def test_format_task_with_overdue(self, mock_api_token, monkeypatch):
        """Overdue task should show overdue indicator."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        task = {
            "content": "過期任務",
            "priority": 2,
            "due": {"date": yesterday}
        }

        result = api.format_task(task)

        assert "過期" in result

    def test_format_task_with_today_due(self, mock_api_token, monkeypatch):
        """Task due today should show today indicator."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        today = datetime.now().strftime("%Y-%m-%d")
        task = {
            "content": "今日任務",
            "priority": 3,
            "due": {"date": today}
        }

        result = api.format_task(task)

        assert "今日" in result

    def test_format_task_with_labels(self, mock_api_token, monkeypatch):
        """Task with labels should show them."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        task = {
            "content": "有標籤",
            "priority": 1,
            "labels": ["work", "urgent"]
        }

        result = api.format_task(task)

        assert "@work" in result
        assert "@urgent" in result

    def test_format_task_with_id(self, mock_api_token, sample_task, monkeypatch):
        """Task formatted with show_id should include ID."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_task(sample_task, show_id=True)

        assert "[ID:12345]" in result


class TestFormatTasks:
    """Tests for format_tasks method."""

    def test_format_empty_tasks(self, mock_api_token, monkeypatch):
        """Empty task list should return specific message."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks([])

        assert "無任務" in result

    def test_format_tasks_sorted_by_priority(self, mock_api_token, sample_tasks, monkeypatch):
        """Tasks should be sorted by priority (high first)."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks(sample_tasks)
        lines = result.strip().split("\n")

        # First line should be high priority (🔴)
        assert "🔴" in lines[0]


class TestFormatTasksGrouped:
    """Tests for format_tasks_grouped method."""

    def test_format_grouped_empty(self, mock_api_token, monkeypatch):
        """Empty task list should return specific message."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks_grouped([])

        assert "無任務" in result

    def test_format_grouped_shows_priority_headers(self, mock_api_token, sample_tasks, monkeypatch):
        """Grouped format should show priority headers."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks_grouped(sample_tasks)

        assert "P1" in result.upper()  # Should have P1 header
