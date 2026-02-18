# ============================================
# Circuit Breaker 工具函式庫
# ============================================
# 用於 run-*-team.ps1 的 PowerShell Circuit Breaker 整合
# 在 Phase 1 之前檢查 API 健康狀態，跳過故障的 API
# 在 Phase 2 完成後更新 API 健康狀態

$script:ApiHealthFile = "$PSScriptRoot\state\api-health.json"

function Test-CircuitBreaker {
    <#
    .SYNOPSIS
    檢查 API Circuit Breaker 狀態

    .DESCRIPTION
    讀取 state/api-health.json，檢查指定 API 的 Circuit Breaker 狀態。
    若為 open 或 half_open 狀態，返回相應狀態；否則返回 closed。

    .PARAMETER ApiName
    API 名稱（todoist, pingtung-news, hackernews, gmail, knowledge）

    .OUTPUTS
    String: "closed", "open", "half_open"

    .EXAMPLE
    $state = Test-CircuitBreaker "todoist"
    if ($state -eq "open") {
        Write-Host "Todoist API 故障中，使用降級模式"
    }
    #>
    param (
        [Parameter(Mandatory=$true)]
        [ValidateSet("todoist", "pingtung-news", "hackernews", "gmail", "knowledge")]
        [string]$ApiName
    )

    # 檔案不存在或讀取失敗 → 假設正常
    if (-not (Test-Path $script:ApiHealthFile)) {
        Write-Verbose "[Circuit Breaker] api-health.json 不存在，假設 $ApiName 為 closed 狀態"
        return "closed"
    }

    try {
        $healthContent = Get-Content $script:ApiHealthFile -Raw -ErrorAction Stop
        $health = $healthContent | ConvertFrom-Json
        $apiState = $health.$ApiName

        if ($null -eq $apiState) {
            Write-Verbose "[Circuit Breaker] $ApiName 未初始化，假設為 closed 狀態"
            return "closed"
        }

        $currentState = $apiState.state

        # 若為 open 狀態，檢查 cooldown 是否過期
        if ($currentState -eq "open" -and $apiState.cooldown) {
            try {
                $cooldownTime = [DateTime]::Parse($apiState.cooldown)
                $now = Get-Date

                if ($now -gt $cooldownTime) {
                    # Cooldown 已過期，應轉為 half_open
                    # 注意：此處僅讀取，不修改狀態（由 Reset-CircuitBreakerCooldown 負責）
                    Write-Verbose "[Circuit Breaker] $ApiName cooldown 已過期，返回 half_open"
                    return "half_open"
                }
            }
            catch {
                Write-Warning "[Circuit Breaker] 解析 $ApiName cooldown 時間失敗：$($_.Exception.Message)"
            }
        }

        Write-Verbose "[Circuit Breaker] $ApiName 當前狀態：$currentState"
        return $currentState
    }
    catch {
        Write-Warning "[Circuit Breaker] 讀取 api-health.json 失敗：$($_.Exception.Message)"
        return "closed"  # fallback 到正常狀態
    }
}

