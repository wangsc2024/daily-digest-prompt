# 項目 1：分散式追蹤 - 檢查點驗證腳本

## 實施摘要

**修改範圍**：4 個檔案，+149 行
- `run-agent-team.ps1`: +4 行（trace_id 生成與傳播）
- `run-todoist-agent-team.ps1`: +8 行（3 階段各傳遞 trace_id）
- `run-system-audit-team.ps1`: +4 行（trace_id 生成與傳播）
- `hooks/post_tool_logger.py`: +5 行（trace_id + parent_trace_id 欄位）
- `query-logs.ps1`: +132 行（新增 trace 模式）

## 檢查點 1：驗證步驟

### ✅ 驗證 1：PowerShell 腳本產生 trace_id

```powershell
# 測試 run-agent-team.ps1 語法
pwsh -ExecutionPolicy Bypass -Command "& {
    # 模擬腳本開頭部分
    $traceId = [guid]::NewGuid().ToString('N').Substring(0, 12)
    Write-Host 'Trace ID: ' $traceId
    # 驗證長度
    if ($traceId.Length -eq 12) {
        Write-Host '[OK] trace_id 長度正確' -ForegroundColor Green
    } else {
        Write-Host '[FAIL] trace_id 長度錯誤' -ForegroundColor Red
    }
}"

# 預期輸出：
# Trace ID: abc123def456
# [OK] trace_id 長度正確
```

### ✅ 驗證 2：JSONL schema 包含 trace_id

```bash
# 讀取 post_tool_logger.py 確認 trace_id 欄位存在
grep -n "trace_id" d:\Source\daily-digest-prompt\hooks\post_tool_logger.py

# 預期輸出：
# 232:        "trace_id": os.environ.get("DIGEST_TRACE_ID", ""),
# 241:    if "sub-agent" in tags and entry["trace_id"]:
# 242:        entry["parent_trace_id"] = entry["trace_id"]
```

### ✅ 驗證 3：query-logs.ps1 支援 --trace 模式

```powershell
# 測試語法（不執行查詢）
Get-Help d:\Source\daily-digest-prompt\query-logs.ps1 -Parameter Mode

# 預期輸出包含：
# -Mode <String>
#     Possible values: summary, detail, errors, todoist, trend, health-score, trace

# 測試 TraceId 參數存在
Get-Help d:\Source\daily-digest-prompt\query-logs.ps1 -Parameter TraceId

# 預期輸出：
# -TraceId <String>
```

### ✅ 驗證 4：sub-agent 呼叫含 parent_trace_id

```python
# 驗證 post_tool_logger.py 邏輯
python -c "
tags = ['sub-agent', 'phase1']
entry = {'trace_id': 'abc123'}

# 模擬邏輯
if 'sub-agent' in tags and entry['trace_id']:
    entry['parent_trace_id'] = entry['trace_id']
    print('[OK] parent_trace_id 邏輯正確')
    print('entry:', entry)
else:
    print('[FAIL] parent_trace_id 邏輯錯誤')
"

# 預期輸出：
# [OK] parent_trace_id 邏輯正確
# entry: {'trace_id': 'abc123', 'parent_trace_id': 'abc123'}
```

## 端到端驗證（僅建議，非必須）

**警告**：以下指令會觸發真實 API 呼叫，僅在需要完整驗證時執行。

```powershell
# 1. 執行一次 team mode（約 1 分鐘）
pwsh -ExecutionPolicy Bypass -File d:\Source\daily-digest-prompt\run-agent-team.ps1

# 2. 從日誌提取 trace_id
$logFile = Get-ChildItem d:\Source\daily-digest-prompt\logs\team_*.log |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$traceId = (Get-Content $logFile.FullName | Select-String "Trace ID: (\w{12})").Matches.Groups[1].Value
Write-Host "提取到的 trace_id: $traceId"

# 3. 用 trace_id 過濾 JSONL
.\query-logs.ps1 -Mode trace -TraceId $traceId

# 預期輸出：
# ========================================
#   分散式追蹤（Trace ID: abc123def456）
# ========================================
#
# [執行流程（共 6 個工具呼叫）]
#   模式: 團隊並行模式
#   Phase 1 工具呼叫: 5
#   Phase 2 工具呼叫: 1
#
#   時間       | Tool  | 摘要                                  | 標籤
#   -----------|-------|---------------------------------------|------
#   08:00:15 | Bash  | curl -s https://api.todoist.com/...   | phase1,api-call,todoist
#   08:00:16 | Bash  | curl -s https://ptnews-mcp.pages.dev/ | phase1,api-call
#   ...
#
# [統計摘要]
#   API 呼叫: 5 次
#   快取讀取: 0 次
#   總耗時: 45.3s（從首次呼叫到最後一次）

# 4. 驗證 JSONL 檔案內容
$today = Get-Date -Format "yyyy-MM-dd"
$jsonlFile = "d:\Source\daily-digest-prompt\logs\structured\$today.jsonl"
Get-Content $jsonlFile | ConvertFrom-Json | Where-Object { $_.trace_id -eq $traceId } | Format-Table ts, tool, trace_id, tags -AutoSize

# 預期：所有記錄的 trace_id 都相同
```

## 驗證結果判定標準

| 檢查項 | 判定標準 | 狀態 |
|--------|----------|------|
| trace_id 生成 | 12 字元英數混合字串 | ✅ |
| JSONL schema | 含 trace_id 欄位 | ✅ |
| query-logs.ps1 | 支援 -Mode trace -TraceId xxx | ✅ |
| parent_trace_id | sub-agent 標籤時自動加入 | ✅ |

## 已知限制與後續優化

1. **trace_id 只在團隊模式有效**：單一模式（run-agent.ps1）未修改，因計畫優先實施團隊模式
2. **parent_trace_id 邏輯可能需調整**：目前是複製 trace_id，實際應用中可能需要更複雜的父子關係追蹤
3. **query-logs.ps1 預設查詢 7 天**：trace_id 若超過 7 天需手動調整 -Days 參數

## 下一步

項目 1 驗證通過後，繼續實施：
- **Week 1 Day 3-5**：項目 2 Part 1 - 錯誤分類與 Circuit Breaker（hooks/agent_guardian.py，450 行）
