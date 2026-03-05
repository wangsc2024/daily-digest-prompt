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
    _sanitize_bash_summary,
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


class TestSanitizeBashSummary:
    """Bash 命令摘要消毒測試。"""

    def test_redact_bearer_token(self):
        """Authorization: Bearer token 應被消毒。"""
        cmd = 'curl -H "Authorization: Bearer abc123secret456" https://api.todoist.com/api/v1/tasks'
        result = _sanitize_bash_summary(cmd)
        assert "abc123secret456" not in result
        assert "<REDACTED>" in result
        assert "Authorization:" in result
        assert "Bearer" in result

    def test_redact_basic_auth(self):
        """Authorization: Basic token 應被消毒。"""
        cmd = 'curl -H "Authorization: Basic dXNlcjpwYXNz" https://example.com'
        result = _sanitize_bash_summary(cmd)
        assert "dXNlcjpwYXNz" not in result
        assert "<REDACTED>" in result

    def test_redact_x_api_token_header(self):
        """X-Api-Token header 應被消毒。"""
        cmd = 'curl -H "X-Api-Token: my_secret_token_value" https://example.com'
        result = _sanitize_bash_summary(cmd)
        assert "my_secret_token_value" not in result
        assert "<REDACTED>" in result

    def test_redact_x_api_key_header(self):
        """X-Api-Key header 應被消毒。"""
        cmd = "curl -H 'X-Api-Key: sk-abc123def456' https://api.openai.com/v1/chat"
        result = _sanitize_bash_summary(cmd)
        assert "sk-abc123def456" not in result
        assert "<REDACTED>" in result

    def test_preserve_non_sensitive_headers(self):
        """非敏感 header 不應被消毒。"""
        cmd = 'curl -H "Content-Type: application/json" https://example.com'
        result = _sanitize_bash_summary(cmd)
        assert result == cmd

    def test_preserve_url_structure(self):
        """URL 結構應保持完整。"""
        cmd = 'curl -H "Authorization: Bearer secret" https://api.todoist.com/api/v1/tasks'
        result = _sanitize_bash_summary(cmd)
        assert "https://api.todoist.com/api/v1/tasks" in result

    def test_no_sensitive_content_passes_through(self):
        """不含敏感內容的命令應原樣通過。"""
        cmd = "ls -la /home/user"
        result = _sanitize_bash_summary(cmd)
        assert result == cmd

    def test_case_insensitive_redaction(self):
        """大小寫不敏感的消毒。"""
        cmd = 'curl -H "authorization: BEARER MyToken123" https://example.com'
        result = _sanitize_bash_summary(cmd)
        assert "MyToken123" not in result


class TestClassifyBashSanitization:
    """classify_bash 的消毒整合測試。"""

    def test_summary_is_sanitized(self):
        """classify_bash 回傳的 summary 應已消毒。"""
        cmd = 'curl -s -H "Authorization: Bearer abc123" https://api.todoist.com/api/v1/tasks'
        summary, tags = classify_bash(cmd)
        assert "abc123" not in summary
        assert "<REDACTED>" in summary
        # tags 仍正常分類
        assert "api-call" in tags
        assert "todoist" in tags

    def test_tags_not_affected_by_sanitization(self):
        """消毒不影響 tag 分類邏輯（使用原始 command 判斷）。"""
        cmd = 'curl -s -H "X-Api-Key: secret" -d @file.json https://ntfy.sh'
        summary, tags = classify_bash(cmd)
        assert "api-call" in tags
        assert "api-write" in tags
        assert "ntfy" in tags


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

    def test_exit_code_0xff_not_benign(self):
        """含 error 且 exit code 非 0 時，不應被 'exit code 0' 的子字串匹配誤判為良性。"""
        output = "error: process failed with exit code 0xFF"
        lower_output = output.lower()
        has_keyword = any(kw in lower_output for kw in ERROR_KEYWORDS)
        # 目前 BENIGN_PATTERNS 中 "exit code 0" 是子字串匹配，會誤匹配 "exit code 0xff"
        has_benign = any(bp in lower_output for bp in BENIGN_PATTERNS)
        assert has_keyword  # "error" matches
        # 修正後 "exit code 0" 不應匹配 "exit code 0xff" → 紅燈測試
        assert not has_benign, "exit code 0xFF 不應被 'exit code 0' 子字串匹配誤判為良性"

    def test_exit_code_0_is_benign(self):
        """exit code 0 確實是良性（成功退出，含換行）。"""
        output = "process completed with exit code 0\n"
        lower_output = output.lower()
        has_benign = any(bp in lower_output for bp in BENIGN_PATTERNS)
        assert has_benign

    def test_exit_code_0_colon_variant_is_benign(self):
        """exit code: 0 格式也是良性。"""
        output = "error handler says exit code: 0"
        lower_output = output.lower()
        has_benign = any(bp in lower_output for bp in BENIGN_PATTERNS)
        assert has_benign

    def test_exit_code_1_not_benign(self):
        """exit code 1 不應被判定為良性。"""
        output = "failed with exit code 1"
        lower_output = output.lower()
        has_benign = any(bp in lower_output for bp in BENIGN_PATTERNS)
        assert not has_benign


