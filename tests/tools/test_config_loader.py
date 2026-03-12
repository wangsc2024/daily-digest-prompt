"""
tests/tools/test_config_loader.py — 集中配置載入器測試

覆蓋重點：
  - get_groq_endpoint() 從 llm-router.yaml 讀取
  - 配置不存在時回傳預設值
  - module-level cache 行為
  - reset_cache() 清除快取
"""
import sys
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.config_loader import (  # noqa: E402
    get_groq_endpoint,
    get_groq_health_endpoint,
    get_groq_model,
    get_groq_timeout,
    get_kb_api_base,
    reset_cache,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """每個測試前後清除 module-level cache。"""
    reset_cache()
    yield
    reset_cache()


class TestGetGroqEndpoint:
    def test_returns_endpoint_from_config(self):
        yaml_content = """
providers:
  groq:
    endpoint: http://custom:9999/groq/chat
"""
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            result = get_groq_endpoint()
        assert result == "http://custom:9999/groq/chat"

    def test_returns_default_when_config_missing(self):
        with patch("tools.config_loader.LLM_ROUTER_CONFIG_PATH", Path("/nonexistent/config.yaml")):
            result = get_groq_endpoint()
        assert result == "http://localhost:3002/groq/chat"


class TestGetGroqHealthEndpoint:
    def test_returns_health_from_config(self):
        yaml_content = """
providers:
  groq:
    health_check: http://custom:9999/groq/health
"""
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            result = get_groq_health_endpoint()
        assert result == "http://custom:9999/groq/health"


class TestGetGroqModel:
    def test_returns_default_model(self):
        with patch("tools.config_loader.LLM_ROUTER_CONFIG_PATH", Path("/nonexistent")):
            result = get_groq_model()
        assert result == "llama-3.1-8b-instant"


class TestGetGroqTimeout:
    def test_returns_default_timeout(self):
        with patch("tools.config_loader.LLM_ROUTER_CONFIG_PATH", Path("/nonexistent")):
            result = get_groq_timeout()
        assert result == 20


class TestGetKbApiBase:
    def test_returns_localhost_3000(self):
        assert get_kb_api_base() == "http://localhost:3000"


class TestCacheReset:
    def test_cache_cleared_after_reset(self):
        with patch("tools.config_loader.LLM_ROUTER_CONFIG_PATH", Path("/nonexistent")):
            get_groq_endpoint()  # populate cache
            reset_cache()

            yaml_content = """
providers:
  groq:
    endpoint: http://new-endpoint:8080/groq/chat
"""
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                result = get_groq_endpoint()
            assert result == "http://new-endpoint:8080/groq/chat"
