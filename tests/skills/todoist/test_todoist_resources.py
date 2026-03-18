"""Tests for TodoistAPI project and label resource methods."""
from unittest.mock import Mock, patch

import pytest
from todoist import TodoistAPI


class TestGetProjects:
    """Tests for get_projects method."""

    @patch("todoist.requests.request")
    def test_get_projects_returns_list(self, mock_request, mock_api_token):
        """get_projects should return list of projects from results field."""
        projects_data = [
            {"id": "proj1", "name": "Work"},
            {"id": "proj2", "name": "Personal"},
        ]
        mock_response = Mock()
        mock_response.text = '{"results": [...]}'
        mock_response.json.return_value = {"results": projects_data}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        projects = api.get_projects()

        assert len(projects) == 2
        assert projects[0]["name"] == "Work"

    @patch("todoist.requests.request")
    def test_get_projects_empty_returns_empty_list(self, mock_request, mock_api_token):
        """get_projects should return empty list when no projects."""
        mock_response = Mock()
        mock_response.text = '{"results": []}'
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        projects = api.get_projects()

        assert projects == []

    @patch("todoist.requests.request")
    def test_get_projects_error_returns_empty(self, mock_request, mock_api_token):
        """get_projects should return empty list on API error."""
        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.json.side_effect = ValueError()
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.get_projects()

        assert result == []


class TestGetProject:
    """Tests for get_project method."""

    @patch("todoist.requests.request")
    def test_get_project_returns_dict(self, mock_request, mock_api_token):
        """get_project should return project dict."""
        mock_response = Mock()
        mock_response.text = '{"id": "proj1", "name": "Work"}'
        mock_response.json.return_value = {"id": "proj1", "name": "Work"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        project = api.get_project("proj1")

        assert project["id"] == "proj1"
        assert project["name"] == "Work"
        call_args = mock_request.call_args
        assert "projects/proj1" in call_args[1]["url"]


class TestCreateProject:
    """Tests for create_project method."""

    @patch("todoist.requests.request")
    def test_create_project_basic(self, mock_request, mock_api_token):
        """create_project should POST project name."""
        mock_response = Mock()
        mock_response.text = '{"id": "new_proj", "name": "New Project"}'
        mock_response.json.return_value = {"id": "new_proj", "name": "New Project"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        project = api.create_project(name="New Project")

        assert project["name"] == "New Project"
        call_args = mock_request.call_args
        assert call_args[1]["json"]["name"] == "New Project"

    @patch("todoist.requests.request")
    def test_create_project_with_color_and_favorite(self, mock_request, mock_api_token):
        """create_project should send color and is_favorite when provided."""
        mock_response = Mock()
        mock_response.text = '{"id": "p1"}'
        mock_response.json.return_value = {"id": "p1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.create_project(name="Fav Project", color="red", is_favorite=True)

        call_args = mock_request.call_args
        data = call_args[1]["json"]
        assert data["color"] == "red"
        assert data["is_favorite"] is True

    @patch("todoist.requests.request")
    def test_create_project_no_optional_fields_by_default(self, mock_request, mock_api_token):
        """create_project should not send optional fields when not provided."""
        mock_response = Mock()
        mock_response.text = '{"id": "p1"}'
        mock_response.json.return_value = {"id": "p1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.create_project(name="Simple")

        call_args = mock_request.call_args
        data = call_args[1]["json"]
        assert "parent_id" not in data
        assert "color" not in data


class TestGetLabels:
    """Tests for get_labels method."""

    @patch("todoist.requests.request")
    def test_get_labels_returns_list(self, mock_request, mock_api_token):
        """get_labels should return list of labels."""
        labels_data = [
            {"id": "lbl1", "name": "work"},
            {"id": "lbl2", "name": "personal"},
        ]
        mock_response = Mock()
        mock_response.text = '{"results": [...]}'
        mock_response.json.return_value = {"results": labels_data}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        labels = api.get_labels()

        assert len(labels) == 2
        assert labels[1]["name"] == "personal"

    @patch("todoist.requests.request")
    def test_get_labels_empty_returns_empty_list(self, mock_request, mock_api_token):
        """get_labels should return empty list when no labels."""
        mock_response = Mock()
        mock_response.text = '{"results": []}'
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        assert api.get_labels() == []


class TestCreateLabel:
    """Tests for create_label method."""

    @patch("todoist.requests.request")
    def test_create_label_basic(self, mock_request, mock_api_token):
        """create_label should POST label name."""
        mock_response = Mock()
        mock_response.text = '{"id": "lbl1", "name": "研究"}'
        mock_response.json.return_value = {"id": "lbl1", "name": "研究"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        label = api.create_label(name="研究")

        assert label["name"] == "研究"
        call_args = mock_request.call_args
        assert call_args[1]["json"]["name"] == "研究"

    @patch("todoist.requests.request")
    def test_create_label_with_color(self, mock_request, mock_api_token):
        """create_label should include color when provided."""
        mock_response = Mock()
        mock_response.text = '{"id": "lbl1"}'
        mock_response.json.return_value = {"id": "lbl1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.create_label(name="urgent", color="red")

        call_args = mock_request.call_args
        assert call_args[1]["json"]["color"] == "red"

    @patch("todoist.requests.request")
    def test_create_label_no_color_by_default(self, mock_request, mock_api_token):
        """create_label should not send color field when not provided."""
        mock_response = Mock()
        mock_response.text = '{"id": "lbl1"}'
        mock_response.json.return_value = {"id": "lbl1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.create_label(name="simple")

        call_args = mock_request.call_args
        assert "color" not in call_args[1]["json"]
