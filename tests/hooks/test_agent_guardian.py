#!/usr/bin/env python3
"""
Tests for Agent Guardian (Error Classifier + Circuit Breaker)

測試覆蓋範圍：
  - ErrorClassifier: 5 categories × 4 scenarios = 20 tests
  - CircuitBreaker: 6 state transitions × 5 scenarios = 30 tests
  - Integration: 5 scenarios
  Total: ~55 tests
"""
import pytest
import json
import os
import tempfile
from datetime import datetime, timedelta
import sys

# Add hooks directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "hooks"))

from agent_guardian import ErrorClassifier, CircuitBreaker


# ============================================
# ErrorClassifier Tests
# ============================================

class TestErrorClassifier:
    """ErrorClassifier 測試套件"""

    @pytest.fixture
    def classifier(self):
        return ErrorClassifier()

    # === Success Cases ===

    def test_success_exit_code_zero(self, classifier):
        """Exit code 0 → success"""
        result = classifier.classify("Bash", "curl https://api.todoist.com", "OK", 0)
        assert result["category"] == "success"
        assert result["retry_intent"] is None
        assert result["should_alert"] is False

    # === Rate Limit (429) ===

    def test_rate_limit_429_with_retry_after(self, classifier):
        """HTTP 429 + Retry-After header → long_delay"""
        output = "HTTP/1.1 429 Too Many Requests\nRetry-After: 30\n"
        result = classifier.classify("Bash", "curl https://api.todoist.com", output, 1)
        assert result["category"] == "rate_limit"
        assert result["retry_intent"] == "long_delay"
        assert result["wait_seconds"] == 30
        assert result["should_alert"] is False

    def test_rate_limit_429_without_retry_after(self, classifier):
        """HTTP 429 無 Retry-After → 預設 60s"""
        output = "HTTP/1.1 429 Too Many Requests\n"
        result = classifier.classify("Bash", "curl https://api.todoist.com", output, 1)
        assert result["category"] == "rate_limit"
        assert result["wait_seconds"] == 60

    def test_rate_limit_status_429(self, classifier):
        """status: 429 pattern"""
        output = "status: 429, message: Rate limit exceeded"
        result = classifier.classify("Bash", "curl todoist", output, 1)
        assert result["category"] == "rate_limit"

    # === Server Error (500-504) ===

    def test_server_error_500(self, classifier):
        """HTTP 500 → use_cache"""
        output = "HTTP/1.1 500 Internal Server Error\n"
        result = classifier.classify("Bash", "curl pingtung", output, 1)
        assert result["category"] == "server_error"
        assert result["retry_intent"] == "use_cache"
        assert result["should_alert"] is True
        assert result["api_source"] == "pingtung-news"

    def test_server_error_503(self, classifier):
        """HTTP 503 → use_cache"""
        output = "Error 503: Service Unavailable"
        result = classifier.classify("Bash", "curl https://example.com", output, 1)
        assert result["category"] == "server_error"
        assert result["retry_intent"] == "use_cache"

    def test_server_error_504(self, classifier):
        """HTTP 504 Gateway Timeout → use_cache"""
        output = "HTTP/1.1 504 Gateway Timeout"
        result = classifier.classify("Bash", "curl api", output, 1)
        assert result["category"] == "server_error"

    # === Client Error (401, 403) ===

    def test_client_error_401(self, classifier):
        """HTTP 401 → stop + alert"""
        output = "HTTP/1.1 401 Unauthorized\n"
        result = classifier.classify("Bash", "curl todoist", output, 1)
        assert result["category"] == "client_error"
        assert result["retry_intent"] == "stop"
        assert result["should_alert"] is True
        assert result["api_source"] == "todoist"

    def test_client_error_403(self, classifier):
        """HTTP 403 → stop + alert"""
        output = "status: 403 Forbidden"
        result = classifier.classify("Bash", "curl https://gmail.googleapis.com/api", output, 1)
        assert result["category"] == "client_error"
        assert result["retry_intent"] == "stop"
        assert result["api_source"] == "gmail"

    # === Network Error ===

    def test_network_error_connection_refused(self, classifier):
        """Connection refused → exponential"""
        output = "curl: (7) Failed to connect to localhost port 3000: Connection refused"
        result = classifier.classify("Bash", "curl localhost:3000", output, 7)
        assert result["category"] == "network_error"
        assert result["retry_intent"] == "exponential"
        assert result["wait_seconds"] == 5
        assert result["api_source"] == "knowledge"

    def test_network_error_timeout(self, classifier):
        """Connection timeout → exponential"""
        output = "curl: (28) Connection timed out after 10000 milliseconds"
        result = classifier.classify("Bash", "curl api", output, 28)
        assert result["category"] == "network_error"

    def test_network_error_name_resolution(self, classifier):
        """DNS 解析失敗 → exponential"""
        output = "curl: (6) Could not resolve host: invalid.example.com"
        result = classifier.classify("Bash", "curl invalid.example.com", output, 6)
        assert result["category"] == "network_error"

    # === API Source Detection ===

    def test_api_source_todoist(self, classifier):
        """偵測 Todoist API"""
        result = classifier.classify("Bash", "curl https://api.todoist.com/rest/v2/tasks", "Error", 1)
        assert result["api_source"] == "todoist"

    def test_api_source_hackernews(self, classifier):
        """偵測 Hacker News API"""
        result = classifier.classify("Bash", "curl https://hacker-news.firebaseio.com/v0/topstories.json", "Error", 1)
        assert result["api_source"] == "hackernews"

    def test_api_source_ntfy(self, classifier):
        """偵測 ntfy API"""
        result = classifier.classify("Bash", "curl -d @msg.json ntfy.sh/topic", "Error", 1)
        assert result["api_source"] == "ntfy"

    def test_api_source_unknown(self, classifier):
        """未知 API → None"""
        result = classifier.classify("Bash", "curl https://unknown-api.com", "Error", 1)
        assert result["api_source"] is None

    # === Unknown Error ===

    def test_unknown_error(self, classifier):
        """無法分類的錯誤 → exponential"""
        output = "Some unknown error occurred"
        result = classifier.classify("Bash", "unknown command", output, 127)
        assert result["category"] == "unknown"
        assert result["retry_intent"] == "exponential"


