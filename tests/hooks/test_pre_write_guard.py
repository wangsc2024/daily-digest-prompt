"""Tests for hooks/pre_write_guard.py — 檔案寫入攔截規則測試。"""
import os
import sys

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from pre_write_guard import check_write_path, load_write_rules, FALLBACK_WRITE_RULES


class TestLoadWriteRules:
    """規則載入：YAML 配置與內建 fallback。"""

    def test_load_from_yaml(self):
        """YAML 存在時應載入完整規則。"""
        rules = load_write_rules()
        assert isinstance(rules, list)
        assert len(rules) >= 4
        rule_ids = [r["id"] for r in rules]
        for expected_id in ["nul-file", "scheduler-state", "sensitive-files", "path-traversal"]:
            assert expected_id in rule_ids

    def test_fallback_rules_structure(self):
        """內建 fallback 規則結構完整性。"""
        for rule in FALLBACK_WRITE_RULES:
            assert "id" in rule
            assert "check" in rule
            assert "guard_tag" in rule
            assert "reason" in rule or "reason_template" in rule

    def test_fallback_when_yaml_missing(self, monkeypatch):
        """YAML 不可用時應回退至內建規則。"""
        import hook_utils
        monkeypatch.setattr(hook_utils, "find_config_path", lambda filename="hook-rules.yaml": None)
        rules = load_write_rules()
        assert rules == FALLBACK_WRITE_RULES


class TestNulFile:
    """規則：nul-file — 攔截寫入 nul 檔案。"""

    @pytest.mark.parametrize("path", [
        r"d:\Source\nul",
        "nul",
        "NUL",
        r"D:\temp\NUL",
        r"C:\Users\test\nul",
        r"d:\Source\daily-digest-prompt\nul",
    ])
    def test_should_block(self, path):
        blocked, _, tag = check_write_path(path)
        assert blocked, f"Expected block for: {path}"
        assert tag == "nul-guard"

    @pytest.mark.parametrize("path", [
        r"d:\Source\null.txt",
        r"d:\Source\annul.txt",
        r"d:\Source\file.nul.bak",
        r"d:\Source\nully.txt",
        "normal_file.txt",
    ])
    def test_should_allow(self, path):
        blocked, _, _ = check_write_path(path)
        assert not blocked, f"Should not block: {path}"


class TestSchedulerState:
    """規則：scheduler-state — 攔截寫入 scheduler-state.json。"""

    @pytest.mark.parametrize("path", [
        "state/scheduler-state.json",
        r"d:\Source\daily-digest-prompt\state\scheduler-state.json",
        "scheduler-state.json",
    ])
    def test_should_block(self, path):
        blocked, reason, tag = check_write_path(path)
        assert blocked, f"Expected block for: {path}"
        assert "scheduler-state" in reason
        assert tag == "state-guard"

    @pytest.mark.parametrize("path", [
        "state/other-state.json",
        "scheduler.json",
        "config.json",
    ])
    def test_should_allow(self, path):
        blocked, _, _ = check_write_path(path)
        assert not blocked, f"Should not block: {path}"


class TestSensitiveFiles:
    """規則：sensitive-files — 攔截寫入敏感檔案。"""

    @pytest.mark.parametrize("path", [
        ".env",
        "credentials.json",
        "token.json",
        "secrets.json",
        ".htpasswd",
        r"d:\project\.env",
        r"d:\project\config\credentials.json",
    ])
    def test_should_block(self, path):
        blocked, _, tag = check_write_path(path)
        assert blocked, f"Expected block for: {path}"
        assert tag == "secret-guard"

    @pytest.mark.parametrize("path", [
        "config.json",
        "settings.json",
        ".env.example",
        "my-credentials-doc.md",
        "hook-rules.yaml",
    ])
    def test_should_allow(self, path):
        blocked, _, _ = check_write_path(path)
        assert not blocked, f"Should not block: {path}"

    def test_reason_includes_matched_file(self):
        """攔截原因應包含命中的檔名。"""
        blocked, reason, _ = check_write_path(".env")
        assert blocked
        assert ".env" in reason


class TestPathTraversal:
    """規則：path-traversal — 攔截路徑遍歷攻擊。"""

    def test_should_block_escape(self, tmp_path):
        """逃逸專案根目錄的路徑應被攔截。"""
        fake_root = str(tmp_path / "project")
        os.makedirs(fake_root, exist_ok=True)
        evil_path = os.path.join(fake_root, "..", "..", "etc", "passwd")
        blocked, _, tag = check_write_path(evil_path, project_root=fake_root)
        assert blocked, f"Expected block for: {evil_path}"
        assert tag == "traversal-guard"

    def test_should_allow_within_project(self, tmp_path):
        """仍在專案目錄內的 .. 路徑應放行。"""
        fake_root = str(tmp_path / "project")
        os.makedirs(os.path.join(fake_root, "sub"), exist_ok=True)
        safe_path = os.path.join(fake_root, "sub", "..", "file.txt")
        blocked, _, _ = check_write_path(safe_path, project_root=fake_root)
        assert not blocked, f"Should not block: {safe_path}"

    def test_no_dotdot_allows(self):
        """不含 .. 的路徑不應觸發遍歷檢查。"""
        blocked, _, _ = check_write_path(
            r"d:\Source\daily-digest-prompt\config\test.yaml",
            project_root=r"d:\Source\daily-digest-prompt",
        )
        assert not blocked

    def test_reason_includes_resolved_path(self, tmp_path):
        """攔截原因應包含解析後的實際路徑。"""
        fake_root = str(tmp_path / "project")
        os.makedirs(fake_root, exist_ok=True)
        evil_path = os.path.join(fake_root, "..", "..", "etc", "passwd")
        blocked, reason, _ = check_write_path(evil_path, project_root=fake_root)
        assert blocked
        assert "passwd" in reason


class TestFallbackBehavior:
    """Fallback 規則應與 YAML 規則產生相同攔截結果。"""

    @pytest.mark.parametrize("path,expected_blocked", [
        ("nul", True),
        ("NUL", True),
        ("scheduler-state.json", True),
        (".env", True),
        ("credentials.json", True),
        ("normal.txt", False),
        ("config.json", False),
        ("hook-rules.yaml", False),
    ])
    def test_fallback_matches_yaml(self, path, expected_blocked):
        blocked_fallback, _, _ = check_write_path(path, FALLBACK_WRITE_RULES)
        blocked_yaml, _, _ = check_write_path(path, load_write_rules())
        assert blocked_fallback == expected_blocked
        assert blocked_yaml == expected_blocked
        assert blocked_fallback == blocked_yaml


class TestEdgeCases:
    """邊界條件。"""

    def test_empty_path(self):
        blocked, _, _ = check_write_path("")
        assert not blocked

    def test_none_rules(self):
        """rules=None 應自動載入規則。"""
        blocked, _, _ = check_write_path("normal.txt", None)
        assert not blocked

    def test_empty_rules_list(self):
        """空規則清單應放行所有路徑。"""
        blocked, _, _ = check_write_path("nul", [])
        assert not blocked

    def test_unknown_check_type_skipped(self):
        """未知的 check 類型應安全跳過（不引發例外）。"""
        rules = [{"id": "bad", "check": "nonexistent_type", "guard_tag": "test"}]
        blocked, _, _ = check_write_path("anything", rules)
        assert not blocked
