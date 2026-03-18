"""Tests for KBSearchClient — 知識庫搜尋請求構建與回應解析。"""
import pytest
from kb_search import KBSearchClient


class TestBuildHybridSearchBody:
    """Tests for KBSearchClient.build_hybrid_search_body()."""

    def test_basic_query(self):
        """Basic query should return dict with required fields."""
        client = KBSearchClient()
        body = client.build_hybrid_search_body("RAG 架構")
        assert body["query"] == "RAG 架構"
        assert body["limit"] == 10
        assert body["threshold"] == 0.7

    def test_custom_limit_and_threshold(self):
        """Custom limit and threshold should be reflected in output."""
        client = KBSearchClient()
        body = client.build_hybrid_search_body("test", limit=5, threshold=0.5)
        assert body["limit"] == 5
        assert body["threshold"] == 0.5

    def test_query_stripped(self):
        """Leading/trailing whitespace should be stripped from query."""
        client = KBSearchClient()
        body = client.build_hybrid_search_body("  knowledge base  ")
        assert body["query"] == "knowledge base"

    def test_empty_query_raises(self):
        """Empty query should raise ValueError."""
        client = KBSearchClient()
        with pytest.raises(ValueError, match="query"):
            client.build_hybrid_search_body("")

    def test_whitespace_only_query_raises(self):
        """Whitespace-only query should raise ValueError."""
        client = KBSearchClient()
        with pytest.raises(ValueError):
            client.build_hybrid_search_body("   ")

    def test_limit_too_small_raises(self):
        """limit < 1 should raise ValueError."""
        client = KBSearchClient()
        with pytest.raises(ValueError, match="limit"):
            client.build_hybrid_search_body("q", limit=0)

    def test_limit_too_large_raises(self):
        """limit > 100 should raise ValueError."""
        client = KBSearchClient()
        with pytest.raises(ValueError, match="limit"):
            client.build_hybrid_search_body("q", limit=101)

    def test_limit_boundary_values(self):
        """limit of 1 and 100 should be accepted."""
        client = KBSearchClient()
        assert client.build_hybrid_search_body("q", limit=1)["limit"] == 1
        assert client.build_hybrid_search_body("q", limit=100)["limit"] == 100

    def test_threshold_out_of_range_raises(self):
        """threshold outside 0.0-1.0 should raise ValueError."""
        client = KBSearchClient()
        with pytest.raises(ValueError, match="threshold"):
            client.build_hybrid_search_body("q", threshold=1.5)
        with pytest.raises(ValueError, match="threshold"):
            client.build_hybrid_search_body("q", threshold=-0.1)


class TestBuildTitleSearchBody:
    """Tests for KBSearchClient.build_title_search_body()."""

    def test_basic_title_search(self):
        """Title search body should include query, type, limit."""
        client = KBSearchClient()
        body = client.build_title_search_body("ADR 架構")
        assert body["query"] == "ADR 架構"
        assert body["search_type"] == "title"
        assert body["limit"] == 5

    def test_empty_title_raises(self):
        """Empty title should raise ValueError."""
        client = KBSearchClient()
        with pytest.raises(ValueError):
            client.build_title_search_body("")


class TestBuildKeywordSearchBody:
    """Tests for KBSearchClient.build_keyword_search_body()."""

    def test_basic_keyword_search(self):
        """Keyword search body should include query and limit."""
        client = KBSearchClient()
        body = client.build_keyword_search_body("LangChain", limit=3)
        assert body["query"] == "LangChain"
        assert body["limit"] == 3

    def test_empty_keyword_raises(self):
        """Empty keyword should raise ValueError."""
        client = KBSearchClient()
        with pytest.raises(ValueError):
            client.build_keyword_search_body("")


class TestParseSearchResults:
    """Tests for KBSearchClient.parse_search_results()."""

    def test_parse_standard_response(self):
        """Standard API response should parse to list of dicts."""
        client = KBSearchClient()
        response = {
            "results": [
                {"id": "abc", "title": "RAG 入門", "content": "向量搜尋", "score": 0.92, "tags": ["AI"]},
                {"id": "def", "title": "LangChain", "content": "框架介紹", "score": 0.75, "tags": []},
            ]
        }
        results = client.parse_search_results(response)
        assert len(results) == 2
        assert results[0]["id"] == "abc"
        assert results[0]["title"] == "RAG 入門"
        assert results[0]["score"] == 0.92
        assert results[0]["tags"] == ["AI"]

    def test_parse_empty_results(self):
        """Empty results list should return empty list."""
        client = KBSearchClient()
        assert client.parse_search_results({"results": []}) == []

    def test_parse_missing_results_key(self):
        """Response without 'results' key should return empty list."""
        client = KBSearchClient()
        assert client.parse_search_results({}) == []

    def test_parse_non_dict_response(self):
        """Non-dict input should return empty list."""
        client = KBSearchClient()
        assert client.parse_search_results(None) == []
        assert client.parse_search_results([]) == []
        assert client.parse_search_results("string") == []

    def test_parse_missing_title_uses_default(self):
        """Missing title should default to '(無標題)'."""
        client = KBSearchClient()
        response = {"results": [{"id": "x", "content": "body", "score": 0.5}]}
        results = client.parse_search_results(response)
        assert results[0]["title"] == "(無標題)"

    def test_parse_score_rounded_to_4_decimals(self):
        """Score should be rounded to 4 decimal places."""
        client = KBSearchClient()
        response = {"results": [{"id": "1", "score": 0.123456789}]}
        results = client.parse_search_results(response)
        assert results[0]["score"] == 0.1235

    def test_parse_skips_non_dict_items(self):
        """Non-dict items in results list should be skipped."""
        client = KBSearchClient()
        response = {"results": [{"id": "1", "title": "Good"}, "bad", None, 123]}
        results = client.parse_search_results(response)
        assert len(results) == 1
        assert results[0]["id"] == "1"


