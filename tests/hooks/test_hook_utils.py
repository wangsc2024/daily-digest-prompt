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
    find_config_path, load_yaml_rules, load_yaml_section, log_blocked_event,
    get_compiled_regex, get_rule_patterns, get_rule_re_flags,
    atomic_write_lines,
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


class TestLoadYamlSection:
    """YAML 通用區段載入（load_yaml_section）。"""

    def test_loads_benign_output_patterns(self):
        """應成功載入 benign_output_patterns 區段（list 型別）。"""
        patterns = load_yaml_section("benign_output_patterns")
        assert isinstance(patterns, list)
        assert len(patterns) >= 10
        # 驗證包含已知的良性模式
        lower_patterns = [str(p).lower() for p in patterns]
        assert "erroraction" in lower_patterns

    def test_loads_presets_as_dict(self):
        """應成功載入 presets 區段（dict 型別）。"""
        presets = load_yaml_section("presets")
        assert isinstance(presets, dict)
        assert "strict" in presets
        assert "normal" in presets

    def test_fallback_on_missing_section(self):
        """YAML 中不存在該區段時應回傳 fallback。"""
        result = load_yaml_section("nonexistent_section", fallback="default_value")
        assert result == "default_value"

    def test_fallback_default_is_none(self):
        """未指定 fallback 時預設回傳 None。"""
        result = load_yaml_section("nonexistent_section")
        assert result is None

    def test_fallback_on_missing_config(self, monkeypatch):
        """配置檔不存在時應回傳 fallback。"""
        import hook_utils
        hook_utils.clear_yaml_config_cache()
        monkeypatch.setattr(hook_utils, "find_config_path", lambda filename="hook-rules.yaml": None)
        result = load_yaml_section("benign_output_patterns", fallback=["fb"])
        assert result == ["fb"]
        hook_utils.clear_yaml_config_cache()

    def test_shares_cache_with_load_yaml_rules(self, monkeypatch):
        """load_yaml_section 與 load_yaml_rules 共用 YAML 快取（不重複開檔）。"""
        import hook_utils
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
            # 第二次呼叫用 load_yaml_section — 應從快取取得
            load_yaml_section("benign_output_patterns")
            second_count = call_count["n"]

        assert second_count == first_count  # 不額外開檔
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


class TestAtomicWriteLines:
    """atomic_write_lines — JSONL 原子寫入。"""

    def test_writes_lines_correctly(self, tmp_path):
        """應正確寫入多行內容，每行自動加換行符。"""
        filepath = str(tmp_path / "test.jsonl")
        lines = ['{"a": 1}', '{"b": 2}', '{"c": 3}']
        atomic_write_lines(filepath, lines)

        with open(filepath, "r", encoding="utf-8") as f:
            written_lines = [l.strip() for l in f.readlines()]

        assert written_lines == lines

    def test_overwrites_existing_file_atomically(self, tmp_path):
        """應原子替換現有檔案（不會出現半寫入狀態）。"""
        filepath = str(tmp_path / "test.jsonl")
        # 先寫入舊內容
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("old content\n")

        # 用 atomic_write_lines 覆寫
        new_lines = ["new line 1", "new line 2"]
        atomic_write_lines(filepath, new_lines)

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        assert "old content" not in content
        assert "new line 1" in content
        assert "new line 2" in content

    def test_creates_parent_directory(self, tmp_path):
        """目標目錄不存在時應自動建立。"""
        filepath = str(tmp_path / "subdir" / "deep" / "test.jsonl")
        atomic_write_lines(filepath, ["line1"])

        assert os.path.exists(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            assert f.readline().strip() == "line1"

    def test_empty_lines_creates_empty_file(self, tmp_path):
        """空清單應建立空檔案。"""
        filepath = str(tmp_path / "empty.jsonl")
        atomic_write_lines(filepath, [])

        assert os.path.exists(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            assert f.read() == ""

    def test_handles_unicode_content(self, tmp_path):
        """應正確處理 UTF-8 中文內容。"""
        filepath = str(tmp_path / "unicode.jsonl")
        lines = ['{"msg": "正體中文測試"}', '{"msg": "日本語テスト"}']
        atomic_write_lines(filepath, lines)

        with open(filepath, "r", encoding="utf-8") as f:
            written_lines = [l.strip() for l in f.readlines()]

        assert written_lines == lines

    def test_no_temp_file_left_on_success(self, tmp_path):
        """成功寫入後不應留下暫存檔。"""
        filepath = str(tmp_path / "clean.jsonl")
        atomic_write_lines(filepath, ["data"])

        # 檢查目錄中沒有 .tmp 檔案
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0
