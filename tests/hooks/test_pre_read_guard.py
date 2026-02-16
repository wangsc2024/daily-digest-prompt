"""Tests for hooks/pre_read_guard.py — Read 路徑攔截。"""
import os
import sys
import pytest

# Add hooks dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "hooks"))

from pre_read_guard import check_read_path, FALLBACK_READ_RULES, _is_within_project


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def rules():
    """Use fallback rules for testing."""
    return FALLBACK_READ_RULES


@pytest.fixture
def project_root(tmp_path):
    """Provide a project root for testing."""
    return str(tmp_path / "project")


# ---------------------------------------------------------------------------
# Sensitive path tests (path_match)
# ---------------------------------------------------------------------------
class TestSensitivePaths:
    """Test path_match rules for sensitive system paths."""

    @pytest.mark.parametrize("path", [
        "C:/Users/user/.ssh/id_rsa",
        "/home/user/.ssh/known_hosts",
        "C:\\Users\\user\\.ssh\\config",
        "C:/Users/user/.gnupg/pubring.kbx",
        "/home/user/.gnupg/secring.gpg",
        "C:/Users/user/.aws/credentials",
        "/home/user/.kube/config",
        "/etc/shadow",
        "/etc/passwd",
    ])
    def test_should_block_outside_project(self, path, rules, project_root):
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is True, f"Should block: {path}"
        assert reason is not None

    @pytest.mark.parametrize("path", [
        "C:/safe/normal_file.txt",
        "/home/user/documents/readme.md",
        "D:/Source/project/config.json",
    ])
    def test_should_allow_safe_paths(self, path, rules, project_root):
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is False, f"Should allow: {path}"

    def test_should_allow_within_project(self, rules, tmp_path):
        """Sensitive-looking paths within project should be allowed."""
        project_root = str(tmp_path / "project")
        os.makedirs(project_root, exist_ok=True)
        # A .env inside the project is still allowed by the Read guard
        # (Write guard blocks creation, not Read)
        path = os.path.join(project_root, "credentials", "test.json")
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is False


# ---------------------------------------------------------------------------
# Sensitive file tests (basename_in)
# ---------------------------------------------------------------------------
class TestSensitiveFiles:
    """Test basename_in rules for sensitive filenames."""

    @pytest.mark.parametrize("path", [
        "C:/Users/user/.env",
        "/home/user/.env.local",
        "C:/external/credentials.json",
        "C:/external/token.json",
        "C:/external/secrets.json",
        "C:/external/.htpasswd",
        "/home/user/id_rsa",
        "/home/user/id_ed25519",
    ])
    def test_should_block_outside_project(self, path, rules, project_root):
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is True, f"Should block: {path}"
        assert "敏感" in reason or "matched" in reason.lower() or "禁止" in reason

    @pytest.mark.parametrize("path", [
        "C:/normal/config.json",
        "C:/normal/settings.yaml",
        "C:/normal/readme.md",
    ])
    def test_should_allow_non_sensitive(self, path, rules, project_root):
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is False

    def test_sensitive_inside_project_allowed(self, rules, tmp_path):
        """Files within the project directory should be readable."""
        project_root = str(tmp_path)
        path = os.path.join(project_root, ".env")
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is False


# ---------------------------------------------------------------------------
# Windows credentials tests
# ---------------------------------------------------------------------------
class TestWindowsCredentials:
    """Test Windows credential path blocking."""

    @pytest.mark.parametrize("path", [
        "C:/Users/user/AppData/Roaming/Microsoft/Credentials/abc123",
        "C:/Users/user/AppData/Roaming/Microsoft/Protect/S-1-5-21",
        "C:/Windows/System32/config/SAM",
    ])
    def test_should_block(self, path, rules, project_root):
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is True, f"Should block: {path}"

    def test_should_allow_normal_appdata(self, rules, project_root):
        path = "C:/Users/user/AppData/Roaming/Some/App/config.json"
        blocked, reason, tag = check_read_path(path, rules, project_root)
        assert blocked is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    """Test edge cases."""

    def test_empty_path(self, rules, project_root):
        blocked, reason, tag = check_read_path("", rules, project_root)
        assert blocked is False

    def test_none_rules(self, project_root):
        # With None rules, should load from YAML or fallback
        # Just ensure it doesn't crash
        blocked, reason, tag = check_read_path(
            "C:/Users/user/.ssh/id_rsa", None, project_root)
        assert blocked is True

    def test_empty_rules_list(self, project_root):
        blocked, reason, tag = check_read_path(
            "C:/Users/user/.ssh/id_rsa", [], project_root)
        assert blocked is False

    def test_guard_tag_returned(self, rules, project_root):
        blocked, reason, tag = check_read_path(
            "C:/Users/user/.ssh/id_rsa", rules, project_root)
        assert tag == "read-guard"

    def test_guard_tag_for_sensitive_file(self, rules, project_root):
        blocked, reason, tag = check_read_path(
            "C:/external/.env", rules, project_root)
        # .env matches path_match rule (.env pattern) first → read-guard
        assert tag in ("read-guard", "secret-read-guard")


# ---------------------------------------------------------------------------
# _is_within_project tests
# ---------------------------------------------------------------------------
class TestIsWithinProject:
    """Test project directory detection."""

    def test_within_project(self, tmp_path):
        project = str(tmp_path / "project")
        os.makedirs(project, exist_ok=True)
        assert _is_within_project(
            os.path.join(project, "file.txt"), project) is True

    def test_outside_project(self, tmp_path):
        project = str(tmp_path / "project")
        outside = str(tmp_path / "other" / "file.txt")
        assert _is_within_project(outside, project) is False

    def test_traversal_attack(self, tmp_path):
        project = str(tmp_path / "project")
        os.makedirs(project, exist_ok=True)
        attack_path = os.path.join(project, "..", "other", "secret.txt")
        assert _is_within_project(attack_path, project) is False


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------
class TestFallbackBehavior:
    """Test that fallback rules cover same cases as YAML rules."""

    @pytest.mark.parametrize("path,expected_blocked", [
        ("/home/user/.ssh/id_rsa", True),
        ("/home/user/.gnupg/key", True),
        ("/etc/shadow", True),
        ("/etc/passwd", True),
        ("C:/external/.env", True),
        ("C:/external/credentials.json", True),
        ("C:/external/token.json", True),
        ("C:/normal/readme.md", False),
        ("C:/normal/config.json", False),
    ])
    def test_fallback_matches_yaml(self, path, expected_blocked, project_root):
        blocked, _, _ = check_read_path(
            path, FALLBACK_READ_RULES, project_root)
        assert blocked == expected_blocked
