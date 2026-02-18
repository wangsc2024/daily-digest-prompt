# Circuit Breaker 端到端測試計畫

## 測試目標

驗證 Circuit Breaker 機制在生產環境的實際效果，確保：
1. API 錯誤正確記錄到 JSONL 日誌
2. Circuit Breaker 狀態轉換正確（closed → open → half_open → closed）
3. ntfy 告警正確觸發（含 trace_id + error details）
4. Assembly agent 根據 api-health.json 加降級標記（待實施）

## 測試架構

```
測試腳本 → 模擬 API 錯誤 → post_tool_logger.py → JSONL 日誌
                                ↓
                  assemble-digest.md Step 1.5 → CircuitBreaker → api-health.json
                                ↓
                         on_stop_alert.py → ntfy 告警
```

## 測試場景

### 場景 1：單次 API 錯誤記錄（基礎功能）

**目標**：驗證 API 錯誤正確記錄到 JSONL

**步驟**：
1. 清空今日 JSONL 日誌（`logs/structured/YYYY-MM-DD.jsonl`）
2. 執行 Bash 指令模擬 Todoist 401 錯誤：
   ```bash
   curl -s -H "Authorization: Bearer INVALID_TOKEN" https://api.todoist.com/rest/v2/tasks
   ```
3. 檢查 post_tool_logger.py 是否記錄錯誤

**預期結果**：
- JSONL 含 `"tool": "Bash"`, `"has_error": true`, `"tags": ["api-call", "todoist", "error"]`
- error 欄位含 HTTP 401 或 "Invalid token"

### 場景 2：Circuit Breaker 記錄單次失敗（未達閾值）

**目標**：驗證 Circuit Breaker 記錄失敗但不轉 open（failures < 3）

**步驟**：
1. 建立測試 JSONL：
   ```jsonl
   {"ts":"2026-02-17T20:30:00+08:00","sid":"test-001","tool":"Bash","event":"post","summary":"curl todoist","output":"HTTP 401","has_error":true,"tags":["api-call","todoist","error"]}
   ```
2. 執行 Step 1.5 的 Python 腳本（從 assemble-digest.md 抽取）
3. 檢查 `state/api-health.json`

**預期結果**：
```json
{
  "todoist": {
    "state": "closed",
    "failures": 1,
    "last_failure_time": "2026-02-17T20:30:00+08:00",
    "cooldown_until": null
  }
}
```

### 場景 3：連續 3 次失敗轉 open

**目標**：驗證連續失敗達閾值後 Circuit Breaker 轉 open

**步驟**：
1. 建立測試 JSONL（3 次失敗記錄）：
   ```jsonl
   {"ts":"2026-02-17T20:30:00+08:00","sid":"test-001","tool":"Bash","event":"post","summary":"curl todoist","output":"HTTP 401","has_error":true,"tags":["api-call","todoist","error"]}
   {"ts":"2026-02-17T20:31:00+08:00","sid":"test-001","tool":"Bash","event":"post","summary":"curl todoist","output":"HTTP 401","has_error":true,"tags":["api-call","todoist","error"]}
   {"ts":"2026-02-17T20:32:00+08:00","sid":"test-001","tool":"Bash","event":"post","summary":"curl todoist","output":"HTTP 401","has_error":true,"tags":["api-call","todoist","error"]}
   ```
2. 執行 Circuit Breaker 更新腳本
3. 檢查 api-health.json

**預期結果**：
```json
{
  "todoist": {
    "state": "open",
    "failures": 3,
    "last_failure_time": "2026-02-17T20:32:00+08:00",
    "cooldown_until": "2026-02-17T20:37:00+08:00"  // +5 分鐘
  }
}
```

### 場景 4：Cooldown 未過期保持 open

**目標**：驗證 cooldown 期間 Circuit Breaker 保持 open 狀態

**步驟**：
1. 延續場景 3 的 api-health.json
2. 立即（cooldown 未過期）再次呼叫 `circuit_breaker.get_state("todoist")`
3. 檢查回傳狀態