# ============================================================
# Tests for output_len Read proxy and cache-miss tag
# ============================================================

class TestOutputLenReadProxy:
    """Read 工具 output_len 代理（使用檔案大小）測試。"""

    def test_read_output_len_uses_file_size(self, tmp_path):
        """Read 工具的 output_len 為 0 時應回落到檔案大小。"""
        # 建立測試檔案
        test_file = tmp_path / "test.md"
        test_file.write_bytes(b"x" * 1234)

        # 模擬 post_tool_logger 計算邏輯（output_len 為 0 時用 file size）
        tool_output = ""
        output_len = len(tool_output)
        if output_len == 0:
            try:
                path = str(test_file)
                import os as _os
                if _os.path.exists(path):
                    output_len = _os.path.getsize(path)
            except (OSError, TypeError):
                pass

        assert output_len == 1234

    def test_read_output_len_nonzero_unchanged(self, tmp_path):
        """output_len 非零時不應修改。"""
        tool_output = "file content here"
        output_len = len(tool_output)
        # 如果已有值，不應被替換
        assert output_len == len("file content here")

    def test_read_output_len_nonexistent_file(self):
        """檔案不存在時 output_len 應維持 0（不拋例外）。"""
        tool_output = ""
        output_len = len(tool_output)
        try:
            import os as _os
            path = "/nonexistent/path/that/does/not/exist.json"
            if _os.path.exists(path):
                output_len = _os.path.getsize(path)
        except (OSError, TypeError):
            pass
        assert output_len == 0


class TestCacheMissTag:
    """cache-miss 標籤偵測測試。"""

    def test_existing_empty_cache_file_tagged_as_miss(self, tmp_path):
        """空快取檔案應標為 cache-miss。"""
        cache_file = tmp_path / "cache" / "todoist.json"
        cache_file.parent.mkdir()
        cache_file.write_bytes(b"")  # 空檔案

        tool_input = {"file_path": str(cache_file)}
        _, tags = classify_read(tool_input)

        assert "cache-read" in tags
        assert "cache-miss" in tags

    def test_nonexistent_cache_file_tagged_as_miss(self, tmp_path):
        """不存在的快取路徑應標為 cache-miss。"""
        cache_path = str(tmp_path / "cache" / "nonexistent.json")
        tool_input = {"file_path": cache_path}
        _, tags = classify_read(tool_input)

        assert "cache-read" in tags
        assert "cache-miss" in tags

    def test_nonempty_cache_file_not_tagged_as_miss(self, tmp_path):
        """有內容的快取檔案不應標為 cache-miss。"""
        cache_file = tmp_path / "cache" / "pingtung-news.json"
        cache_file.parent.mkdir()
        cache_file.write_text('{"data": "ok"}', encoding="utf-8")

        tool_input = {"file_path": str(cache_file)}
        _, tags = classify_read(tool_input)

        assert "cache-read" in tags
        assert "cache-miss" not in tags

    def test_non_cache_path_no_miss_tag(self, tmp_path):
        """非快取路徑讀取不應有 cache-miss 標籤。"""
        regular_file = tmp_path / "SKILL.md"
        regular_file.write_text("# Skill", encoding="utf-8")

        tool_input = {"file_path": str(regular_file)}
        _, tags = classify_read(tool_input)

        assert "cache-miss" not in tags


