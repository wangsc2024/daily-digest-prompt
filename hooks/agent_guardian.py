#!/usr/bin/env python3
"""
Agent Guardian - Error Classification, Circuit Breaker & Loop Detection

綜合模組整合三大守護機制：
  1. ErrorClassifier: 分類錯誤並返回重試策略
  2. CircuitBreaker: API 可用性追蹤與狀態管理
  3. LoopDetector: 偵測工具呼叫迴圈（跨進程狀態持久化，整合於 post_tool_logger.py）

使用方式：
  from agent_guardian import ErrorClassifier, CircuitBreaker, LoopDetector

  classifier = ErrorClassifier()
  result = classifier.classify("Bash", "curl ...", output, exit_code)

  breaker = CircuitBreaker("state/api-health.json")
  state = breaker.check_health("todoist")
  breaker.record_result("todoist", success=True)

  # 跨進程使用（PostToolUse hook）：
  detector = LoopDetector(warning_mode=True, initial_state=saved_state)
  result = detector.check_loop(tool, params, output)
  saved_state = detector.get_state()  # 寫回 state/loop-state-{sid}.json
"""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List

# Import shared API source patterns and regex cache
try:
    from hook_utils import API_SOURCE_PATTERNS, get_compiled_regex
except ImportError:
    API_SOURCE_PATTERNS = {
        "todoist": ["todoist.com", "todoist"],
        "pingtung-news": ["ptnews-mcp", "pingtung"],
        "hackernews": ["hacker-news.firebaseio", "hn.algolia"],
        "knowledge": ["localhost:3000"],
        "ntfy": ["ntfy.sh"],
        "gmail": ["gmail.googleapis"],
    }

    # Standalone fallback: simple cache for compiled regex
    _standalone_regex_cache: dict = {}

    def get_compiled_regex(pattern: str, flags: int = 0):
        key = (pattern, flags)
        if key not in _standalone_regex_cache:
            _standalone_regex_cache[key] = re.compile(pattern, flags)
        return _standalone_regex_cache[key]


# ============================================
# Error Classifier
# ============================================

class ErrorClassifier:
    """
    分類錯誤並返回重試策略。

    4 大錯誤分類：
      - rate_limit (429): 等待 Retry-After 或 60s
      - server_error (500-504): 使用快取降級
      - client_error (401, 403): 停止重試，立即告警
      - network_error (timeout, connection refused): 指數退避

    5 種重試意圖：
      - immediate: 立即重試
      - exponential: 指數退避（2^n × 5s，最多 3 次）
      - long_delay: 長時間延遲（從 Retry-After header 讀取或預設 60s）
      - use_cache: 跳過重試，直接用快取
      - stop: 停止重試，發送告警
    """

    # HTTP 狀態碼 pattern
    HTTP_STATUS_PATTERNS = [
        (r"HTTP/\d\.\d\s+(\d{3})", "http_status"),  # HTTP/1.1 429
        (r"status:\s*(\d{3})", "status_code"),      # status: 429
        (r"Error\s+(\d{3})", "error_code"),         # Error 429
    ]

    # Retry-After header pattern
    RETRY_AFTER_PATTERN = r"Retry-After:\s*(\d+)"

    # Connection error keywords
    CONNECTION_ERRORS = [
        "connection refused",
        "connection timed out",
        "connection reset",
        "network unreachable",
        "timeout",
        "timed out",
        "name or service not known",
        "temporary failure in name resolution",
        "could not resolve host",
    ]

    def classify(
        self,
        tool_name: str,
        command: str,
        output: str,
        exit_code: int
    ) -> Dict:
        """
        分類錯誤並返回重試策略。

        Returns:
          {
            "category": "rate_limit" | "server_error" | "client_error" | "network_error" | "success",
            "retry_intent": "immediate" | "exponential" | "long_delay" | "use_cache" | "stop",
            "wait_seconds": int,
            "should_alert": bool,
            "api_source": str | None,
            "details": str
          }
        """
        # 成功案例
        if exit_code == 0:
            return {
                "category": "success",
                "retry_intent": None,
                "wait_seconds": 0,
                "should_alert": False,
                "api_source": None,
                "details": "Command executed successfully"
            }

        # 偵測 API 來源
        api_source = self._detect_api_source(command)

        # 提取 HTTP 狀態碼
        http_status = self._extract_http_status(output)

        # 分類錯誤
        if http_status == 429:
            # Rate Limit
            retry_after = self._extract_retry_after(output)
            return {
                "category": "rate_limit",
                "retry_intent": "long_delay",
                "wait_seconds": retry_after if retry_after else 60,
                "should_alert": False,
                "api_source": api_source,
                "details": f"Rate limit hit, retry after {retry_after or 60}s"
            }

        elif http_status and 500 <= http_status <= 504:
            # Server Error
            return {
                "category": "server_error",
                "retry_intent": "use_cache",
                "wait_seconds": 0,
                "should_alert": True,  # 連續 3 次後告警
                "api_source": api_source,
                "details": f"Server error {http_status}, use cache fallback"
            }

        elif http_status in [401, 403]:
            # Client Error (認證失效)
            return {
                "category": "client_error",
                "retry_intent": "stop",
                "wait_seconds": 0,
                "should_alert": True,  # 立即告警
                "api_source": api_source,
                "details": f"Auth error {http_status}, token may be expired"
            }

        elif self._is_connection_error(output):
            # Network Error
            return {
                "category": "network_error",
                "retry_intent": "exponential",
                "wait_seconds": 5,  # 初始值，實際使用時需乘以 2^retry_count
                "should_alert": True,  # 連續 3 次後告警
                "api_source": api_source,
                "details": "Connection error, use exponential backoff"
            }

        else:
            # 未分類錯誤
            return {
                "category": "unknown",
                "retry_intent": "exponential",
                "wait_seconds": 10,
                "should_alert": True,
                "api_source": api_source,
                "details": f"Unknown error (exit code {exit_code})"
            }

    def _detect_api_source(self, command: str) -> Optional[str]:
        """偵測 API 來源（使用 hook_utils.API_SOURCE_PATTERNS 共用定義）"""
        lower_cmd = command.lower()
        for source, patterns in API_SOURCE_PATTERNS.items():
            if any(p in lower_cmd for p in patterns):
                return source
        return None

    def _extract_http_status(self, output: str) -> Optional[int]:
        """提取 HTTP 狀態碼"""
        for pattern, _ in self.HTTP_STATUS_PATTERNS:
            match = get_compiled_regex(pattern, re.IGNORECASE).search(output)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        return None

    def _extract_retry_after(self, output: str) -> Optional[int]:
        """提取 Retry-After header 值（秒）"""
        match = get_compiled_regex(self.RETRY_AFTER_PATTERN, re.IGNORECASE).search(output)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    def _is_connection_error(self, output: str) -> bool:
        """判斷是否為連線錯誤"""
        lower_output = output.lower()
        return any(keyword in lower_output for keyword in self.CONNECTION_ERRORS)