function Update-CircuitBreaker {
    <#
    .SYNOPSIS
    更新 API Circuit Breaker 狀態

    .DESCRIPTION
    根據 API 呼叫成功/失敗更新斷路器狀態。
    失敗 3 次 → open；成功 → closed + 重置計數器。

    .PARAMETER ApiName
    API 名稱（todoist, pingtung-news, hackernews, gmail, knowledge）

    .PARAMETER Success
    $true 表示成功，$false 表示失敗

    .PARAMETER ErrorCategory
    錯誤分類（rate_limit, server_error, client_error, network_error）

    .EXAMPLE
    Update-CircuitBreaker -ApiName "todoist" -Success $false -ErrorCategory "rate_limit"
    #>
    param (
        [Parameter(Mandatory=$true)]
        [ValidateSet("todoist", "pingtung-news", "hackernews", "gmail", "knowledge")]
        [string]$ApiName,

        [Parameter(Mandatory=$true)]
        [bool]$Success,

        [Parameter(Mandatory=$false)]
        [ValidateSet("rate_limit", "server_error", "client_error", "network_error", "")]
        [string]$ErrorCategory = ""
    )

    if (-not (Test-Path $script:ApiHealthFile)) {
        Write-Warning "[Circuit Breaker] api-health.json 不存在，跳過更新"
        return
    }

    try {
        $health = Get-Content $script:ApiHealthFile -Raw -Encoding UTF8 | ConvertFrom-Json

        if ($null -eq $health.$ApiName) {
            Write-Warning "[Circuit Breaker] 未知 API: $ApiName，跳過更新"
            return
        }

        $circuit = $health.$ApiName

        if ($Success) {
            # 成功：重置計數器，關閉斷路器
            $circuit.state = "closed"
            $circuit.failures = 0
            $circuit.cooldown = $null
            Write-Verbose "[Circuit Breaker] $ApiName 成功，狀態重置為 closed"
        }
        else {
            # 失敗：遞增計數器
            $circuit.failures++
            Write-Verbose "[Circuit Breaker] $ApiName 失敗，failures = $($circuit.failures)"

            # 閾值：3 次連續失敗 → open
            if ($circuit.failures -ge 3) {
                $circuit.state = "open"

                # 根據錯誤分類計算冷卻時間
                $cooldownMinutes = switch ($ErrorCategory) {
                    "rate_limit"    { 60 }   # 1 小時（速率限制）
                    "server_error"  { 30 }   # 30 分鐘（5xx）
                    "network_error" { 15 }   # 15 分鐘（網路問題）
                    default         { 10 }   # 10 分鐘（預設）
                }

                $cooldownTime = (Get-Date).AddMinutes($cooldownMinutes).ToUniversalTime()
                $circuit.cooldown = $cooldownTime.ToString("yyyy-MM-ddTHH:mm:ssZ")

                Write-Host "[Circuit Breaker] $ApiName 開啟斷路器（failures ≥ 3），冷卻 $cooldownMinutes 分鐘" -ForegroundColor Red
            }
        }

        # 儲存更新後的狀態
        $health | ConvertTo-Json -Depth 5 | Set-Content $script:ApiHealthFile -Encoding UTF8 -NoNewline
    }
    catch {
        Write-Warning "[Circuit Breaker] 更新失敗：$($_.Exception.Message)"
    }
}

function Reset-CircuitBreakerCooldown {
    <#
    .SYNOPSIS
    重置已過期的 Circuit Breaker 冷卻時間

    .DESCRIPTION
    檢查所有 API 的斷路器狀態，將已過期的 open 狀態轉為 half_open。

    .EXAMPLE
    Reset-CircuitBreakerCooldown
    #>
    if (-not (Test-Path $script:ApiHealthFile)) {
        return
    }

    try {
        $health = Get-Content $script:ApiHealthFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $now = (Get-Date).ToUniversalTime()
        $updated = $false

        foreach ($apiName in @("todoist", "pingtung-news", "hackernews", "gmail", "knowledge")) {
            $circuit = $health.$apiName
            if ($null -ne $circuit -and $circuit.state -eq "open" -and $null -ne $circuit.cooldown) {
                $cooldownTime = [DateTime]::Parse($circuit.cooldown)
                if ($now -ge $cooldownTime) {
                    # 冷卻時間已過期，轉為 half_open
                    $circuit.state = "half_open"
                    $circuit.cooldown = $null
                    $updated = $true
                    Write-Host "[Circuit Breaker] $apiName: open → half_open（冷卻已過期）" -ForegroundColor Yellow
                }
            }
        }

        if ($updated) {
            $health | ConvertTo-Json -Depth 5 | Set-Content $script:ApiHealthFile -Encoding UTF8 -NoNewline
        }
    }
    catch {
        Write-Warning "[Circuit Breaker] 重置冷卻失敗：$($_.Exception.Message)"
    }
}

