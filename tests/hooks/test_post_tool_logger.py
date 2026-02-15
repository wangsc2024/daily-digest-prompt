"""Tests for hooks/post_tool_logger.py — 結構化日誌分類與標籤測試。"""
import os
import sys

import pytest

# 將 hooks/ 加入路徑以便匯入
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, "hooks"))

from post_tool_logger import (
    detect_api_sources,
    classify_bash,
    classify_write,
    classify_read,
    classify_edit,
    ERROR_KEYWORDS,
    BENIGN_PATTERNS,
)


class TestDetectApiSources:
    """API 來源偵測。"""

    def test_detect_todoist(self):
        sources = detect_api_sources("curl -s https://api.todoist.com/api/v1/tasks")
        assert "todoist" in sources

    def test_detect_pingtung_news(self):
        sources = detect_api_sources("curl -s -X POST https://ptnews-mcp.pages.dev/mcp")
        assert "pingtung-news" in sources

    def test_detect_hackernews(self):
        sources = detect_api_sources("curl -s https://hacker-news.firebaseio.com/v0/topstories.json")
        assert "hackernews" in sources

    def test_detect_knowledge(self):
        sources = detect_api_sources("curl -s http://localhost:3000/api/notes")
        assert "knowledge" in sources

    def test_detect_ntfy(self):
        sources = detect_api_sources("curl -d @file.json https://ntfy.sh")
        assert "ntfy" in sources

    def test_detect_gmail(self):
        sources = detect_api_sources("curl https://gmail.googleapis.com/gmail/v1/users/me")
        assert "gmail" in sources

    def test_detect_multiple_sources(self):
        sources = detect_api_sources("todoist.com and localhost:3000")
        assert "todoist" in sources
        assert "knowledge" in sources

    def test_no_source_detected(self):
        sources = detect_api_sources("echo hello world")
        assert sources == []


class TestClassifyBash:
    """Bash 指令分類。"""

    def test_curl_api_call(self):
        summary, tags = classify_bash("curl -s https://api.todoist.com/api/v1/tasks")
        assert "api-call" in tags
        assert "todoist" in tags
        assert "api-read" in tags

    def test_curl_post_is_api_write(self):
        summary, tags = classify_bash("curl -s -X POST https://ntfy.sh -d @file.json")
        assert "api-call" in tags
        assert "api-write" in tags

    def test_curl_with_data_flag_is_write(self):
        summary, tags = classify_bash("curl -d @import.json http://localhost:3000/api/import")
        assert "api-write" in tags

    def test_curl_with_data_raw_is_write(self):
        summary, tags = classify_bash('curl --data-raw \'{"key":"val"}\' https://example.com')
        assert "api-write" in tags

    def test_git_push(self):
        summary, tags = classify_bash("git push origin main")
        assert "git" in tags
        assert "git-push" in tags

    def test_git_commit(self):
        summary, tags = classify_bash("git commit -m 'fix bug'")
        assert "git" in tags
        assert "git-commit" in tags

    def test_rm_file_delete(self):
        summary, tags = classify_bash("rm temp_file.json")
        assert "file-delete" in tags

    def test_sub_agent(self):
        summary, tags = classify_bash("claude -p --allowedTools 'Read,Bash' prompt.md")
        assert "sub-agent" in tags

    def test_python_command(self):
        summary, tags = classify_bash("python -m pytest tests/")
        assert "python" in tags

    def test_summary_truncated(self):
        long_cmd = "x" * 500
        summary, _ = classify_bash(long_cmd)
        assert len(summary) <= 200

    def test_no_tags_for_simple_command(self):
        summary, tags = classify_bash("ls -la")
        assert tags == []


class TestClassifyWrite:
    """Write 工具分類。"""

    def test_cache_write(self):
        summary, tags = classify_write({"file_path": "cache/todoist.json", "content": "{}"})
        assert "cache-write" in tags
        assert "todoist" in tags

    def test_cache_write_backslash(self):
        summary, tags = classify_write({"file_path": "cache\\hackernews.json", "content": "{}"})
        assert "cache-write" in tags

    def test_memory_write(self):
        summary, tags = classify_write({"file_path": "context/digest-memory.json", "content": "{}"})
        assert "memory-write" in tags

    def test_frequency_write(self):
        summary, tags = classify_write({"file_path": "context/auto-tasks-today.json", "content": "{}"})
        assert "frequency-write" in tags

    def test_ntfy_payload(self):
        summary, tags = classify_write({"file_path": "ntfy_temp.json", "content": "{}"})
        assert "ntfy-payload" in tags

    def test_kb_import_payload(self):
        summary, tags = classify_write({"file_path": "import_note.json", "content": "{}"})
        assert "kb-import-payload" in tags

    def test_sub_agent_prompt(self):
        summary, tags = classify_write({"file_path": "task_prompt_3.md", "content": "..."})
        assert "sub-agent-prompt" in tags

    def test_history_write(self):
        summary, tags = classify_write({"file_path": "state/todoist-history.json", "content": "{}"})
        assert "history-write" in tags

    def test_summary_format(self):
        summary, _ = classify_write({"file_path": "test.json", "content": "abc"})
        assert "test.json" in summary
        assert "3 chars" in summary

    def test_no_tags_for_generic_file(self):
        summary, tags = classify_write({"file_path": "some/random/file.txt", "content": "hello"})
        assert tags == []


