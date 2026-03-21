#!/usr/bin/env python3
"""Skill Registry 同步工具單元測試。"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.sync_skill_registry import parse_frontmatter, load_skill_index


class TestParseFrontmatter:
    """parse_frontmatter() YAML 前文解析測試。"""

    def test_simple_key_value(self):
        text = "---\nname: test-skill\nversion: 1.0.0\n---\n# Content"
        result = parse_frontmatter(text)
        assert result["name"] == "test-skill"
        assert result["version"] == "1.0.0"

    def test_list_items(self):
        text = "---\nname: test\ntriggers:\n  - hello\n  - world\n---\n"
        result = parse_frontmatter(text)
        assert result["triggers"] == ["hello", "world"]

    def test_inline_list(self):
        text = '---\ndepends-on: [api-cache, groq]\n---\n'
        result = parse_frontmatter(text)
        assert result["depends-on"] == ["api-cache", "groq"]

    def test_quoted_values(self):
        text = '---\nversion: "2.0.0"\nname: \'my-skill\'\n---\n'
        result = parse_frontmatter(text)
        assert result["version"] == "2.0.0"
        assert result["name"] == "my-skill"

    def test_no_frontmatter(self):
        text = "# Just a markdown file\nNo frontmatter here."
        result = parse_frontmatter(text)
        assert result == {}

    def test_empty_string(self):
        result = parse_frontmatter("")
        assert result == {}

    def test_unclosed_frontmatter(self):
        text = "---\nname: test\nversion: 1.0\n"
        result = parse_frontmatter(text)
        assert result == {}

    def test_multiline_description(self):
        text = "---\nname: test\ndescription: |\n  This is a long\n  description\n---\n"
        result = parse_frontmatter(text)
        assert result["name"] == "test"
        assert "description" in result

    def test_list_without_indent(self):
        text = "---\ntriggers:\n- alpha\n- beta\n---\n"
        result = parse_frontmatter(text)
        assert result["triggers"] == ["alpha", "beta"]

    def test_empty_value_followed_by_list(self):
        text = "---\nallowed-tools:\n  - Bash\n  - Read\n  - Write\n---\n"
        result = parse_frontmatter(text)
        assert result["allowed-tools"] == ["Bash", "Read", "Write"]

    def test_mixed_keys_and_lists(self):
        text = "---\nname: test\nversion: 1.0\ntriggers:\n  - a\n  - b\ncache-ttl: 60min\n---\n"
        result = parse_frontmatter(text)
        assert result["name"] == "test"
        assert result["triggers"] == ["a", "b"]
        assert result["cache-ttl"] == "60min"


class TestLoadSkillIndex:
    """load_skill_index() 技能名稱擷取測試。"""

    def test_backtick_names(self, tmp_path):
        index = tmp_path / "SKILL_INDEX.md"
        index.write_text("| 1 | `todoist` | 待辦 |\n| 2 | `gmail` | 郵件 |\n", encoding="utf-8")
        result = load_skill_index(index)
        assert "todoist" in result
        assert "gmail" in result

    def test_bold_names(self, tmp_path):
        index = tmp_path / "SKILL_INDEX.md"
        index.write_text("- **knowledge-query**: KB\n- **ntfy-notify**: 通知\n", encoding="utf-8")
        result = load_skill_index(index)
        assert "knowledge-query" in result
        assert "ntfy-notify" in result

    def test_table_pipe_names(self, tmp_path):
        index = tmp_path / "SKILL_INDEX.md"
        index.write_text("| api-cache | 快取管理 |\n| system-insight | 系統洞察 |\n", encoding="utf-8")
        result = load_skill_index(index)
        assert "api-cache" in result
        assert "system-insight" in result

    def test_nonexistent_file(self, tmp_path):
        result = load_skill_index(tmp_path / "nonexistent.md")
        assert result == set()

    def test_empty_file(self, tmp_path):
        index = tmp_path / "SKILL_INDEX.md"
        index.write_text("# Empty index\n", encoding="utf-8")
        result = load_skill_index(index)
        assert isinstance(result, set)

    def test_mixed_formats(self, tmp_path):
        index = tmp_path / "SKILL_INDEX.md"
        index.write_text(
            "| `todoist` | 待辦 |\n**gmail** is good\nUse `api-cache` for caching\n",
            encoding="utf-8"
        )
        result = load_skill_index(index)
        assert "todoist" in result
        assert "gmail" in result
        assert "api-cache" in result