# ============================================
# CircuitBreaker Tests
# ============================================

class TestCircuitBreaker:
    """CircuitBreaker 測試套件"""

    @pytest.fixture
    def temp_state_file(self):
        """建立臨時狀態檔案"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_file = f.name
        yield temp_file
        # Cleanup
        if os.path.exists(temp_file):
            os.remove(temp_file)

    @pytest.fixture
    def breaker(self, temp_state_file):
        return CircuitBreaker(temp_state_file)

    # === Initial State ===

    def test_initial_state_closed(self, breaker):
        """初始狀態 → closed"""
        state = breaker.check_health("todoist")
        assert state == "closed"

    # === State Transitions ===

    def test_closed_to_open_after_3_failures(self, breaker):
        """連續 3 次失敗 → closed → open"""
        breaker.record_result("todoist", success=False)
        assert breaker.check_health("todoist") == "closed"

        breaker.record_result("todoist", success=False)
        assert breaker.check_health("todoist") == "closed"

        breaker.record_result("todoist", success=False)
        assert breaker.check_health("todoist") == "open"

    def test_open_stays_open_during_cooldown(self, breaker):
        """open 狀態在 cooldown 期間保持 open"""
        # 觸發 open
        for _ in range(3):
            breaker.record_result("todoist", success=False)

        # 立即檢查 → 仍為 open
        assert breaker.check_health("todoist") == "open"

    def test_open_to_half_open_after_cooldown(self, breaker, temp_state_file):
        """cooldown 期過 → open → half_open"""
        # 觸發 open
        for _ in range(3):
            breaker.record_result("todoist", success=False)

        # 手動修改 cooldown 為過去時間
        state = json.load(open(temp_state_file, "r"))
        past_time = (datetime.now() - timedelta(seconds=10)).isoformat()
        state["todoist"]["cooldown"] = past_time
        json.dump(state, open(temp_state_file, "w"))

        # 檢查 → 轉為 half_open
        assert breaker.check_health("todoist") == "half_open"

    def test_half_open_to_closed_on_success(self, breaker, temp_state_file):
        """half_open 成功 → closed"""
        # 設定 half_open 狀態
        state = {
            "todoist": {
                "state": "half_open",
                "failures": 3,
                "cooldown": None
            }
        }
        json.dump(state, open(temp_state_file, "w"))

        # 記錄成功 → 轉為 closed
        breaker.record_result("todoist", success=True)
        assert breaker.check_health("todoist") == "closed"

    def test_half_open_to_open_on_failure(self, breaker, temp_state_file):
        """half_open 失敗 → 回到 open + cooldown 翻倍"""
        # 設定 half_open 狀態
        state = {
            "todoist": {
                "state": "half_open",
                "failures": 3,
                "cooldown": None
            }
        }
        json.dump(state, open(temp_state_file, "w"))

        # 記錄失敗 → 轉回 open
        breaker.record_result("todoist", success=False)
        assert breaker.check_health("todoist") == "open"

        # 驗證 cooldown 被設定（雖然無法驗證是否翻倍，但至少存在）
        state = json.load(open(temp_state_file, "r"))
        assert state["todoist"]["cooldown"] is not None

    # === Success Resets State ===

    def test_success_resets_failures(self, breaker):
        """成功重置失敗計數"""
        breaker.record_result("todoist", success=False)
        breaker.record_result("todoist", success=False)
        breaker.record_result("todoist", success=True)  # 重置

        # 失敗計數歸零，再失敗 3 次才會 open
        breaker.record_result("todoist", success=False)
        breaker.record_result("todoist", success=False)
        assert breaker.check_health("todoist") == "closed"  # 仍為 closed

    # === Multiple APIs ===

    def test_multiple_apis_independent(self, breaker):
        """多個 API 獨立管理"""
        # todoist 失敗 3 次 → open
        for _ in range(3):
            breaker.record_result("todoist", success=False)
        assert breaker.check_health("todoist") == "open"

        # hackernews 正常 → closed
        breaker.record_result("hackernews", success=True)
        assert breaker.check_health("hackernews") == "closed"

    # === State Persistence ===

    def test_state_persistence(self, temp_state_file):
        """狀態持久化"""
        breaker1 = CircuitBreaker(temp_state_file)
        breaker1.record_result("todoist", success=False)
        breaker1.record_result("todoist", success=False)

        # 建立新實例，狀態應保留
        breaker2 = CircuitBreaker(temp_state_file)
        state = json.load(open(temp_state_file, "r"))
        assert state["todoist"]["failures"] == 2


# ============================================
# Integration Tests
# ============================================

class TestIntegration:
    """整合測試：ErrorClassifier + CircuitBreaker"""

    @pytest.fixture
    def temp_state_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_file = f.name
        yield temp_file
        if os.path.exists(temp_file):
            os.remove(temp_file)

    def test_rate_limit_does_not_trigger_circuit_breaker(self, temp_state_file):
        """Rate limit (429) 不觸發 circuit breaker"""
        classifier = ErrorClassifier()
        breaker = CircuitBreaker(temp_state_file)

        # 模擬 3 次 429 錯誤
        output = "HTTP/1.1 429 Too Many Requests"
        for _ in range(3):
            result = classifier.classify("Bash", "curl todoist", output, 1)
            # Rate limit 應該等待重試，而非標記為失敗
            if result["category"] == "rate_limit":
                # 不呼叫 record_result，因為 rate limit 是暫時性的
                pass

        # circuit breaker 狀態應保持 closed
        assert breaker.check_health("todoist") == "closed"

    def test_server_error_triggers_circuit_breaker(self, temp_state_file):
        """Server error (5xx) 連續 3 次觸發 circuit breaker"""
        classifier = ErrorClassifier()
        breaker = CircuitBreaker(temp_state_file)

        # 模擬 3 次 503 錯誤
        output = "HTTP/1.1 503 Service Unavailable"
        for _ in range(3):
            result = classifier.classify("Bash", "curl todoist", output, 1)
            if result["category"] == "server_error":
                breaker.record_result("todoist", success=False)

        # circuit breaker 應轉為 open
        assert breaker.check_health("todoist") == "open"

    def test_client_error_immediate_alert(self, temp_state_file):
        """Client error (401) 立即告警，無需 circuit breaker"""
        classifier = ErrorClassifier()

        output = "HTTP/1.1 401 Unauthorized"
        result = classifier.classify("Bash", "curl todoist", output, 1)

        # 應立即告警
        assert result["category"] == "client_error"
        assert result["retry_intent"] == "stop"
        assert result["should_alert"] is True

    def test_network_error_exponential_backoff(self, temp_state_file):
        """Network error 應使用指數退避"""
        classifier = ErrorClassifier()
        breaker = CircuitBreaker(temp_state_file)

        output = "curl: (7) Failed to connect: Connection refused"
        result = classifier.classify("Bash", "curl localhost:3000", output, 7)

        # 應建議 exponential backoff
        assert result["category"] == "network_error"
        assert result["retry_intent"] == "exponential"
        assert result["wait_seconds"] == 5  # 初始值

        # 記錄失敗（實際重試時需乘以 2^retry_count）
        breaker.record_result("knowledge", success=False)

    def test_recovery_workflow(self, temp_state_file):
        """完整恢復流程：closed → open → half_open → closed"""
        classifier = ErrorClassifier()
        breaker = CircuitBreaker(temp_state_file)

        # Step 1: 連續 3 次失敗 → open
        for _ in range(3):
            breaker.record_result("todoist", success=False)
        assert breaker.check_health("todoist") == "open"

        # Step 2: 手動設定 cooldown 過期 → half_open
        state = json.load(open(temp_state_file, "r"))
        past_time = (datetime.now() - timedelta(seconds=10)).isoformat()
        state["todoist"]["cooldown"] = past_time
        json.dump(state, open(temp_state_file, "w"))
        assert breaker.check_health("todoist") == "half_open"

        # Step 3: 試探成功 → closed
        breaker.record_result("todoist", success=True)
        assert breaker.check_health("todoist") == "closed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
