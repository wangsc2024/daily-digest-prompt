"""Tests for hooks/cjk_guard.py — CJK 日文漢字混入偵測與修正工具測試。"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from cjk_guard import (
    CORRECTIONS,
    EXCLUDED_FILES,
    SCAN_EXTENSIONS,
    detect_issues,
    fix_text,
    post_fix,
)


# ============================================================
# CORRECTIONS 映射表
# ============================================================

class TestCJKCorrections:
    """CORRECTIONS 映射表驗證。"""

    def test_valid_mappings_count(self):
        """CORRECTIONS 應有 12 個唯一映射（源碼無重複 key）。"""
        assert len(CORRECTIONS) == 12

    def test_no_duplicate_keys_in_source(self):
        """源碼中 CORRECTIONS dict 不應有重複 key（Python dict 靜默覆蓋）。"""
        import re
        source_path = os.path.join(project_root, "hooks", "cjk_guard.py")
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()
        # 提取 CORRECTIONS = { ... } 區塊中的 hex key
        m = re.search(r"CORRECTIONS\s*=\s*\{([^}]+)\}", source, re.DOTALL)
        assert m, "找不到 CORRECTIONS 定義"
        keys = re.findall(r"0x[0-9A-Fa-f]+", m.group(1))
        # 每個 key:value 對有兩個 hex，取偶數位置為 key
        hex_keys = keys[::2]
        assert len(hex_keys) == len(set(hex_keys)), (
            f"CORRECTIONS 源碼有重複 key: {[k for k in hex_keys if hex_keys.count(k) > 1]}"
        )

    def test_no_same_codepoint_entries(self):
        """CORRECTIONS 中不應有 jp == tc 的條目。"""
        for jp, tc in CORRECTIONS.items():
            assert jp != tc, f"映射 {jp:#06X} → {tc:#06X} 不應相同"

    def test_edge_mapping_0x8FBA(self):
        """0x8FBA（邊）應正確映射。"""
        assert 0x8FBA in CORRECTIONS
        assert CORRECTIONS[0x8FBA] == 0x908A

    def test_known_mapping_specialist(self):
        """chr(0x5C02) 日文專 → chr(0x5C08) 繁中專。"""
        assert CORRECTIONS[0x5C02] == 0x5C08

    def test_known_mapping_body(self):
        """chr(0x4F53) 日文體 → chr(0x9AD4) 繁中體。"""
        assert CORRECTIONS[0x4F53] == 0x9AD4

    def test_all_corrections_values_differ_from_keys(self):
        """CORRECTIONS 中每個 key 與 value 必須不同。"""
        for jp, tc in CORRECTIONS.items():
            assert jp != tc, f"映射 {jp:#06X} → {tc:#06X} 不應相同"


# ============================================================
# detect_issues 偵測功能
# ============================================================

class TestDetectIssues:
    """detect_issues() 偵測日文漢字混入。"""

    def test_clean_text_returns_empty(self):
        """純繁體中文文字不應報問題。"""
        text = "這是一段正常的繁體中文文字，專案進行中。"
        assert detect_issues(text) == []

    def test_empty_text_returns_empty(self):
        """空字串不應報錯。"""
        assert detect_issues("") == []

    def test_ascii_only_returns_empty(self):
        """純 ASCII 文字不應報問題。"""
        assert detect_issues("hello world 123!@#") == []

    def test_detect_single_jp_char(self):
        """偵測單個日文漢字（U+5C02 專）。"""
        jp_sen = chr(0x5C02)  # 日文「專」
        text = f"這是{jp_sen}案計畫"
        issues = detect_issues(text, "test.md")
        assert len(issues) == 1
        issue = issues[0]
        assert issue['file'] == "test.md"
        assert issue['line'] == 1
        assert issue['char'] == jp_sen
        assert issue['codepoint'] == 'U+5C02'
        assert issue['correct'] == chr(0x5C08)
        assert issue['correct_codepoint'] == 'U+5C08'

    def test_detect_multiple_issues_same_line(self):
        """同一行偵測多個日文漢字。"""
        jp_sen = chr(0x5C02)  # 專
        jp_tai = chr(0x4F53)  # 體
        text = f"這是{jp_sen}案的整{jp_tai}架構"
        issues = detect_issues(text)
        assert len(issues) == 2
        codepoints = {i['codepoint'] for i in issues}
        assert codepoints == {'U+5C02', 'U+4F53'}

    def test_detect_multiline(self):
        """多行偵測，行號正確。"""
        jp_sen = chr(0x5C02)
        jp_guo = chr(0x56FD)  # 國
        text = f"第一行{jp_sen}案\n第二行正常\n第三行{jp_guo}際"
        issues = detect_issues(text)
        assert len(issues) == 2
        assert issues[0]['line'] == 1
        assert issues[1]['line'] == 3

    def test_issue_col_is_one_based(self):
        """欄位 col 應為 1-based。"""
        jp_sen = chr(0x5C02)
        text = f"AB{jp_sen}CD"  # 位置 index=2，col=3
        issues = detect_issues(text)
        assert len(issues) == 1
        assert issues[0]['col'] == 3

    def test_issue_context_field(self):
        """context 欄位應包含前後各最多 10 個字元。"""
        jp_sen = chr(0x5C02)
        text = f"前方文字內容{jp_sen}後方文字內容"
        issues = detect_issues(text)
        assert len(issues) == 1
        ctx = issues[0]['context']
        assert jp_sen in ctx
        assert len(ctx) <= 21  # 前10 + 自身1 + 後10

    def test_issue_dict_has_all_keys(self):
        """issue 字典應包含所有必要欄位。"""
        jp_sen = chr(0x5C02)
        issues = detect_issues(f"{jp_sen}", "myfile.md")
        required_keys = {'file', 'line', 'col', 'char', 'codepoint',
                         'correct', 'correct_codepoint', 'context'}
        assert required_keys == set(issues[0].keys())

    def test_filepath_passed_through(self):
        """filepath 參數應傳遞到 issue['file']。"""
        jp_sen = chr(0x5C02)
        issues = detect_issues(f"text{jp_sen}", "path/to/file.yaml")
        assert issues[0]['file'] == "path/to/file.yaml"

    def test_default_filepath_is_empty(self):
        """未指定 filepath 時預設為空字串。"""
        jp_sen = chr(0x5C02)
        issues = detect_issues(f"{jp_sen}")
        assert issues[0]['file'] == ""


# ============================================================
# fix_text 修正功能
# ============================================================

class TestFixText:
    """fix_text() 日文漢字自動修正。"""

    def test_clean_text_unchanged(self):
        """無問題文字不修改，count=0。"""
        text = "正常的繁體中文文字"
        fixed, count = fix_text(text)
        assert fixed == text
        assert count == 0

    def test_empty_text(self):
        """空字串不報錯，count=0。"""
        fixed, count = fix_text("")
        assert fixed == ""
        assert count == 0

    def test_fix_single_jp_char(self):
        """修正單個日文漢字。"""
        jp_sen = chr(0x5C02)
        tc_sen = chr(0x5C08)
        text = f"這是{jp_sen}案"
        fixed, count = fix_text(text)
        assert count == 1
        assert fixed == f"這是{tc_sen}案"
        assert jp_sen not in fixed

    def test_fix_multiple_jp_chars(self):
        """修正多個不同日文漢字，count 正確。"""
        jp_sen = chr(0x5C02)
        jp_tai = chr(0x4F53)
        jp_guo = chr(0x56FD)
        text = f"{jp_sen}案{jp_tai}制{jp_guo}際"
        fixed, count = fix_text(text)
        assert count == 3
        assert chr(0x5C08) in fixed
        assert chr(0x9AD4) in fixed
        assert chr(0x570B) in fixed

    def test_fix_mixed_text(self):
        """混合 ASCII、繁中、日文漢字的文字。"""
        jp_sen = chr(0x5C02)
        tc_sen = chr(0x5C08)
        text = f"Hello 世界 {jp_sen}案 test 123"
        fixed, count = fix_text(text)
        assert count == 1
        assert fixed == f"Hello 世界 {tc_sen}案 test 123"

    def test_fix_preserves_newlines(self):
        """修正時保留換行符。"""
        jp_sen = chr(0x5C02)
        tc_sen = chr(0x5C08)
        text = f"第一行\n{jp_sen}案\n第三行"
        fixed, count = fix_text(text)
        assert count == 1
        assert fixed == f"第一行\n{tc_sen}案\n第三行"

    def test_fix_same_char_multiple_times(self):
        """同一個日文字出現多次，每次都修正。"""
        jp_sen = chr(0x5C02)
        tc_sen = chr(0x5C08)
        text = f"{jp_sen}案{jp_sen}業{jp_sen}注"
        fixed, count = fix_text(text)
        assert count == 3
        assert fixed == f"{tc_sen}案{tc_sen}業{tc_sen}注"


# ============================================================
# SCAN_EXTENSIONS 與 EXCLUDED_FILES
# ============================================================

class TestConstants:
    """常數定義驗證。"""

    def test_scan_extensions_contains_expected(self):
        """SCAN_EXTENSIONS 應包含 .md, .yaml, .yml, .json, .py, .ps1。"""
        expected = {'.md', '.yaml', '.yml', '.json', '.py', '.ps1'}
        assert expected.issubset(SCAN_EXTENSIONS)

    def test_excluded_files_contains_self(self):
        """EXCLUDED_FILES 應包含 cjk_guard.py 自身。"""
        assert 'cjk_guard.py' in EXCLUDED_FILES


# ============================================================
# post_fix（PostToolUse hook 模式）
# ============================================================

class TestPostFix:
    """post_fix() stdin JSON 處理邏輯。"""

    def _run_post_fix(self, stdin_data: dict) -> int:
        """輔助方法：模擬 stdin JSON 輸入並執行 post_fix。"""
        stdin_json = json.dumps(stdin_data)
        with patch('sys.stdin', __class__=type(sys.stdin)):
            sys.stdin = __import__('io').StringIO(stdin_json)
            return post_fix()

    def test_write_tool_triggers_fix(self):
        """Write 工具寫入含日文漢字的檔案時應自動修正。"""
        jp_sen = chr(0x5C02)
        tc_sen = chr(0x5C08)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md',
                                         delete=False, encoding='utf-8') as f:
            f.write(f"內容含{jp_sen}案")
            tmp_path = f.name
        try:
            result = self._run_post_fix({
                'tool_name': 'Write',
                'tool_input': {'file_path': tmp_path}
            })
            assert result == 0
            content = Path(tmp_path).read_text(encoding='utf-8')
            assert tc_sen in content
            assert jp_sen not in content
        finally:
            os.unlink(tmp_path)

    def test_edit_tool_triggers_fix(self):
        """Edit 工具修改含日文漢字的檔案時應自動修正。"""
        jp_tai = chr(0x4F53)
        tc_tai = chr(0x9AD4)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml',
                                         delete=False, encoding='utf-8') as f:
            f.write(f"description: 整{jp_tai}架構")
            tmp_path = f.name
        try:
            result = self._run_post_fix({
                'tool_name': 'Edit',
                'tool_input': {'file_path': tmp_path}
            })
            assert result == 0
            content = Path(tmp_path).read_text(encoding='utf-8')
            assert tc_tai in content
            assert jp_tai not in content
        finally:
            os.unlink(tmp_path)

    def test_non_write_edit_tool_skipped(self):
        """非 Write/Edit 工具不處理，直接返回 0。"""
        result = self._run_post_fix({
            'tool_name': 'Bash',
            'tool_input': {'command': 'echo hello'}
        })
        assert result == 0

    def test_missing_file_path_skipped(self):
        """無 file_path 不處理。"""
        result = self._run_post_fix({
            'tool_name': 'Write',
            'tool_input': {}
        })
        assert result == 0

    def test_unsupported_extension_skipped(self):
        """不支援的副檔名不處理。"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt',
                                         delete=False, encoding='utf-8') as f:
            f.write(f"text with {chr(0x5C02)}")
            tmp_path = f.name
        try:
            result = self._run_post_fix({
                'tool_name': 'Write',
                'tool_input': {'file_path': tmp_path}
            })
            assert result == 0
            # 檔案不應被修改
            content = Path(tmp_path).read_text(encoding='utf-8')
            assert chr(0x5C02) in content
        finally:
            os.unlink(tmp_path)

    def test_nonexistent_file_skipped(self):
        """檔案不存在時不處理。"""
        result = self._run_post_fix({
            'tool_name': 'Write',
            'tool_input': {'file_path': '/nonexistent/path/file.md'}
        })
        assert result == 0

    def test_invalid_stdin_json(self):
        """無效 JSON stdin 不報錯，返回 0。"""
        with patch('sys.stdin', __class__=type(sys.stdin)):
            sys.stdin = __import__('io').StringIO("not json")
            result = post_fix()
        assert result == 0

    def test_clean_file_not_rewritten(self):
        """無日文漢字的檔案不應被重新寫入。"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                         delete=False, encoding='utf-8') as f:
            f.write("# 正常的繁體中文程式碼\nprint('hello')\n")
            tmp_path = f.name
        try:
            mtime_before = os.path.getmtime(tmp_path)
            result = self._run_post_fix({
                'tool_name': 'Write',
                'tool_input': {'file_path': tmp_path}
            })
            assert result == 0
            mtime_after = os.path.getmtime(tmp_path)
            # count == 0 時不寫入，mtime 不變
            assert mtime_before == mtime_after
        finally:
            os.unlink(tmp_path)