# ============================================
# Circuit Breaker
# ============================================

class CircuitBreaker:
    """
    API 可用性追蹤與狀態管理（Circuit Breaker Pattern）。

    3 種狀態：
      - closed: 正常運作，允許所有請求
      - open: 故障狀態，拒絕所有請求（使用快取）
      - half_open: 試探狀態，允許單次請求測試恢復

    狀態轉換：
      - closed → open: 連續 3 次失敗（5xx/timeout/connection refused）
      - open → half_open: cooldown 5 分鐘後
      - half_open → closed: 試探成功
      - half_open → open: 試探失敗，cooldown 時間翻倍（10 分鐘）

    狀態檔案格式（state/api-health.json）：
      {
        "todoist": {
          "state": "closed",
          "failures": 0,
          "cooldown": null
        },
        ...
      }
    """

    # 狀態常數
    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    # 設定常數
    FAILURE_THRESHOLD = 3  # 連續失敗 3 次觸發 open
    COOLDOWN_SECONDS = 300  # 5 分鐘（初始 cooldown）
    COOLDOWN_MAX_SECONDS = 1200  # 20 分鐘（最大 cooldown）

    def __init__(self, state_file: str):
        """
        Args:
          state_file: API 健康狀態檔案路徑（JSON）
        """
        self.state_file = state_file
        self._ensure_state_file()

    def _ensure_state_file(self):
        """確保狀態檔案存在"""
        if not os.path.exists(self.state_file):
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            self._save_state({})

    def _load_state(self) -> Dict:
        """載入狀態"""
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: Dict):
        """保存狀態（原子寫入，防止並行 Agent 競態損壞）"""
        try:
            from hook_utils import atomic_write_json
            atomic_write_json(self.state_file, state)
        except ImportError:
            # Fallback：hook_utils 不可用時退回直接寫入
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

    def _atomic_update(self, updater):
        """
        以檔案鎖保護的 read-modify-write 操作。

        避免團隊模式中多個並行 Agent 同時讀寫 api-health.json
        導致狀態覆蓋（競態條件）。

        Args:
          updater: callable(state_dict) -> None，原地修改 state dict
        """
        lock_path = self.state_file + ".lock"
        lock_fd = None
        try:
            # 取得檔案鎖（跨平台）
            lock_fd = open(lock_path, "w")
            try:
                import msvcrt
                msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            except (ImportError, OSError):
                try:
                    import fcntl
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (ImportError, OSError):
                    pass  # 無鎖可用時退化為無鎖模式

            state = self._load_state()
            updater(state)
            self._save_state(state)
        finally:
            if lock_fd:
                lock_fd.close()
                try:
                    os.remove(lock_path)
                except OSError:
                    pass

    def _get_api_state(self, api_source: str) -> Dict:
        """取得特定 API 的狀態"""
        state = self._load_state()
        if api_source not in state:
            def _init(s):
                s[api_source] = {
                    "state": self.STATE_CLOSED,
                    "failures": 0,
                    "cooldown": None
                }
            self._atomic_update(_init)
            state = self._load_state()
        return state[api_source]

    def check_health(self, api_source: str) -> str:
        """
        檢查 API 健康狀態。

        Returns:
          "closed" | "open" | "half_open"
        """
        api_state = self._get_api_state(api_source)
        current_state = api_state["state"]

        # 若為 open 狀態，檢查是否已過 cooldown 期
        if current_state == self.STATE_OPEN:
            cooldown_str = api_state.get("cooldown")
            if cooldown_str:
                cooldown_time = datetime.fromisoformat(cooldown_str)
                if datetime.now() >= cooldown_time:
                    # cooldown 期過，轉為 half_open
                    self._update_state(api_source, self.STATE_HALF_OPEN, failures=api_state["failures"])
                    return self.STATE_HALF_OPEN

        return current_state

    def record_result(self, api_source: str, success: bool):
        """
        記錄 API 呼叫結果並更新狀態。

        Args:
          api_source: API 來源（如 "todoist"）
          success: 是否成功
        """
        api_state = self._get_api_state(api_source)
        current_state = api_state["state"]
        failures = api_state["failures"]

        if success:
            # 成功 → 重置失敗計數，狀態轉為 closed
            self._update_state(api_source, self.STATE_CLOSED, failures=0)
        else:
            # 失敗處理
            if current_state == self.STATE_CLOSED:
                failures += 1
                if failures >= self.FAILURE_THRESHOLD:
                    # 達到閾值 → 轉為 open，設定 cooldown
                    cooldown = datetime.now() + timedelta(seconds=self.COOLDOWN_SECONDS)
                    self._update_state(api_source, self.STATE_OPEN, failures=failures, cooldown=cooldown)
                else:
                    # 未達閾值 → 保持 closed，累積失敗計數
                    self._update_state(api_source, self.STATE_CLOSED, failures=failures)

            elif current_state == self.STATE_HALF_OPEN:
                # half_open 狀態試探失敗 → 轉回 open，cooldown 翻倍
                cooldown_seconds = min(self.COOLDOWN_SECONDS * 2, self.COOLDOWN_MAX_SECONDS)
                cooldown = datetime.now() + timedelta(seconds=cooldown_seconds)
                self._update_state(api_source, self.STATE_OPEN, failures=failures, cooldown=cooldown)

    def _update_state(
        self,
        api_source: str,
        new_state: str,
        failures: int,
        cooldown: Optional[datetime] = None
    ):
        """更新狀態（使用檔案鎖避免競態條件）"""
        def _do_update(state):
            state[api_source] = {
                "state": new_state,
                "failures": failures,
                "cooldown": cooldown.isoformat() if cooldown else None
            }
        self._atomic_update(_do_update)


