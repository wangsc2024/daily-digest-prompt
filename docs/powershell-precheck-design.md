# PowerShell Circuit Breaker 預檢查機制設計

## 目標

在 Phase 1 開始前檢查 `state/api-health.json`，若 API 為 open 狀態，跳過該 API 的 agent 執行，直接使用降級快取，節省執行時間。

## 設計方案

### 方案 A：完整預檢查（推薦用於未來優化）

修改 `run-agent-team.ps1`，在 Phase 1 之前加入預檢查邏輯。

#### 實施步驟

1. **讀取 api-health.json**：

```powershell
function Test-APIHealth {
    param (
        [string]$APIName
    )

    $healthFile = "state/api-health.json"
    if (-not (Test-Path $healthFile)) {
        return "closed"  # 檔案不存在，假設正常
    }

    $health = Get-Content $healthFile -Raw | ConvertFrom-Json
    $apiState = $health.$APIName
    if ($null -eq $apiState) {
        return "closed"  # API 未初始化，假設正常
    }

    return $apiState.state
}
```

2. **在 Phase 1 之前檢查每個 API**：

```powershell
# Phase 1: 並行擷取（含預檢查）
Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] Phase 1: 啟動資料擷取 Agents (含預檢查)" -ForegroundColor Cyan

# 檢查各 API 狀態
$todoistState = Test-APIHealth "todoist"
$newsState = Test-APIHealth "pingtung-news"
$hnState = Test-APIHealth "hackernews"
$gmailState = Test-APIHealth "gmail"

# 根據狀態決定是否啟動 Agent
$jobs = @()

if ($todoistState -eq "open") {
    Write-Host "[預檢查] Todoist API 為 open 狀態，跳過執行，使用快取降級" -ForegroundColor Yellow
    # 建立降級結果檔案
    @{
        status = "cache_degraded"
        source = "cache"
        circuit_breaker = "open"
        message = "Circuit Breaker 預檢查發現 API 為 open 狀態，跳過執行"
    } | ConvertTo-Json -Depth 10 | Set-Content "results/todoist.json" -Encoding UTF8
} else {
    Write-Host "[預檢查] Todoist API 狀態: $todoistState，正常執行" -ForegroundColor Green
    $jobs += Start-Job -Name "Todoist" -WorkingDirectory $AgentDir -ScriptBlock {
        # 原有執行邏輯
        param($AgentDir)
        $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        # ... 原有代碼
    } -ArgumentList $AgentDir
}

# 對其他 API 重複相同邏輯（news, hackernews, gmail）
```

3. **Phase 2 處理降級結果**：

Phase 2 的 assemble-digest.md 已有容錯處理（步驟 1），會自動識別 `source = "cache_degraded"` 並加註「⚠️ 資料來自快取」。

結合步驟 6.5 的降級標記檢查，會進一步加上「⚠️ XXX API 暫時故障」。

### 方案 B：輕量級預警（目前實施）

不修改 Phase 1 執行邏輯，僅在 Phase 2 檢測並加註降級標記（已於 `prompts/team/assemble-digest.md` 步驟 6.5 實施）。

#### 優點

- 實施簡單，無需修改 PowerShell 腳本
- 不影響現有穩定流程
- 透過降級標記讓用戶察覺 API 故障

#### 缺點

- 無法節省執行時間（Phase 1 仍會嘗試呼叫 open 狀態的 API）
- API 連續失敗可能導致 Phase 1 timeout（目前 timeout 300s 仍足夠）

## 效益分析

### 方案 A（完整預檢查）

**節省時間估算**（假設 Todoist API 為 open）：
- 跳過 Todoist Agent 執行：~30-60 秒
- 直接使用快取降級：< 1 秒
- **淨節省**：30-60 秒/次

**適用場景**：
- API 長時間故障（如 OAuth token 過期）
- 頻繁執行的排程（每小時執行）

### 方案 B（輕量級預警）

**適用場景**：
- 快速實施，優先保證穩定性
- API 故障頻率低（偶發性問題）
- 執行頻率不高（每日 3 次）

## 建議實施順序

1. **Week 2 Day 1-2**（已完成）：方案 B（輕量級預警）
   - ✅ Step 6.5 降級標記檢查
   - ✅ 降級標記對照表
   - ✅ Step 7 整合降級標記