class TestClassifyRead:
    """Read 工具分類。"""

    def test_cache_read(self):
        summary, tags = classify_read({"file_path": "cache/todoist.json"})
        assert "cache-read" in tags
        assert "todoist" in tags

    def test_skill_read(self):
        summary, tags = classify_read({"file_path": "skills/todoist/SKILL.md"})
        assert "skill-read" in tags

    def test_skill_index(self):
        summary, tags = classify_read({"file_path": "skills/SKILL_INDEX.md"})
        assert "skill-index" in tags

    def test_memory_read(self):
        summary, tags = classify_read({"file_path": "context/digest-memory.json"})
        assert "memory-read" in tags

    def test_state_read(self):
        summary, tags = classify_read({"file_path": "state/scheduler-state.json"})
        assert "state-read" in tags

    def test_frequency_read(self):
        summary, tags = classify_read({"file_path": "context/auto-tasks-today.json"})
        assert "frequency-read" in tags

    def test_history_read(self):
        summary, tags = classify_read({"file_path": "state/todoist-history.json"})
        assert "history-read" in tags

    def test_no_tags_for_generic_file(self):
        summary, tags = classify_read({"file_path": "some/file.txt"})
        assert tags == []


class TestClassifyEdit:
    """Edit 工具分類。"""

    def test_always_has_file_edit_tag(self):
        summary, tags = classify_edit({"file_path": "any_file.txt"})
        assert "file-edit" in tags

    def test_powershell_edit(self):
        summary, tags = classify_edit({"file_path": "run-agent.ps1"})
        assert "powershell-edit" in tags

    def test_markdown_edit(self):
        summary, tags = classify_edit({"file_path": "README.md"})
        assert "markdown-edit" in tags

    def test_json_edit(self):
        summary, tags = classify_edit({"file_path": "config.json"})
        assert "json-edit" in tags


class TestErrorDetection:
    """錯誤偵測邏輯。"""

    def test_error_keywords_are_lowercase(self):
        """所有關鍵字應為小寫（與 lower_output 比對）。"""
        for kw in ERROR_KEYWORDS:
            assert kw == kw.lower(), f"ERROR_KEYWORD '{kw}' should be lowercase"

    def test_benign_patterns_are_lowercase(self):
        """所有良性模式應為小寫。"""
        for bp in BENIGN_PATTERNS:
            assert bp == bp.lower(), f"BENIGN_PATTERN '{bp}' should be lowercase"

    def test_error_keyword_404_does_not_false_positive_with_benign(self):
        """HTTP 狀態碼在良性上下文中不應誤報。"""
        # 例如 "error_count: 0" 包含 "error" 但也包含 "error_count"
        output = '{"error_count": 0, "has_error": false}'
        lower_output = output.lower()
        has_keyword = any(kw in lower_output for kw in ERROR_KEYWORDS)
        has_benign = any(bp in lower_output for bp in BENIGN_PATTERNS)
        # 有 keyword 但也有 benign → 不應判為錯誤
        assert has_keyword
        assert has_benign

    def test_real_error_detected(self):
        """真正的錯誤訊息應能被偵測到。"""
        output = "Connection refused: cannot connect to server"
        lower_output = output.lower()
        has_keyword = any(kw in lower_output for kw in ERROR_KEYWORDS)
        has_benign = any(bp in lower_output for bp in BENIGN_PATTERNS)
        assert has_keyword
        assert not has_benign

    def test_silentlycontinue_is_benign(self):
        """PowerShell 的 SilentlyContinue 不應觸發錯誤。"""
        output = "-ErrorAction SilentlyContinue"
        lower_output = output.lower()
        has_keyword = any(kw in lower_output for kw in ERROR_KEYWORDS)
        has_benign = any(bp in lower_output for bp in BENIGN_PATTERNS)
        assert has_keyword  # "error" matches
        assert has_benign   # "silentlycontinue" is benign