# ============================================
# Loop Detector
# ============================================

from collections import deque
import hashlib


class LoopDetector:
    """
    偵測工具呼叫迴圈（Loop Detection）。

    3 層偵測演算法：
      1. Tool Hash 重複：同一工具 + 相同參數連續呼叫 ≥5 次
      2. Content 重複：相同 output 連續出現 ≥3 次（SHA-256 hash）
      3. Excessive Turns：單一 session 超過 100 個 tool calls

    白名單機制：
      - 允許重複：SKILL_INDEX.md 讀取（正常載入 + 路由 + 驗證）
      - 允許重複：cache/*.json 讀取（降級模式可能多次查詢快取）

    警告模式（2 週觀察期）：
      - 不阻斷執行，只記錄到 JSONL（tags: ["loop-suspected"]）
      - 累積數據後調整閾值
    """

    # 閾值設定
    TOOL_HASH_THRESHOLD = 5       # Tool Hash 重複閾值
    CONTENT_HASH_THRESHOLD = 3    # Content Hash 重複閾值
    EXCESSIVE_TURNS_THRESHOLD = 100  # Session 呼叫次數閾值

    # 白名單 patterns
    WHITELIST_PATTERNS = [
        r"SKILL_INDEX\.md$",
        r"cache/.*\.json$",
        r"digest-memory\.json$",
        r"scheduler-state\.json$",
        r"api-health\.json$",
        r"state/loop-state-[0-9a-f]{8}\.json$",
    ]

    def __init__(self, warning_mode: bool = True, initial_state: dict = None):
        """
        初始化迴圈偵測器。

        Args:
          warning_mode: True=僅警告，False=阻斷執行（預設為 True，2 週觀察期）
          initial_state: 從 JSON 還原的跨進程持久化狀態（PostToolUse hook 使用）
        """
        self.warning_mode = warning_mode
        if initial_state:
            self.session_call_count = initial_state.get("session_call_count", 0)
            self.tool_hash_window = deque(
                initial_state.get("tool_hash_window", []),
                maxlen=self.TOOL_HASH_THRESHOLD
            )
            self.content_hash_window = deque(
                initial_state.get("content_hash_window", []),
                maxlen=self.CONTENT_HASH_THRESHOLD
            )
        else:
            self.tool_hash_window = deque(maxlen=self.TOOL_HASH_THRESHOLD)
            self.content_hash_window = deque(maxlen=self.CONTENT_HASH_THRESHOLD)
            self.session_call_count = 0

    def get_state(self) -> dict:
        """序列化當前狀態為字典，供跨進程持久化使用。"""
        return {
            "session_call_count": self.session_call_count,
            "tool_hash_window": list(self.tool_hash_window),
            "content_hash_window": list(self.content_hash_window),
        }

    def check_loop(
        self,
        tool_name: str,
        params_summary: str,
        output_snippet: str
    ) -> Dict:
        """
        檢查是否存在迴圈。

        Args:
          tool_name: 工具名稱（如 "Read", "Bash"）
          params_summary: 參數摘要（如檔案路徑、命令片段）
          output_snippet: 輸出片段（前 500 字元）

        Returns:
          {
            "loop_detected": bool,       # 是否偵測到迴圈
            "loop_type": str | None,     # tool_hash / content_hash / excessive_turns
            "warning_only": bool,        # 是否僅警告
            "reason": str,               # 詳細原因
          }
        """
        self.session_call_count += 1

        # 檢查白名單
        if self._is_whitelisted(params_summary):
            return {
                "loop_detected": False,
                "loop_type": None,
                "warning_only": False,
                "reason": "Whitelisted operation",
            }

        # 檢查 1：Tool Hash 重複
        tool_hash = self._compute_tool_hash(tool_name, params_summary)
        self.tool_hash_window.append(tool_hash)

        if len(self.tool_hash_window) == self.TOOL_HASH_THRESHOLD:
            if len(set(self.tool_hash_window)) == 1:
                # 所有 hash 相同 → 重複呼叫
                return {
                    "loop_detected": True,
                    "loop_type": "tool_hash",
                    "warning_only": self.warning_mode,
                    "reason": f"同一工具+參數連續呼叫 {self.TOOL_HASH_THRESHOLD} 次",
                }

        # 檢查 2：Content Hash 重複
        if output_snippet:  # 只有有輸出時才檢查
            content_hash = self._compute_content_hash(output_snippet)
            self.content_hash_window.append(content_hash)

            if len(self.content_hash_window) == self.CONTENT_HASH_THRESHOLD:
                if len(set(self.content_hash_window)) == 1:
                    # 所有 output 相同 → 重複輸出
                    return {
                        "loop_detected": True,
                        "loop_type": "content_hash",
                        "warning_only": self.warning_mode,
                        "reason": f"相同輸出連續出現 {self.CONTENT_HASH_THRESHOLD} 次",
                    }

        # 檢查 3：Excessive Turns
        if self.session_call_count > self.EXCESSIVE_TURNS_THRESHOLD:
            return {
                "loop_detected": True,
                "loop_type": "excessive_turns",
                "warning_only": self.warning_mode,
                "reason": f"Session 呼叫次數超過 {self.EXCESSIVE_TURNS_THRESHOLD}",
            }

        return {
            "loop_detected": False,
            "loop_type": None,
            "warning_only": False,
            "reason": "No loop detected",
        }

    def _is_whitelisted(self, params_summary: str) -> bool:
        """檢查是否在白名單中。"""
        for pattern in self.WHITELIST_PATTERNS:
            if get_compiled_regex(pattern).search(params_summary):
                return True
        return False

    def _compute_tool_hash(self, tool_name: str, params_summary: str) -> str:
        """計算 tool + params 的 hash。"""
        combined = f"{tool_name}:{params_summary}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _compute_content_hash(self, output_snippet: str) -> str:
        """計算 output 的 hash。"""
        # 只取前 500 字元避免過長
        snippet = output_snippet[:500] if len(output_snippet) > 500 else output_snippet
        return hashlib.sha256(snippet.encode()).hexdigest()[:16]
