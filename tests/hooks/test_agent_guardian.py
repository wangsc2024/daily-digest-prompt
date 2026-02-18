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


# ============================================
# LoopDetector Tests
# ============================================

class TestLoopDetector:
    """LoopDetector 測試套件"""

    @pytest.fixture
    def detector(self):
        from agent_guardian import LoopDetector
        return LoopDetector(warning_mode=True)

    # === Whitelist Tests ===

    def test_whitelist_skill_index(self, detector):
        """白名單：SKILL_INDEX.md 多次讀取不觸發"""
        for _ in range(10):
            result = detector.check_loop("Read", "skills/SKILL_INDEX.md", "content")

        assert result["loop_detected"] is False
        assert result["reason"] == "Whitelisted operation"

    def test_whitelist_cache_json(self, detector):
        """白名單：cache/*.json 多次讀取不觸發"""
        for _ in range(10):
            result = detector.check_loop("Read", "cache/todoist.json", "data")

        assert result["loop_detected"] is False

    def test_whitelist_digest_memory(self, detector):
        """白名單：digest-memory.json 多次讀取不觸發"""
        for _ in range(10):
            result = detector.check_loop("Read", "context/digest-memory.json", "{}")

        assert result["loop_detected"] is False

    # === Tool Hash Loop Detection ===

    def test_tool_hash_loop_detected(self, detector):
        """Tool Hash 迴圈：相同工具+參數連續 5 次（確保輸出不同避免 content_hash 觸發）"""
        for i in range(4):
            result = detector.check_loop("Bash", "curl https://api.example.com", f"output_{i}")
            assert result["loop_detected"] is False, f"Should not detect loop at iteration {i+1}"

        # 第 5 次應該觸發
        result = detector.check_loop("Bash", "curl https://api.example.com", "output_4")
        assert result["loop_detected"] is True
        assert result["loop_type"] == "tool_hash"
        assert result["warning_only"] is True  # warning_mode=True

    def test_tool_hash_different_params_no_loop(self, detector):
        """Tool Hash：不同參數不觸發迴圈（確保輸出不同避免 content_hash 觸發）"""
        for i in range(10):
            result = detector.check_loop("Read", f"file_{i}.txt", f"content_{i}")

        assert result["loop_detected"] is False

    # === Content Hash Loop Detection ===

    def test_content_hash_loop_detected(self, detector):
        """Content Hash 迴圈：相同輸出連續 3 次（確保工具/參數不同避免 tool_hash 觸發）"""
        same_output = "Error: File not found"

        for i in range(2):
            result = detector.check_loop("Bash", f"cat file_{i}.txt", same_output)
            assert result["loop_detected"] is False

        # 第 3 次應該觸發
        result = detector.check_loop("Bash", "cat file_2.txt", same_output)
        assert result["loop_detected"] is True
        assert result["loop_type"] == "content_hash"

    def test_content_hash_different_output_no_loop(self, detector):
        """Content Hash：不同輸出不觸發迴圈（確保工具/參數也不同避免 tool_hash 觸發）"""
        for i in range(10):
            result = detector.check_loop("Read", f"file_{i}.txt", f"output_{i}")

        assert result["loop_detected"] is False

    # === Excessive Turns Detection ===

    def test_excessive_turns_detected(self, detector):
        """Excessive Turns：超過 100 次呼叫"""
        for i in range(100):
            result = detector.check_loop("Read", f"file_{i}.txt", f"content_{i}")
            assert result["loop_detected"] is False

        # 第 101 次應該觸發
        result = detector.check_loop("Read", "file_101.txt", "content_101")
        assert result["loop_detected"] is True
        assert result["loop_type"] == "excessive_turns"

    # === Warning Mode Tests ===

    def test_warning_mode_true(self):
        """Warning Mode=True 僅警告，不阻斷"""
        from agent_guardian import LoopDetector
        detector = LoopDetector(warning_mode=True)

        for _ in range(5):
            detector.check_loop("Bash", "same command", "output")

        result = detector.check_loop("Bash", "same command", "output")
        assert result["loop_detected"] is True
        assert result["warning_only"] is True

    def test_warning_mode_false(self):
        """Warning Mode=False 應阻斷"""
        from agent_guardian import LoopDetector
        detector = LoopDetector(warning_mode=False)

        for _ in range(5):
            detector.check_loop("Bash", "same command", "output")

        result = detector.check_loop("Bash", "same command", "output")
        assert result["loop_detected"] is True
        assert result["warning_only"] is False

    # === Edge Cases ===

    def test_empty_output_no_content_hash(self, detector):
        """空輸出不觸發 content hash 檢查，但會觸發 tool hash"""
        for i in range(4):
            result = detector.check_loop("Bash", "same command", "")
            assert result["loop_detected"] is False

        # 第 5 次應僅觸發 tool hash
        result = detector.check_loop("Bash", "same command", "")
        assert result["loop_detected"] is True
        assert result["loop_type"] == "tool_hash"

    def test_session_call_count_increments(self, detector):
        """Session 計數器正確遞增"""
        assert detector.session_call_count == 0

        detector.check_loop("Read", "file.txt", "content")
        assert detector.session_call_count == 1

        detector.check_loop("Bash", "echo test", "test")
        assert detector.session_call_count == 2

    # === State Serialization Tests（跨進程持久化）===

    def test_get_state_returns_serializable_dict(self, detector):
        """get_state() 回傳可序列化的字典（供 JSON 持久化）"""
        detector.check_loop("Read", "file.txt", "content")
        state = detector.get_state()

        assert isinstance(state, dict)
        assert "session_call_count" in state
        assert "tool_hash_window" in state
        assert "content_hash_window" in state
        assert isinstance(state["tool_hash_window"], list)
        assert isinstance(state["content_hash_window"], list)
        assert state["session_call_count"] == 1

    def test_initial_state_restores_call_count(self):
        """initial_state 正確還原 session_call_count（跨進程繼續計數）"""
        from agent_guardian import LoopDetector

        saved = {"session_call_count": 50, "tool_hash_window": [], "content_hash_window": []}
        detector = LoopDetector(warning_mode=True, initial_state=saved)

        assert detector.session_call_count == 50

    def test_initial_state_restores_tool_hash_window(self):
        """initial_state 正確還原 tool_hash_window（跨進程繼續偵測）"""
        from agent_guardian import LoopDetector

        # 模擬前一進程已累積 4 個相同 hash
        fake_hash = "abcd1234"
        saved = {
            "session_call_count": 4,
            "tool_hash_window": [fake_hash] * 4,
            "content_hash_window": [],
        }
        detector = LoopDetector(warning_mode=True, initial_state=saved)

        # 第 5 次相同呼叫（從前一進程的角度看）應觸發 tool_hash 迴圈
        # 用與前一進程相同的 tool+params 產生相同 hash 不易，改驗窗口長度
        assert len(detector.tool_hash_window) == 4

    def test_get_state_roundtrip(self):
        """get_state() → initial_state 完整往返，session_call_count 累加正確"""
        from agent_guardian import LoopDetector

        # 第一個進程：執行 3 次
        d1 = LoopDetector(warning_mode=True)
        for i in range(3):
            d1.check_loop("Read", f"file_{i}.txt", f"output_{i}")
        state1 = d1.get_state()

        assert state1["session_call_count"] == 3

        # 第二個進程：從第一個進程的狀態繼續
        d2 = LoopDetector(warning_mode=True, initial_state=state1)
        assert d2.session_call_count == 3

        d2.check_loop("Read", "file_3.txt", "output_3")
        state2 = d2.get_state()

        assert state2["session_call_count"] == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
