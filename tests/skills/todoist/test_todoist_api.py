"""Tests for TodoistAPI request methods using mocks."""
from unittest.mock import Mock, patch

import pytest
from todoist import TodoistAPI


class TestTodoistAPIInit:
    """Tests for TodoistAPI initialization."""

    def test_init_with_token_param(self):
        """API should accept token as parameter."""
        api = TodoistAPI(api_token="test_token")
        assert api.api_token == "test_token"

    def test_init_with_env_var(self, monkeypatch):
        """API should read token from environment variable."""
        monkeypatch.setenv("TODOIST_API_TOKEN", "env_token")
        api = TodoistAPI()
        assert api.api_token == "env_token"

    def test_init_without_token_raises(self, monkeypatch):
        """API should raise ValueError without token."""
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        with pytest.raises(ValueError):
            TodoistAPI()


class TestGetTasks:
    """Tests for get_tasks method."""

    @patch("todoist.requests.request")
    def test_get_tasks_success(self, mock_request, mock_api_token):
        """Successful API call should return task list from results field."""
        mock_response = Mock()
        mock_response.text = '{"results": [{"id": "1", "content": "Task 1"}], "next_cursor": null}'
        mock_response.json.return_value = {"results": [{"id": "1", "content": "Task 1"}], "next_cursor": None}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        tasks = api.get_tasks()

        assert len(tasks) == 1
        assert tasks[0]["id"] == "1"
        mock_request.assert_called_once()

    @patch("todoist.requests.request")
    def test_get_tasks_with_filter(self, mock_request, mock_api_token):
        """Filter parameter should be passed to API."""
        mock_response = Mock()
        mock_response.text = '{"results": [], "next_cursor": null}'
        mock_response.json.return_value = {"results": [], "next_cursor": None}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.get_tasks(filter_query="today")

        call_args = mock_request.call_args
        assert call_args[1]["params"]["filter"] == "today"


class TestCreateTask:
    """Tests for create_task method."""

    @patch("todoist.requests.request")
    def test_create_task_success(self, mock_request, mock_api_token):
        """Successful task creation should return task object."""
        mock_response = Mock()
        mock_response.text = '{"id": "new_task", "content": "New Task"}'
        mock_response.json.return_value = {"id": "new_task", "content": "New Task"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        task = api.create_task(content="New Task")

        assert task["id"] == "new_task"
        call_args = mock_request.call_args
        assert call_args[1]["json"]["content"] == "New Task"

    @patch("todoist.requests.request")
    def test_create_task_with_all_options(self, mock_request, mock_api_token):
        """Task creation should accept all optional parameters."""
        mock_response = Mock()
        mock_response.text = '{"id": "1"}'
        mock_response.json.return_value = {"id": "1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.create_task(
            content="Task",
            description="Description",
            due_string="tomorrow",
            priority=4,
            labels=["work"]
        )

        call_args = mock_request.call_args
        data = call_args[1]["json"]
        assert data["content"] == "Task"
        assert data["description"] == "Description"
        assert data["due_string"] == "tomorrow"
        assert data["priority"] == 4
        assert data["labels"] == ["work"]


class TestCompleteTask:
    """Tests for complete_task method."""

    @patch("todoist.requests.request")
    def test_complete_task_success(self, mock_request, mock_api_token):
        """Successful completion should return True."""
        mock_response = Mock()
        mock_response.text = ""
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.complete_task("12345")

        assert result is True
        call_args = mock_request.call_args
        assert "12345/close" in call_args[1]["url"]


class TestErrorHandling:
    """Tests for error handling."""

    @patch("todoist.requests.request")
    def test_http_error_returns_empty_list(self, mock_request, mock_api_token, capsys):
        """HTTP errors should return empty list for get_tasks."""
        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.json.side_effect = ValueError()
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.get_tasks()

        assert result == []  # get_tasks returns [] on error

    @patch("todoist.requests.request")
    def test_network_error_returns_empty_list(self, mock_request, mock_api_token, capsys):
        """Network errors should return empty list for get_tasks."""
        from requests.exceptions import ConnectionError

        mock_request.side_effect = ConnectionError("Network error")

        api = TodoistAPI(api_token=mock_api_token)
        result = api.get_tasks()

        assert result == []  # get_tasks returns [] on error