function New-DegradedResult {
    <#
    .SYNOPSIS
    建立降級結果檔案

    .DESCRIPTION
    當 API 為 open 狀態時，建立降級結果檔案供 Phase 2 使用。
    結果檔案標記為 cache_degraded，並含 circuit_breaker 欄位說明原因。

    .PARAMETER APIName
    API 名稱

    .PARAMETER OutputPath
    輸出路徑（如 results/todoist.json）

    .PARAMETER State
    Circuit Breaker 狀態（open 或 half_open）

    .EXAMPLE
    New-DegradedResult -APIName "todoist" -OutputPath "results/todoist.json" -State "open"
    #>
    param (
        [Parameter(Mandatory=$true)]
        [string]$APIName,

        [Parameter(Mandatory=$true)]
        [string]$OutputPath,

        [Parameter(Mandatory=$true)]
        [ValidateSet("open", "half_open")]
        [string]$State
    )

    $result = @{
        status = "cache_degraded"
        source = "cache"
        circuit_breaker = $State
        message = "Circuit Breaker 預檢查發現 $APIName API 為 $State 狀態，跳過執行，使用快取降級"
        timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
        precheck_skipped = $true
    }

    # 確保 results 目錄存在
    $resultsDir = Split-Path $OutputPath -Parent
    if (-not (Test-Path $resultsDir)) {
        New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null
    }

    # 寫入 JSON
    $result | ConvertTo-Json -Depth 10 | Set-Content $OutputPath -Encoding UTF8

    Write-Host "[降級] 已建立 $APIName 降級結果 → $OutputPath" -ForegroundColor Yellow
}

function Get-PrecheckSummary {
    <#
    .SYNOPSIS
    產生預檢查摘要

    .DESCRIPTION
    檢查所有 API 狀態並產生摘要報告。

    .OUTPUTS
    Hashtable: @{ todoist = "closed", "pingtung-news" = "open", ... }

    .EXAMPLE
    $summary = Get-PrecheckSummary
    $summary.Keys | ForEach-Object {
        Write-Host "$_ : $($summary[$_])"
    }
    #>

    $apis = @("todoist", "pingtung-news", "hackernews", "gmail", "knowledge")
    $summary = @{}

    foreach ($api in $apis) {
        $state = Test-CircuitBreaker $api
        $summary[$api] = $state
    }

    return $summary
}

function Show-PrecheckReport {
    <#
    .SYNOPSIS
    顯示預檢查報告

    .DESCRIPTION
    檢查所有 API 並以彩色輸出顯示狀態。

    .EXAMPLE
    Show-PrecheckReport
    #>

    Write-Host "`n[Circuit Breaker 預檢查]" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Gray

    $summary = Get-PrecheckSummary
    $degradedCount = 0

    foreach ($api in $summary.Keys | Sort-Object) {
        $state = $summary[$api]

        switch ($state) {
            "closed" {
                Write-Host "  ✓ $api : " -NoNewline -ForegroundColor Green
                Write-Host "正常運作 (closed)" -ForegroundColor Gray
            }
            "half_open" {
                Write-Host "  ⚠ $api : " -NoNewline -ForegroundColor Yellow
                Write-Host "試探狀態 (half_open) - 將正常執行" -ForegroundColor Yellow
                $degradedCount++
            }
            "open" {
                Write-Host "  ✗ $api : " -NoNewline -ForegroundColor Red
                Write-Host "故障中 (open) - 將跳過執行，使用快取" -ForegroundColor Red
                $degradedCount++
            }
        }
    }

    Write-Host ("=" * 60) -ForegroundColor Gray

    if ($degradedCount -eq 0) {
        Write-Host "所有 API 正常運作，無需降級" -ForegroundColor Green
    } else {
        Write-Host "偵測到 $degradedCount 個 API 需要降級處理" -ForegroundColor Yellow
    }

    Write-Host ""
}

# 注意：腳本模式（. 載入）時，所有函式已自動可用，無需 Export-ModuleMember
# Export-ModuleMember 僅在模組模式（Import-Module）時有效