**預期結果**：
- `get_state()` 回傳 `"open"`
- api-health.json 保持不變

### 場景 5：Cooldown 過期轉 half_open

**目標**：驗證 cooldown 過期後自動轉 half_open

**步驟**：
1. 手動修改 api-health.json 的 `cooldown_until` 為過去時間：
   ```json
   {
     "todoist": {
       "state": "open",
       "failures": 3,
       "last_failure_time": "2026-02-17T20:32:00+08:00",
       "cooldown_until": "2026-02-17T20:33:00+08:00"  // 已過期
     }
   }
   ```
2. 呼叫 `circuit_breaker.get_state("todoist")`
3. 檢查 api-health.json 是否自動更新

**預期結果**：
- `get_state()` 回傳 `"half_open"`
- api-health.json 更新為：
  ```json
  {
    "todoist": {
      "state": "half_open",
      "failures": 3,
      "last_failure_time": "2026-02-17T20:32:00+08:00",
      "cooldown_until": null
    }
  }
  ```

### 場景 6：試探成功轉 closed

**目標**：驗證 half_open 狀態下試探成功轉 closed

**步驟**：
1. 延續場景 5 的 api-health.json（state=half_open）
2. 建立成功的 JSONL 記錄：
   ```jsonl
   {"ts":"2026-02-17T20:40:00+08:00","sid":"test-002","tool":"Bash","event":"post","summary":"curl todoist","output":"[{\"id\":\"123\"}]","has_error":false,"tags":["api-call","todoist"]}
   ```
3. 執行 Circuit Breaker 更新腳本（`record_result("todoist", success=True)`）
4. 檢查 api-health.json

**預期結果**：
```json
{
  "todoist": {
    "state": "closed",
    "failures": 0,
    "last_failure_time": null,
    "cooldown_until": null
  }
}
```

### 場景 7：ntfy 告警機制（整合測試）

**目標**：驗證 on_stop_alert.py 偵測錯誤並發送 ntfy 告警

**步驟**：
1. 建立包含錯誤的 JSONL 日誌（≥1 筆錯誤）
2. 手動執行 `python hooks/on_stop_alert.py` 並傳入 session summary：
   ```json
   {
     "session_id": "test-alert-001",
     "total_calls": 5,
     "errors": 2,
     "blocked": 0
   }
   ```
3. 檢查 ntfy.sh/wangsc2025 是否收到告警

**預期結果**：
- ntfy 收到 warning 級別告警（priority 4）
- 告警訊息含：
  - session_id
  - 錯誤統計（2 errors）
  - 錯誤詳情（至少列出前 5 筆）

### 場景 8：降級標記自動加註（待實施）

**目標**：驗證 assembly agent 根據 api-health.json 加降級標記

**步驟**：
1. 設定 api-health.json 為 open 或 half_open：
   ```json
   {
     "todoist": {"state": "open", "failures": 3, ...},
     "pingtung-news": {"state": "closed", "failures": 0, ...}
   }
   ```
2. 執行 assemble-digest.md（或手動測試相關邏輯）
3. 檢查生成的摘要內容

**預期結果**：
- 摘要含「⚠️ Todoist API 暫時故障，使用快取資料」
- pingtung-news 正常顯示（無降級標記）

## 測試工具

### 工具 1：Circuit Breaker 更新腳本（從 assemble-digest.md 抽取）

建立獨立測試腳本 `test-circuit-breaker-update.py`：
```python
import json
import sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, 'hooks')
from agent_guardian import CircuitBreaker

# 讀取測試 JSONL
jsonl_path = sys.argv[1] if len(sys.argv) > 1 else "logs/structured/test-circuit-breaker.jsonl"

# 統計各 API 呼叫結果
api_results = {}
with open(jsonl_path, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line.strip())
        if 'api-call' in entry.get('tags', []):
            for tag in entry['tags']:
                if tag in ['todoist', 'pingtung-news', 'hackernews', 'gmail']:
                    api_results.setdefault(tag, []).append(not entry.get('has_error', False))

# 更新 Circuit Breaker
breaker = CircuitBreaker("state/api-health.json")
for api_source, results in api_results.items():
    last_result = results[-1] if results else True
    breaker.record_result(api_source, success=last_result)
    print(f"Updated {api_source}: {len(results)} calls, last={last_result}")

# 顯示最終狀態
print("\n[最終狀態]")
for api in ['todoist', 'pingtung-news', 'hackernews', 'gmail']:
    state = breaker.get_state(api)
    print(f"{api}: {state}")
```

