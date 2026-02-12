"""Pytest fixtures for daily-digest-prompt tests."""
import os
import sys

import pytest

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "skills", "todoist", "scripts"))
sys.path.insert(0, os.path.join(project_root, "skills", "gmail", "scripts"))


@pytest.fixture
def mock_api_token():
    """Provide a mock API token for testing."""
    return "test_token_12345"


@pytest.fixture
def sample_task():
    """Provide a sample Todoist task."""
    return {
        "id": "12345",
        "content": "測試任務",
        "description": "",
        "priority": 4,
        "due": {
            "date": "2026-02-12",
            "string": "today"
        },
        "labels": ["work"]
    }


@pytest.fixture
def sample_tasks(sample_task):
    """Provide a list of sample tasks."""
    return [
        sample_task,
        {
            "id": "12346",
            "content": "低優先級任務",
            "priority": 1,
            "due": None,
            "labels": []
        },
        {
            "id": "12347",
            "content": "中優先級任務",
            "priority": 2,
            "due": {
                "date": "2026-02-20",
                "string": "next week"
            },
            "labels": ["personal"]
        }
    ]