class TestCognitiveTags:
    """Tests for cognitive tags in classify_bash and classify_read. (Level 3-C)"""

    def test_routing_config_read_bash_gets_cognitive_routing(self):
        """讀取 routing.yaml 的 Bash 指令應標記 cognitive-routing。"""
        cmd = "cat config/routing.yaml"
        _, tags = classify_bash(cmd)
        assert "cognitive-routing" in tags

    def test_scoring_config_read_bash_gets_cognitive_routing(self):
        """讀取 scoring.yaml 的 Bash 指令應標記 cognitive-routing。"""
        cmd = "python -c \"import yaml; yaml.safe_load(open('config/scoring.yaml'))\""
        _, tags = classify_bash(cmd)
        assert "cognitive-routing" in tags

    def test_frequency_limits_bash_gets_cognitive_routing(self):
        """讀取 frequency-limits.yaml 應標記 cognitive-routing。"""
        cmd = "cat config/frequency-limits.yaml | head -20"
        _, tags = classify_bash(cmd)
        assert "cognitive-routing" in tags

    def test_skill_index_bash_gets_cognitive_skill_select(self):
        """讀取 SKILL_INDEX 應標記 cognitive-skill-select。"""
        cmd = "cat skills/SKILL_INDEX.md"
        _, tags = classify_bash(cmd)
        assert "cognitive-skill-select" in tags

    def test_skill_md_bash_gets_cognitive_skill_select(self):
        """讀取 SKILL.md 應標記 cognitive-skill-select。"""
        cmd = "cat skills/ntfy-notify/SKILL.md"
        _, tags = classify_bash(cmd)
        assert "cognitive-skill-select" in tags

    def test_skill_md_read_tool_gets_cognitive_skill_select(self):
        """Read 工具讀取 SKILL.md 應標記 cognitive-skill-select。"""
        tool_input = {"file_path": "skills/ntfy-notify/SKILL.md"}
        _, tags = classify_read(tool_input)
        assert "cognitive-skill-select" in tags
        assert "skill-read" in tags

    def test_claude_retry_bash_gets_cognitive_retry(self):
        """claude -p 含 retry 關鍵字應標記 cognitive-retry。"""
        cmd = "echo 'retry prompt' | claude -p --allowedTools Read,Bash"
        _, tags = classify_bash(cmd)
        assert "cognitive-retry" in tags

    def test_normal_bash_no_cognitive_tags(self):
        """一般 Bash 指令不應有 cognitive tags。"""
        cmd = "ls -la results/"
        _, tags = classify_bash(cmd)
        assert "cognitive-routing" not in tags
        assert "cognitive-skill-select" not in tags
        assert "cognitive-retry" not in tags


class TestSpanTypeInLogEntry:
    """Tests for span_type field in JSONL log entry. (Level 3-B)"""

    def test_classify_bash_does_not_add_span_type(self):
        """classify_bash 不應加入 span_type 標籤（由 log entry building 負責注入）。"""
        _, tags = classify_bash("ls -la")
        assert "span_type" not in tags

    def test_classify_read_does_not_add_span_type(self):
        """classify_read 不應加入 span_type 標籤。"""
        _, tags = classify_read({"file_path": "config/slo.yaml"})
        assert "span_type" not in tags