### 工具 2：JSONL 產生器

建立測試 JSONL 的輔助函式：
```python
import json
from datetime import datetime, timedelta

def generate_test_jsonl(output_path, scenario):
    """
    scenario: "single_error", "triple_failure", "success_after_failure"
    """
    base_time = datetime.now()
    entries = []

    if scenario == "single_error":
        entries.append({
            "ts": base_time.isoformat(),
            "sid": "test-001",
            "tool": "Bash",
            "event": "post",
            "summary": "curl todoist API",
            "output": "HTTP 401 Unauthorized",
            "has_error": True,
            "tags": ["api-call", "todoist", "error"]
        })
    elif scenario == "triple_failure":
        for i in range(3):
            entries.append({
                "ts": (base_time + timedelta(minutes=i)).isoformat(),
                "sid": "test-001",
                "tool": "Bash",
                "event": "post",
                "summary": f"curl todoist API (attempt {i+1})",
                "output": "HTTP 401 Unauthorized",
                "has_error": True,
                "tags": ["api-call", "todoist", "error"]
            })
    elif scenario == "success_after_failure":
        # 3 次失敗
        for i in range(3):
            entries.append({
                "ts": (base_time + timedelta(minutes=i)).isoformat(),
                "sid": "test-001",
                "tool": "Bash",
                "event": "post",
                "summary": f"curl todoist API (failure {i+1})",
                "output": "HTTP 401 Unauthorized",
                "has_error": True,
                "tags": ["api-call", "todoist", "error"]
            })
        # 1 次成功（試探）
        entries.append({
            "ts": (base_time + timedelta(minutes=10)).isoformat(),
            "sid": "test-002",
            "tool": "Bash",
            "event": "post",
            "summary": "curl todoist API (trial)",
            "output": '[{"id":"123","content":"test"}]',
            "has_error": False,
            "tags": ["api-call", "todoist"]
        })

    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"Generated {len(entries)} test entries → {output_path}")
```

## 測試執行順序

1. **基礎驗證**（場景 1-2）：確認錯誤記錄與單次失敗處理
2. **狀態轉換**（場景 3-6）：完整驗證 closed → open → half_open → closed 循環
3. **告警機制**（場景 7）：驗證 ntfy 通知
4. **降級標記**（場景 8）：待實施後驗證

## 驗收標準

| 場景 | 檢查點 | 狀態 |
|------|--------|------|
| 1 | JSONL 正確記錄 API 錯誤 | ⏸️ 待測試 |
| 2 | Circuit Breaker 記錄單次失敗（failures=1, state=closed） | ⏸️ 待測試 |
| 3 | 連續 3 次失敗轉 open（failures=3, state=open, cooldown_until 設定） | ⏸️ 待測試 |
| 4 | Cooldown 未過期保持 open | ⏸️ 待測試 |
| 5 | Cooldown 過期自動轉 half_open | ⏸️ 待測試 |
| 6 | half_open 試探成功轉 closed（failures=0） | ⏸️ 待測試 |
| 7 | ntfy 告警正確發送（含 trace_id + error details） | ⏸️ 待測試 |
| 8 | 降級標記自動加註 | ⏸️ 待實施 |

## 預計時間

- 測試腳本準備：30 分鐘
- 場景 1-6 執行：60 分鐘
- 場景 7 執行：30 分鐘
- 場景 8 實施 + 測試：60 分鐘
- **總計：3 小時**
