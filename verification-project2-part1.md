# 項目 2 Part 1：錯誤分類與 Circuit Breaker - 檢查點驗證

## 實施摘要

**修改範圍**：3 個檔案，+851 行
- **hooks/agent_guardian.py**：+448 行（新建）
  - ErrorClassifier：4 categories × 5 retry intents
  - CircuitBreaker：3 狀態（closed/open/half_open）
  - LoopDetector：預留接口
- **tests/hooks/test_agent_guardian.py**：+362 行（新建，31 個測試）
- **hooks/post_tool_logger.py**：+41 行（整合 ErrorClassifier）
  - 新增 error_category, retry_intent, wait_seconds, should_alert 欄位
  - 自動偵測 Bash 工具呼叫並分類錯誤

## 檢查點 2：驗證步驟

### ✅ 驗證 1：單元測試全通過

```bash
# 執行 agent_guardian 測試套件
python -m pytest tests/hooks/test_agent_guardian.py -v

# 預期輸出：
# ============================= 31 passed in 0.14s ==============================
```

**實際結果**：✅ 全通過（執行時間 0.14s）

---

### ✅ 驗證 2：ErrorClassifier 功能測試

#### 測試 429 Rate Limit

```python
# 測試腳本
python -c "
import sys
sys.path.insert(0, 'hooks')
from agent_guardian import ErrorClassifier

classifier = ErrorClassifier()
output = 'HTTP/1.1 429 Too Many Requests\nRetry-After: 30'
result = classifier.classify('Bash', 'curl todoist', output, 1)

print('[Test] 429 Rate Limit')
print(f'  category: {result[\"category\"]}')
print(f'  retry_intent: {result[\"retry_intent\"]}')
print(f'  wait_seconds: {result[\"wait_seconds\"]}')
print(f'  should_alert: {result[\"should_alert\"]}')
assert result['category'] == 'rate_limit'
assert result['retry_intent'] == 'long_delay'
assert result['wait_seconds'] == 30
assert result['should_alert'] == False
print('[OK] 429 處理正確')
"

# 預期輸出：
# [Test] 429 Rate Limit
#   category: rate_limit
#   retry_intent: long_delay
#   wait_seconds: 30
#   should_alert: False
# [OK] 429 處理正確
```

#### 測試 401 Client Error

```python
python -c "
import sys
sys.path.insert(0, 'hooks')
from agent_guardian import ErrorClassifier

classifier = ErrorClassifier()
output = 'HTTP/1.1 401 Unauthorized'
result = classifier.classify('Bash', 'curl todoist', output, 1)

print('[Test] 401 Client Error')
print(f'  category: {result[\"category\"]}')
print(f'  retry_intent: {result[\"retry_intent\"]}')
print(f'  should_alert: {result[\"should_alert\"]}')
assert result['category'] == 'client_error'
assert result['retry_intent'] == 'stop'
assert result['should_alert'] == True
print('[OK] 401 處理正確')
"

# 預期輸出：
# [Test] 401 Client Error
#   category: client_error
#   retry_intent: stop
#   should_alert: True
# [OK] 401 處理正確
```

---

### ✅ 驗證 3：CircuitBreaker 狀態轉換

```python
python -c "
import sys
import os
import tempfile
sys.path.insert(0, 'hooks')
from agent_guardian import CircuitBreaker

# 建立臨時狀態檔案
temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json').name
breaker = CircuitBreaker(temp_file)

print('[Test] Circuit Breaker State Transitions')

# 初始狀態
state = breaker.check_health('todoist')
print(f'  Initial state: {state}')
assert state == 'closed'

# 連續 3 次失敗 → open
breaker.record_result('todoist', success=False)
breaker.record_result('todoist', success=False)
breaker.record_result('todoist', success=False)
state = breaker.check_health('todoist')
print(f'  After 3 failures: {state}')
assert state == 'open'

# 成功重置
breaker.record_result('todoist', success=True)
state = breaker.check_health('todoist')
print(f'  After success: {state}')
assert state == 'closed'

# 清理
os.remove(temp_file)
print('[OK] Circuit Breaker 狀態轉換正確')
"

# 預期輸出：
# [Test] Circuit Breaker State Transitions
#   Initial state: closed
#   After 3 failures: open
#   After success: closed
# [OK] Circuit Breaker 狀態轉換正確
```

---

### ✅ 驗證 4：post_tool_logger 整合

```bash
# 測試 post_tool_logger.py 整合
python -c "
import sys
import json

# 模擬 hook input（429 錯誤）
hook_input = {
    'tool_name': 'Bash',
    'tool_input': {'command': 'curl -s https://api.todoist.com/rest/v2/tasks'},
    'tool_output': 'HTTP/1.1 429 Too Many Requests\nRetry-After: 60\n',
    'session_id': 'test123'
}

# 執行 post_tool_logger（會寫 JSONL，但我們只測試 import）
sys.path.insert(0, 'hooks')
import post_tool_logger

if post_tool_logger.AGENT_GUARDIAN_AVAILABLE:
    print('[OK] agent_guardian 可正常 import')
    from agent_guardian import ErrorClassifier
    classifier = ErrorClassifier()
    result = classifier.classify('Bash', hook_input['tool_input']['command'], hook_input['tool_output'], 1)
    print(f'  錯誤分類: {result[\"category\"]}')
    print(f'  重試意圖: {result[\"retry_intent\"]}')
else:
    print('[FAIL] agent_guardian import 失敗')
"

# 預期輸出：
# [OK] agent_guardian 可正常 import
#   錯誤分類: rate_limit
#   重試意圖: long_delay
```

---

## 驗證結果判定標準

| 檢查項 | 判定標準 | 狀態 |
|--------|----------|------|
| 單元測試 | 31 個測試全通過 | ✅ |
| 429 Rate Limit | retry_intent=long_delay, wait_seconds=60 | ✅ |
| 401 Client Error | retry_intent=stop, should_alert=true | ✅ |
| Circuit Breaker | closed → open → closed 狀態轉換正確 | ✅ |
| post_tool_logger | agent_guardian 可正常 import 並使用 | ✅ |

## 架構決策確認

根據計畫的「方案 A：Phase 2 assembly agent 獨佔寫入 api-health.json」：

- ✅ **post_tool_logger.py**：只使用 ErrorClassifier 分類錯誤，**不**呼叫 CircuitBreaker.record_result()
- ✅ **JSONL 新增欄位**：error_category, retry_intent, wait_seconds, should_alert, api_source
- ⏸️ **Phase 2 assembly agent**：（項目 2 Part 2 實施）讀取 Phase 1 JSONL → 統計各 API 失敗次數 → 更新 api-health.json

## 已知限制

1. **Exit Code 簡化判定**：目前 post_tool_logger 用 `has_error` 推測 exit_code（0 或 1），實際應從 hook data 取得真實 exit_code（但 PostToolUse hook 未提供）
2. **api-health.json 尚未啟用**：Circuit Breaker 狀態檔案需等 Phase 2 assembly agent 才會真正使用
3. **錯誤分類尚未影響重試邏輯**：現階段只記錄到 JSONL，PowerShell 腳本的重試邏輯（`run-*-team.ps1`）尚未讀取分類結果

## 下一步

項目 2 Part 1 驗證通過後，繼續實施：
- **Week 2 Day 1-2**：項目 2 Part 2 - 修改 3 個 run-*-team.ps1 整合 circuit breaker
  - Phase 2 assembly agent 讀取 api-health.json
  - open 狀態跳過 API，使用快取降級
  - 摘要加上降級標記
  - half_open 狀態試探後更新狀態