class TestParseNoteIds:
    """Tests for KBSearchClient.parse_note_ids()."""

    def test_extract_ids(self):
        """parse_note_ids should return list of IDs."""
        client = KBSearchClient()
        response = {"results": [{"id": "abc"}, {"id": "def"}, {"id": ""}]}
        ids = client.parse_note_ids(response)
        assert ids == ["abc", "def"]  # empty ID excluded


class TestFormatResultsForAgent:
    """Tests for KBSearchClient.format_results_for_agent()."""

    def test_format_empty_returns_no_notes_message(self):
        """Empty results should return placeholder message."""
        client = KBSearchClient()
        assert client.format_results_for_agent([]) == "（無相關筆記）"

    def test_format_includes_title_and_id(self):
        """Formatted output should include title and note ID."""
        client = KBSearchClient()
        results = [{"id": "abc123", "title": "RAG 入門", "content": "內容", "score": 0.9}]
        output = client.format_results_for_agent(results)
        assert "RAG 入門" in output
        assert "abc123" in output

    def test_format_includes_score(self):
        """Formatted output should include score by default."""
        client = KBSearchClient()
        results = [{"id": "x", "title": "T", "content": "", "score": 0.87}]
        output = client.format_results_for_agent(results)
        assert "0.87" in output

    def test_format_hides_score_when_disabled(self):
        """Score should be hidden when show_score=False."""
        client = KBSearchClient()
        results = [{"id": "x", "title": "T", "content": "", "score": 0.87}]
        output = client.format_results_for_agent(results, show_score=False)
        assert "0.87" not in output

    def test_format_content_truncated(self):
        """Content should be truncated at max_chars_per_result."""
        client = KBSearchClient()
        long_content = "x" * 500
        results = [{"id": "1", "title": "T", "content": long_content, "score": 0.5}]
        output = client.format_results_for_agent(results, max_chars_per_result=50)
        assert "x" * 500 not in output

    def test_format_numbered_list(self):
        """Results should be numbered starting from 1."""
        client = KBSearchClient()
        results = [
            {"id": "1", "title": "First", "content": "", "score": 0.9},
            {"id": "2", "title": "Second", "content": "", "score": 0.8},
        ]
        output = client.format_results_for_agent(results)
        assert "1. First" in output
        assert "2. Second" in output


class TestFormatDedupCheck:
    """Tests for KBSearchClient.format_dedup_check()."""

    def test_no_high_similarity_returns_none(self):
        """No results above threshold should return None."""
        client = KBSearchClient()
        results = [{"id": "x", "title": "T", "score": 0.5}]
        assert client.format_dedup_check(results, threshold=0.8) is None

    def test_high_similarity_returns_warning(self):
        """Results above threshold should return warning message."""
        client = KBSearchClient()
        results = [{"id": "x", "title": "Similar Note", "score": 0.9}]
        warning = client.format_dedup_check(results, threshold=0.8)
        assert warning is not None
        assert "Similar Note" in warning
        assert "去重" in warning

    def test_empty_results_returns_none(self):
        """Empty results should return None."""
        client = KBSearchClient()
        assert client.format_dedup_check([]) is None


class TestURLHelpers:
    """Tests for KBSearchClient URL helper methods."""

    def test_default_base_url(self):
        """Default base URL should be localhost:3000."""
        client = KBSearchClient()
        assert "localhost:3000" in client.health_check_url()

    def test_custom_base_url(self):
        """Custom base URL should be reflected in all URL methods."""
        client = KBSearchClient(base_url="http://my-kb.local:8080")
        assert "my-kb.local:8080" in client.search_url("hybrid")
        assert "my-kb.local:8080" in client.notes_url()

    def test_trailing_slash_stripped_from_base_url(self):
        """Trailing slash in base_url should be stripped."""
        client = KBSearchClient(base_url="http://localhost:3000/")
        assert not client.health_check_url().startswith("http://localhost:3000//")

    def test_search_url_by_type(self):
        """search_url should include search type in path."""
        client = KBSearchClient()
        assert "/hybrid" in client.search_url("hybrid")
        assert "/title" in client.search_url("title")
        assert "/keyword" in client.search_url("keyword")
