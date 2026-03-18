"""Tests for TodoistAPI CRUD operations: update, delete, reopen, get_task."""
from unittest.mock import Mock, patch

import pytest
from todoist import TodoistAPI


class TestGetTask:
    """Tests for get_task method."""

    @patch("todoist.requests.request")
    def test_get_task_returns_task_dict(self, mock_request, mock_api_token):
        """get_task should return task dict on success."""
        mock_response = Mock()
        mock_response.text = '{"id": "abc123", "content": "My Task"}'
        mock_response.json.return_value = {"id": "abc123", "content": "My Task"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        task = api.get_task("abc123")

        assert task["id"] == "abc123"
        assert task["content"] == "My Task"
        call_args = mock_request.call_args
        assert "tasks/abc123" in call_args[1]["url"]

    @patch("todoist.requests.request")
    def test_get_task_not_found_returns_none(self, mock_request, mock_api_token):
        """get_task should return None when task not found (HTTP 404)."""
        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.side_effect = ValueError()
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.get_task("nonexistent")

        assert result is None


class TestUpdateTask:
    """Tests for update_task method."""

    @patch("todoist.requests.request")
    def test_update_task_content(self, mock_request, mock_api_token):
        """update_task should POST new content to task endpoint."""
        mock_response = Mock()
        mock_response.text = '{"id": "task1", "content": "Updated Content"}'
        mock_response.json.return_value = {"id": "task1", "content": "Updated Content"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.update_task("task1", content="Updated Content")

        assert result["id"] == "task1"
        call_args = mock_request.call_args
        assert call_args[1]["json"]["content"] == "Updated Content"
        assert "tasks/task1" in call_args[1]["url"]

    @patch("todoist.requests.request")
    def test_update_task_priority(self, mock_request, mock_api_token):
        """update_task should send updated priority."""
        mock_response = Mock()
        mock_response.text = '{"id": "task1", "priority": 4}'
        mock_response.json.return_value = {"id": "task1", "priority": 4}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.update_task("task1", priority=4)

        call_args = mock_request.call_args
        assert call_args[1]["json"]["priority"] == 4

    @patch("todoist.requests.request")
    def test_update_task_labels(self, mock_request, mock_api_token):
        """update_task should send updated labels list."""
        mock_response = Mock()
        mock_response.text = '{"id": "task1"}'
        mock_response.json.return_value = {"id": "task1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.update_task("task1", labels=["work", "urgent"])

        call_args = mock_request.call_args
        assert call_args[1]["json"]["labels"] == ["work", "urgent"]

    @patch("todoist.requests.request")
    def test_update_task_empty_body_sends_no_fields(self, mock_request, mock_api_token):
        """update_task with no arguments should send empty body."""
        mock_response = Mock()
        mock_response.text = '{"id": "task1"}'
        mock_response.json.return_value = {"id": "task1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.update_task("task1")

        call_args = mock_request.call_args
        assert call_args[1]["json"] == {}

    @patch("todoist.requests.request")
    def test_update_task_clears_description(self, mock_request, mock_api_token):
        """update_task with description='' should send empty description."""
        mock_response = Mock()
        mock_response.text = '{"id": "task1"}'
        mock_response.json.return_value = {"id": "task1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.update_task("task1", description="")

        call_args = mock_request.call_args
        # description=None (falsy) is not included; description="" is included
        assert "description" in call_args[1]["json"]


class TestDeleteTask:
    """Tests for delete_task method."""

    @patch("todoist.requests.request")
    def test_delete_task_success(self, mock_request, mock_api_token):
        """delete_task should return True on success."""
        mock_response = Mock()
        mock_response.text = ""
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.delete_task("task1")

        assert result is True
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "DELETE"
        assert "tasks/task1" in call_args[1]["url"]

    @patch("todoist.requests.request")
    def test_delete_task_failure_returns_false(self, mock_request, mock_api_token):
        """delete_task should return False on API error."""
        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.json.side_effect = ValueError()
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.delete_task("task1")

        assert result is False


class TestReopenTask:
    """Tests for reopen_task method."""

    @patch("todoist.requests.request")
    def test_reopen_task_success(self, mock_request, mock_api_token):
        """reopen_task should return True and POST to reopen endpoint."""
        mock_response = Mock()
        mock_response.text = ""
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.reopen_task("task1")

        assert result is True
        call_args = mock_request.call_args
        assert "tasks/task1/reopen" in call_args[1]["url"]

    @patch("todoist.requests.request")
    def test_reopen_task_network_error_returns_false(self, mock_request, mock_api_token):
        """reopen_task should return False on network error."""
        from requests.exceptions import ConnectionError

        mock_request.side_effect = ConnectionError("Network unreachable")

        api = TodoistAPI(api_token=mock_api_token)
        result = api.reopen_task("task1")

        assert result is False