2. **Week 2 Day 3-5**（待評估）：方案 A（完整預檢查）
   - 修改 run-agent-team.ps1
   - 建立 Test-APIHealth 函式
   - 建立降級結果檔案
   - 端到端測試

## 回滾計畫

若方案 A 實施後出現問題：

1. **立即回滾**：恢復原 run-agent-team.ps1
2. **降級至方案 B**：保留步驟 6.5 的降級標記邏輯
3. **檢查 api-health.json**：手動修正錯誤的 Circuit Breaker 狀態

## 測試計畫

### 方案 A 測試場景

1. **場景 1**：Todoist API 為 open
   - 預期：跳過 Phase 1 Todoist Agent
   - 預期：Phase 2 讀取降級結果，加註降級標記

2. **場景 2**：所有 API 正常
   - 預期：正常執行 Phase 1 所有 Agent
   - 預期：Phase 2 無降級標記

3. **場景 3**：api-health.json 不存在
   - 預期：正常執行（fallback 到 closed 狀態）

4. **場景 4**：混合狀態（Todoist open, News closed, HN half_open）
   - 預期：跳過 Todoist，執行 News 和 HN
   - 預期：HN 因 half_open 可能成功或失敗

## 附錄：完整 PowerShell 函式

```powershell
# ============================================
# Circuit Breaker 預檢查函式庫
# ============================================

function Test-APIHealth {
    <#
    .SYNOPSIS
    檢查 API 健康狀態
    .PARAMETER APIName
    API 名稱（todoist, pingtung-news, hackernews, gmail）
    .OUTPUTS
    String: "closed", "open", "half_open"
    #>
    param (
        [Parameter(Mandatory=$true)]
        [ValidateSet("todoist", "pingtung-news", "hackernews", "gmail")]
        [string]$APIName
    )

    $healthFile = "state/api-health.json"

    # 檔案不存在或讀取失敗 → 假設正常
    if (-not (Test-Path $healthFile)) {
        return "closed"
    }

    try {
        $health = Get-Content $healthFile -Raw -ErrorAction Stop | ConvertFrom-Json
        $apiState = $health.$APIName

        if ($null -eq $apiState) {
            return "closed"  # API 未初始化
        }

        # 檢查 cooldown 是否過期（若為 open 狀態）
        if ($apiState.state -eq "open" -and $apiState.cooldown) {
            $cooldownTime = [DateTime]::Parse($apiState.cooldown)
            $now = Get-Date

            if ($now -gt $cooldownTime) {
                # Cooldown 已過期，應轉為 half_open
                # 但此處僅讀取，不修改狀態（由 assembly agent 負責）
                return "half_open"
            }
        }

        return $apiState.state
    }
    catch {
        Write-Warning "讀取 api-health.json 失敗：$($_.Exception.Message)"
        return "closed"  # fallback 到正常狀態
    }
}

function New-DegradedResult {
    <#
    .SYNOPSIS
    建立降級結果檔案
    .PARAMETER APIName
    API 名稱
    .PARAMETER OutputPath
    輸出路徑
    #>
    param (
        [string]$APIName,
        [string]$OutputPath
    )

    $result = @{
        status = "cache_degraded"
        source = "cache"
        circuit_breaker = "open"
        message = "Circuit Breaker 預檢查發現 $APIName API 為 open 狀態，跳過執行，使用快取降級"
        timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    }

    $result | ConvertTo-Json -Depth 10 | Set-Content $OutputPath -Encoding UTF8
    Write-Host "[降級] 已建立 $APIName 降級結果 → $OutputPath" -ForegroundColor Yellow
}
```

## 使用範例

```powershell
# 在 run-agent-team.ps1 中使用
. "$PSScriptRoot/circuit-breaker-utils.ps1"  # 載入函式庫

# 檢查 Todoist 狀態
$todoistState = Test-APIHealth "todoist"

if ($todoistState -eq "open") {
    Write-Host "[預檢查] Todoist API 為 open 狀態，使用降級模式" -ForegroundColor Yellow
    New-DegradedResult -APIName "todoist" -OutputPath "results/todoist.json"
} else {
    # 正常執行 Todoist Agent
    $jobs += Start-Job -Name "Todoist" -WorkingDirectory $AgentDir -ScriptBlock {
        # ... Phase 1 Todoist 執行邏輯
    }
}
```
