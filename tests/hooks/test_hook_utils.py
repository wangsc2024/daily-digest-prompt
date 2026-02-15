"""Tests for hooks/hook_utils.py — Hook 共用工具模組測試。"""
import json
import os
import sys

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from hook_utils import find_config_path, load_yaml_rules, log_blocked_event


class TestFindConfigPath:
    """配置檔搜尋邏輯。"""

    def test_finds_existing_config(self):
        """專案 config/ 目錄下存在時應回傳路徑。"""
        path = find_config_path("hook-rules.yaml")
        assert path is not None
        assert path.endswith("hook-rules.yaml")
        assert os.path.isfile(path)

    def test_returns_none_for_missing(self):
        """檔案不存在時應回傳 None。"""
        path = find_config_path("nonexistent-file.yaml")
        assert path is None

    def test_default_filename(self):
        """未指定檔名時使用預設值 hook-rules.yaml。"""
        path = find_config_path()
        assert path is not None


class TestLoadYamlRules:
    """YAML 規則載入與 fallback 機制。"""

    def test_loads_bash_rules(self):
        """應成功載入 bash_rules 區段。"""
        fallback = [{"id": "fallback"}]
        rules = load_yaml_rules("bash_rules", fallback)
        assert isinstance(rules, list)
        assert len(rules) >= 6
        assert rules is not fallback

    def test_loads_write_rules(self):
        """應成功載入 write_rules 區段。"""
        fallback = [{"id": "fallback"}]
        rules = load_yaml_rules("write_rules", fallback)
        assert isinstance(rules, list)
        assert len(rules) >= 4
        assert rules is not fallback

    def test_fallback_on_missing_section(self):
        """YAML 中不存在該區段時應回退。"""
        fallback = [{"id": "fallback"}]
        rules = load_yaml_rules("nonexistent_section", fallback)
        assert rules is fallback

    def test_fallback_on_missing_config(self, monkeypatch):
        """配置檔不存在時應回退。"""
        import hook_utils
        monkeypatch.setattr(hook_utils, "find_config_path", lambda filename="hook-rules.yaml": None)
        fallback = [{"id": "fallback"}]
        rules = load_yaml_rules("bash_rules", fallback)
        assert rules is fallback


class TestLogBlockedEvent:
    """攔截事件 JSONL 日誌寫入。"""

    def test_creates_log_entry(self, tmp_path, monkeypatch):
        """應建立包含正確欄位的 JSONL 日誌記錄。"""
        monkeypatch.chdir(tmp_path)
        log_blocked_event("session123", "Bash", "echo > nul", "禁止 nul", "nul-guard")

        log_dir = tmp_path / "logs" / "structured"
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) == 1

        with open(log_files[0], "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["tool"] == "Bash"
        assert entry["event"] == "blocked"
        assert entry["reason"] == "禁止 nul"
        assert "blocked" in entry["tags"]
        assert "nul-guard" in entry["tags"]
        assert entry["sid"] == "session123"[:12]

    def test_truncates_long_summary(self, tmp_path, monkeypatch):
        """summary 超過 200 字元應被截斷。"""
        monkeypatch.chdir(tmp_path)
        long_command = "x" * 500
        log_blocked_event("sid", "Bash", long_command, "reason", "tag")

        log_dir = tmp_path / "logs" / "structured"
        log_files = list(log_dir.glob("*.jsonl"))
        with open(log_files[0], "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert len(entry["summary"]) == 200

    def test_handles_empty_session_id(self, tmp_path, monkeypatch):
        """空 session_id 不應引發錯誤。"""
        monkeypatch.chdir(tmp_path)
        log_blocked_event("", "Write", "/path", "reason", "tag")

        log_dir = tmp_path / "logs" / "structured"
        log_files = list(log_dir.glob("*.jsonl"))
        with open(log_files[0], "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["sid"] == ""
