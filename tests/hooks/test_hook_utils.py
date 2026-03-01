"""Tests for hooks/hook_utils.py — Hook 共用工具模組測試。"""
import json
import os
import re
import sys
from unittest.mock import patch

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from hook_utils import (
    find_config_path, load_yaml_rules, log_blocked_event,
    get_compiled_regex, get_rule_patterns, get_rule_re_flags,
)


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
        hook_utils.clear_yaml_config_cache()
        monkeypatch.setattr(hook_utils, "find_config_path", lambda filename="hook-rules.yaml": None)
        fallback = [{"id": "fallback"}]
        rules = load_yaml_rules("bash_rules", fallback)
        assert rules is fallback
        hook_utils.clear_yaml_config_cache()


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


class TestYamlConfigCache:
    """YAML 配置載入快取機制。"""

    def test_repeated_calls_return_same_result(self):
        """連續呼叫 load_yaml_rules 應回傳一致的結果。"""
        fallback = [{"id": "fallback"}]
        result1 = load_yaml_rules("bash_rules", fallback)
        result2 = load_yaml_rules("bash_rules", fallback)
        assert result1 == result2

    def test_cache_avoids_repeated_file_reads(self, monkeypatch):
        """快取啟用後，第二次呼叫不應重新開檔。"""
        import hook_utils
        # 清除快取
        hook_utils.clear_yaml_config_cache()

        call_count = {"n": 0}
        original_open = open

        def counting_open(*args, **kwargs):
            if args and isinstance(args[0], str) and "hook-rules.yaml" in args[0]:
                call_count["n"] += 1
            return original_open(*args, **kwargs)

        with patch("builtins.open", side_effect=counting_open):
            load_yaml_rules("bash_rules", [])
            first_count = call_count["n"]
            load_yaml_rules("write_rules", [])
            second_count = call_count["n"]

        # 第二次呼叫不應增加開檔次數（從快取取得）
        assert second_count == first_count
        # 清除快取避免影響其他測試
        hook_utils.clear_yaml_config_cache()

    def test_clear_cache_forces_reload(self, monkeypatch):
        """清除快取後應重新載入配置。"""
        import hook_utils
        hook_utils.clear_yaml_config_cache()

        fallback = [{"id": "fallback"}]
        result1 = load_yaml_rules("bash_rules", fallback)
        hook_utils.clear_yaml_config_cache()
        result2 = load_yaml_rules("bash_rules", fallback)
        assert result1 == result2  # 結果相同但經過重新載入


class TestGetRulePatterns:
    """共用規則 pattern 提取。"""

    def test_single_pattern(self):
        """單一 pattern 規則應回傳含該 pattern 的清單。"""
        rule = {"pattern": r"echo\s+hello"}
        assert get_rule_patterns(rule) == [r"echo\s+hello"]

    def test_multiple_patterns(self):
        """多個 patterns 應直接回傳。"""
        rule = {"patterns": [r"a+", r"b+"]}
        assert get_rule_patterns(rule) == [r"a+", r"b+"]

    def test_patterns_takes_precedence(self):
        """同時有 pattern 和 patterns 時，patterns 優先。"""
        rule = {"pattern": r"single", "patterns": [r"multi1", r"multi2"]}
        assert get_rule_patterns(rule) == [r"multi1", r"multi2"]

    def test_empty_rule(self):
        """無 pattern/patterns 時回傳空清單。"""
        assert get_rule_patterns({}) == []

    def test_empty_patterns_falls_back_to_single(self):
        """patterns 為空清單時應回退到 pattern。"""
        rule = {"pattern": r"fallback", "patterns": []}
        assert get_rule_patterns(rule) == [r"fallback"]


class TestGetRuleReFlags:
    """共用規則 regex flags 提取。"""

    def test_ignorecase(self):
        """flags 為 IGNORECASE 時回傳 re.IGNORECASE。"""
        rule = {"flags": "IGNORECASE"}
        assert get_rule_re_flags(rule) == re.IGNORECASE

    def test_no_flags(self):
        """無 flags 時回傳 0。"""
        assert get_rule_re_flags({}) == 0

    def test_unknown_flags(self):
        """未知 flags 值回傳 0。"""
        assert get_rule_re_flags({"flags": "UNKNOWN"}) == 0
