# ============================================
# Claude Agent Team - Parallel Orchestrator (PowerShell 7)
# ============================================
# Usage:
#   Manual: pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1
#   Task Scheduler: same command
# ============================================
# Architecture:
#   Phase 1: 5 parallel fetch agents (todoist, news, hackernews, gmail, security)
#   Phase 2: 1 assembly agent (reads results, compiles digest, sends notification)
# ============================================

# PowerShell 7 defaults to UTF-8, explicit set for safety
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Set paths
$AgentDir = $PSScriptRoot
$LogDir = "$AgentDir\logs"
$StateFile = "$AgentDir\state\scheduler-state.json"
$ResultsDir = "$AgentDir\results"

# Config
$MaxPhase2Retries = 1
$Phase1TimeoutSeconds = 300
$Phase2TimeoutSeconds = 420  # Assembly 實測最大 360s，加 60s buffer

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$LogDir\structured" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\context" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\cache" | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

# ─── Instance Lock（防止同一腳本多實例並行）───
$LockFile = "$AgentDir\state\run-agent-team.lock"
if (Test-Path $LockFile) {
    $lockContent = Get-Content $LockFile -Raw -ErrorAction SilentlyContinue
    $lockPid = ($lockContent -split "`n")[0].Trim()
    # 檢查持有鎖的行程是否仍在執行
    $existingProcess = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
        Write-Host "[SKIP] Another instance is running (PID $lockPid). Exiting."
        exit 0
    } else {
        Write-Host "[WARN] Stale lock found (PID $lockPid not running). Removing."
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
}
# 寫入當前 PID
$PID | Set-Content $LockFile -Encoding UTF8
# 確保退出時清理鎖檔
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Remove-Item "$using:LockFile" -Force -ErrorAction SilentlyContinue
} | Out-Null

# Generate log filename (team_ prefix to distinguish from single mode)
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\team_$Timestamp.log"

# Write-Log function (UTF-8 without BOM, fixes Tee-Object UTF-16LE issue)
function Write-Log {
    param([string]$Message)
    Write-Host $Message
    [System.IO.File]::AppendAllText($LogFile, "$Message`r`n", [System.Text.Encoding]::UTF8)
}

# Remove stderr file if empty or contains only benign warnings
function Remove-StderrIfBenign {
    param([string]$StderrFile)
    if (-not (Test-Path $StderrFile)) { return }
    $size = (Get-Item $StderrFile).Length
    if ($size -eq 0) {
        Remove-Item $StderrFile -Force -ErrorAction SilentlyContinue
        return
    }
    $content = Get-Content $StderrFile -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) { return }
    $filtered = $content -replace '(?m)^.*\.claude\.json is corrupted.*$', '' `
                         -replace '(?m)^.*corrupted file has been backed up.*$', '' `
                         -replace '(?m)^.*corrupted file has already been backed up.*$', '' `
                         -replace '(?m)^.*backup file exists at.*$', '' `
                         -replace '(?m)^.*manually restore it by running.*$', '' `
                         -replace '(?m)^.*Pre-flight check is taking longer.*$', ''
    if ([string]::IsNullOrWhiteSpace($filtered)) {
        Remove-Item $StderrFile -Force -ErrorAction SilentlyContinue
    }
}

# Update scheduler state
function Update-State {
    param(
        [string]$Status,
        [int]$Duration,
        [string]$ErrorMsg,
        [hashtable]$Sections,
        [PSCustomObject]$PhaseBreakdown
    )

    $run = @{
        timestamp        = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")
        start_time       = $script:startTime.ToString("yyyy-MM-ddTHH:mm:ss")
        agent            = "daily-digest-team"
        status           = $Status
        duration_seconds = $Duration
        error            = $ErrorMsg
        sections         = $Sections
        log_file         = (Split-Path -Leaf $LogFile)
        phase_breakdown  = $PhaseBreakdown
    }

    if (Test-Path $StateFile) {
        try {
            $stateJson = Get-Content -Path $StateFile -Raw -Encoding UTF8
            $state = $stateJson | ConvertFrom-Json
        } catch {
            Write-Log "[WARN] scheduler-state.json corrupted, backing up and rebuilding..."
            Copy-Item $StateFile "$StateFile.corrupted.$(Get-Date -Format 'yyyyMMdd_HHmmss')" -ErrorAction SilentlyContinue
            $state = @{ runs = @() }
        }
    }
    else {
        $state = @{ runs = @() }
    }

    # Convert runs to ArrayList for manipulation
    $runs = [System.Collections.ArrayList]@($state.runs)
    $runs.Add($run) | Out-Null

    # Keep only last 200 runs
    while ($runs.Count -gt 200) {
        $runs.RemoveAt(0)
    }

    $state.runs = $runs.ToArray()
    $json = $state | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($StateFile, $json, [System.Text.Encoding]::UTF8)
}

# Update failure stats
function Update-FailureStats {
    param(
        [string]$FailureType,  # "timeout" | "api_error" | "circuit_open" | "phase_failure" | "parse_error"
        [string]$Phase = "unknown",
        [string]$AgentType = "daily-digest"
    )

    $statsFile = "$AgentDir\state\failure-stats.json"

    # 讀取現有統計
    if (Test-Path $statsFile) {
        try {
            $stats = Get-Content $statsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            $stats = [PSCustomObject]@{ updated = ""; daily = [PSCustomObject]@{}; total = [PSCustomObject]@{} }
        }
    } else {
        $stats = [PSCustomObject]@{ updated = ""; daily = [PSCustomObject]@{}; total = [PSCustomObject]@{} }
    }

    $today = (Get-Date).ToString("yyyy-MM-dd")

    # 確保今日條目存在
    if (-not $stats.daily.$today) {
        $stats.daily | Add-Member -NotePropertyName $today -NotePropertyValue ([PSCustomObject]@{
            timeout = 0; api_error = 0; circuit_open = 0; phase_failure = 0; parse_error = 0
        }) -Force
    }

    # 更新今日統計
    $currentVal = $stats.daily.$today.$FailureType
    if ($null -eq $currentVal) { $currentVal = 0 }
    $stats.daily.$today | Add-Member -NotePropertyName $FailureType -NotePropertyValue ($currentVal + 1) -Force

    # 更新總計
    $totalVal = $stats.total.$FailureType
    if ($null -eq $totalVal) { $totalVal = 0 }
    $stats.total | Add-Member -NotePropertyName $FailureType -NotePropertyValue ($totalVal + 1) -Force

    # 只保留 30 天
    $cutoff = (Get-Date).AddDays(-30).ToString("yyyy-MM-dd")
    $oldKeys = @($stats.daily.PSObject.Properties.Name | Where-Object { $_ -lt $cutoff })
    foreach ($k in $oldKeys) {
        $stats.daily.PSObject.Properties.Remove($k)
    }

    $stats | Add-Member -NotePropertyName "updated" -NotePropertyValue (Get-Date -Format "yyyy-MM-ddTHH:mm:ss") -Force

    # 原子寫入（write-to-temp + rename）
    $tmpFile = "$statsFile.tmp"
    $stats | ConvertTo-Json -Depth 5 | Set-Content $tmpFile -Encoding UTF8
    Move-Item $tmpFile $statsFile -Force
}

# FSM 狀態管理
function Set-FsmState {
    param(
        [string]$RunId,      # 唯一執行 ID（通常是 $traceId 的前 8 碼）
        [string]$Phase,      # "phase1" | "phase2" | "phase3" | "overall"
        [string]$State,      # "pending" | "running" | "completed" | "failed"
        [string]$AgentType = "daily-digest",
        [string]$Detail = ""
    )

    $fsmFile = "$AgentDir\state\run-fsm.json"
    $transitionFile = "$AgentDir\logs\structured\fsm-transitions.jsonl"
    $now = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"

    # 讀取現有 FSM 狀態
    if (Test-Path $fsmFile) {
        try {
            $fsm = Get-Content $fsmFile -Raw | ConvertFrom-Json
        } catch {
            $fsm = [PSCustomObject]@{ runs = [PSCustomObject]@{}; updated = "" }
        }
    } else {
        $fsm = [PSCustomObject]@{ runs = [PSCustomObject]@{}; updated = "" }
    }

    # P2-A: 殭屍狀態清理（running 超過 stale_timeout_hours → timeout）
    $staleHours = 2  # 與 config/timeouts.yaml fsm.stale_timeout_hours 同步
    $staleCutoff = (Get-Date).AddHours(-$staleHours).ToString("yyyy-MM-ddTHH:mm:ss")
    foreach ($existingRun in @($fsm.runs.PSObject.Properties)) {
        foreach ($existingPhase in @($existingRun.Value.phases.PSObject.Properties)) {
            if ($existingPhase.Value.state -eq "running" -and $existingPhase.Value.updated -lt $staleCutoff) {
                $existingPhase.Value | Add-Member -NotePropertyName "state" -NotePropertyValue "timeout" -Force
                $existingPhase.Value | Add-Member -NotePropertyName "detail" -NotePropertyValue "auto-timeout: running > ${staleHours}h" -Force
            }
        }
    }

    # 建立或更新 run 記錄
    $runKey = "${AgentType}_${RunId}"
    if (-not $fsm.runs.$runKey) {
        $fsm.runs | Add-Member -NotePropertyName $runKey -NotePropertyValue ([PSCustomObject]@{
            run_id     = $RunId
            agent_type = $AgentType
            started    = $now
            phases     = [PSCustomObject]@{}
        }) -Force
    }

    # 更新 Phase 狀態
    $fsm.runs.$runKey.phases | Add-Member -NotePropertyName $Phase -NotePropertyValue ([PSCustomObject]@{
        state   = $State
        updated = $now
        detail  = $Detail
    }) -Force

    $fsm | Add-Member -NotePropertyName "updated" -NotePropertyValue $now -Force

    # 清理：已完成/失敗/timeout 超過 24 小時的 runs（不清除仍 running 的 runs）
    $cutoff24h = (Get-Date).AddHours(-24).ToString("yyyy-MM-ddTHH:mm:ss")
    $doneOldKeys = @($fsm.runs.PSObject.Properties | Where-Object {
        $run = $_.Value
        $phases = @($run.phases.PSObject.Properties.Value)
        $isOld = $run.started -lt $cutoff24h
        $allDone = $phases.Count -gt 0 -and ($phases | Where-Object { $_.state -eq "running" }).Count -eq 0
        $isOld -and $allDone
    } | Select-Object -ExpandProperty Name)
    foreach ($k in $doneOldKeys) {
        $fsm.runs.PSObject.Properties.Remove($k)
    }

    # max_entries 限制（超過 20 則移除最舊的已完成 run）
    $maxEntries = 20  # 與 config/timeouts.yaml fsm.max_entries 同步
    $runCount = ($fsm.runs.PSObject.Properties | Measure-Object).Count
    if ($runCount -gt $maxEntries) {
        $toRemoveCount = $runCount - $maxEntries
        $doneRunsToRemove = @($fsm.runs.PSObject.Properties | Where-Object {
            $phases = @($_.Value.phases.PSObject.Properties.Value)
            $phases.Count -gt 0 -and ($phases | Where-Object { $_.state -eq "running" }).Count -eq 0
        } | Sort-Object { $_.Value.started } | Select-Object -First $toRemoveCount -ExpandProperty Name)
        foreach ($k in $doneRunsToRemove) {
            $fsm.runs.PSObject.Properties.Remove($k)
        }
    }

    # 原子寫入 FSM 狀態
    $tmpFile = "$fsmFile.tmp"
    $fsm | ConvertTo-Json -Depth 6 | Set-Content $tmpFile -Encoding UTF8
    Move-Item $tmpFile $fsmFile -Force

    # Append-only 寫入 transition JSONL
    $transition = [PSCustomObject]@{
        ts         = $now
        run_id     = $RunId
        agent_type = $AgentType
        phase      = $Phase
        state      = $State
        detail     = $Detail
    }
    $transitionJson = $transition | ConvertTo-Json -Compress

    # 確保目錄存在
    $transitionDir = Split-Path $transitionFile -Parent
    if (-not (Test-Path $transitionDir)) {
        New-Item -ItemType Directory -Path $transitionDir -Force | Out-Null
    }

    # Append（檔案不存在時自動建立）
    Add-Content -Path $transitionFile -Value $transitionJson -Encoding UTF8
}

function Write-Span {
    <#
    .SYNOPSIS
        記錄 Phase/Agent 級別 Span 到 results/spans-{traceId}.json（Level 3-A）
    .DESCRIPTION
        每個 Phase 或子 Agent 完成後呼叫，記錄 start_time、end_time、duration_s、status。
        由 query-logs.ps1 -Mode waterfall 讀取渲染 ASCII Waterfall 視覺化。
    #>
    param(
        [string]$TraceId,
        [string]$SpanType,   # "phase" | "agent"
        [string]$Phase,      # "phase1" | "phase2" | "overall"
        [string]$Agent = "", # 子 Agent 名稱（phase 層級時為空）
        [datetime]$StartTime,
        [datetime]$EndTime,
        [string]$Status      # "ok" | "failed" | "timeout" | "cache"
    )

    $spansFile = "$ResultsDir\spans-$TraceId.json"
    $spans = @()
    if (Test-Path $spansFile) {
        try { $spans = @(Get-Content $spansFile -Raw | ConvertFrom-Json) } catch { $spans = @() }
    }

    $span = [PSCustomObject]@{
        span_id    = [guid]::NewGuid().ToString("N").Substring(0, 8)
        trace_id   = $TraceId
        span_type  = $SpanType
        phase      = $Phase
        agent      = $Agent
        start_time = $StartTime.ToString("yyyy-MM-ddTHH:mm:ss")
        end_time   = $EndTime.ToString("yyyy-MM-ddTHH:mm:ss")
        duration_s = [int]($EndTime - $StartTime).TotalSeconds
        status     = $Status
    }
    $spans += $span

    try {
        $spans | ConvertTo-Json -Depth 3 | Set-Content $spansFile -Encoding UTF8
    } catch {
        Write-Log "[Span] Write failed: $_"
    }
}

# ============================================
# Start execution
# ============================================
$startTime = Get-Date

# ─── 載入 Todoist API Token（一次性，安全讀取）───
if (-not $env:TODOIST_API_TOKEN) {
    $envFile = "$AgentDir\.env"
    if (Test-Path $envFile) {
        $envLine = Get-Content $envFile | Where-Object { $_ -match '^TODOIST_API_TOKEN=' }
        if ($envLine) {
            $todoistToken = ($envLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $todoistToken, "Process")
            Write-Host "[Token] TODOIST_API_TOKEN loaded from .env"
        }
        else { $todoistToken = ""; Write-Host "[WARN] TODOIST_API_TOKEN not found in .env" }
    }
    else { $todoistToken = ""; Write-Host "[WARN] .env not found, TODOIST_API_TOKEN may be missing" }
}
else {
    $todoistToken = $env:TODOIST_API_TOKEN
    Write-Host "[Token] TODOIST_API_TOKEN loaded from environment"
}

# ─── 載入 BOT_API_SECRET（chatroom 認證，選用）───
if (-not $env:BOT_API_SECRET) {
    if (Test-Path "$AgentDir\.env") {
        $botSecretLine = Get-Content "$AgentDir\.env" | Where-Object { $_ -match '^BOT_API_SECRET=' }
        if ($botSecretLine) {
            $botSecret = ($botSecretLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable("BOT_API_SECRET", $botSecret, "Process")
            Write-Host "[Token] BOT_API_SECRET loaded from .env"
        }
        # 無 BOT_API_SECRET 時靜默略過（chatroom 為可選整合）
    }
}

# ─── 生產環境安全策略 ───
# 若未設定則預設 strict（排程器執行環境），手動執行可覆蓋
if (-not (Test-Path Env:HOOK_SECURITY_PRESET)) {
    $env:HOOK_SECURITY_PRESET = "strict"
}
Write-Log "[Security] HOOK_SECURITY_PRESET = $($env:HOOK_SECURITY_PRESET)"

# Generate trace ID for distributed tracing
$traceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
Write-Log "=== Agent Team start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Log "Trace ID: $traceId"
Write-Log "Mode: parallel (Phase 1 x6 + Phase 2 x1)"

# Check if claude is installed
$claudePath = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudePath) {
    Write-Log "[ERROR] claude not found, install: npm install -g @anthropic-ai/claude-code"
    Update-State -Status "failed" -Duration 0 -ErrorMsg "claude not found" -Sections @{}
    exit 1
}

# ============================================
# Phase 0: Circuit Breaker 預檢查
# ============================================
Write-Log ""
Write-Log "=== Phase 0: Circuit Breaker precheck ==="

# 載入預檢查工具函式庫
$utilsPath = "$AgentDir\circuit-breaker-utils.ps1"
if (Test-Path $utilsPath) {
    . $utilsPath
    Write-Log "[預檢查] 已載入 circuit-breaker-utils.ps1"
} else {
    Write-Log "[WARN] circuit-breaker-utils.ps1 不存在，跳過預檢查"
}

# API 對照表（agent name → API name in api-health.json）
$apiMapping = @{
    "todoist"    = "todoist"
    "news"       = "pingtung-news"
    "hackernews" = "hackernews"
    "gmail"      = "gmail"
    "chatroom"   = "gun-bot"
}

# 執行預檢查
$precheckResults = @{}
if (Test-Path $utilsPath) {
    foreach ($agentName in $apiMapping.Keys) {
        $apiName = $apiMapping[$agentName]
        $state = Test-CircuitBreaker $apiName
        $precheckResults[$agentName] = $state

        if ($state -eq "open") {
            Write-Log "[預檢查] ✗ $apiName ($agentName) 為 OPEN 狀態，將跳過執行"
        } elseif ($state -eq "half_open") {
            Write-Log "[預檢查] ⚠ $apiName ($agentName) 為 HALF_OPEN 狀態，將正常執行（試探）"
        } else {
            Write-Log "[預檢查] ✓ $apiName ($agentName) 為 CLOSED 狀態，正常執行"
        }
    }
} else {
    # 預檢查工具不存在，全部假設為 closed
    foreach ($agentName in $apiMapping.Keys) {
        $precheckResults[$agentName] = "closed"
    }
}

# ============================================
# Phase 0: 快取狀態預計算（由 PS 計算，不依賴 LLM 時鐘）
# LLM 無時鐘問題：讓 PS 預計算 valid/expired，LLM 只讀 valid 欄位
# ============================================
Write-Log ""
Write-Log "=== Phase 0: Cache status precomputation ==="
$cacheTtl = @{
    "todoist"       = 45
    "pingtung-news" = 360
    "hackernews"    = 180
    "gmail"         = 360
    "knowledge"     = 60
}
# 從 cache-policy.yaml 讀取實際 TTL（若可用，覆蓋預設值）
$cachePolicyPath = "$AgentDir\config\cache-policy.yaml"
if (Test-Path $cachePolicyPath) {
    $policyContent = Get-Content $cachePolicyPath -Raw -Encoding UTF8
    foreach ($api in @("todoist", "pingtung-news", "hackernews", "gmail", "knowledge")) {
        if ($policyContent -match "(?s)${api}:.*?ttl_minutes:\s*(\d+)") {
            $cacheTtl[$api] = [int]$Matches[1]
        }
    }
}
$cacheStatus = [ordered]@{
    generated_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
    apis = [ordered]@{}
}
foreach ($api in @("todoist", "pingtung-news", "hackernews", "gmail", "knowledge")) {
    $cacheFile = "$AgentDir\cache\$api.json"
    if (-not (Test-Path $cacheFile)) {
        $cacheFile = "$AgentDir\cache\$($api -replace '-', '_').json"
    }
    if (Test-Path $cacheFile) {
        try {
            $cacheData = Get-Content $cacheFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $cachedAt = [DateTime]$cacheData.cached_at
            $ageMins = [int]((Get-Date).ToUniversalTime() - $cachedAt.ToUniversalTime()).TotalMinutes
            $ttl = $cacheTtl[$api]
            $valid = ($ageMins -lt $ttl)
            $reason = if ($valid) { "hit" } else { "expired" }
            $cacheStatus.apis[$api] = [ordered]@{ valid = $valid; reason = $reason; age_min = $ageMins; ttl_min = $ttl }
            $statusStr = if ($valid) { "HIT (${ageMins}min / TTL ${ttl}min)" } else { "EXPIRED (${ageMins}min > TTL ${ttl}min)" }
            Write-Log "  [Cache] ${api}: $statusStr"
        } catch {
            $cacheStatus.apis[$api] = [ordered]@{ valid = $false; reason = "error" }
            Write-Log "  [Cache] ${api}: ERROR (parse failed)"
        }
    } else {
        $cacheStatus.apis[$api] = [ordered]@{ valid = $false; reason = "missing" }
        Write-Log "  [Cache] ${api}: MISSING"
    }
}
$cacheStatusJson = $cacheStatus | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText("$AgentDir\cache\status.json", $cacheStatusJson, [System.Text.Encoding]::UTF8)
Write-Log "[Phase0] cache/status.json 生成完成"

# ============================================
# Phase 1: Parallel Data Fetch (含預檢查)
# ============================================
Write-Log ""
Write-Log "=== Phase 1: Parallel fetch start (with precheck) ==="
$phase1Start = Get-Date
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "running" -AgentType "daily-digest"

$fetchAgents = @(
    @{ Name = "todoist";    Prompt = "$AgentDir\prompts\team\fetch-todoist.md";    Result = "$ResultsDir\todoist.json" },
    @{ Name = "news";       Prompt = "$AgentDir\prompts\team\fetch-news.md";       Result = "$ResultsDir\news.json" },
    @{ Name = "hackernews"; Prompt = "$AgentDir\prompts\team\fetch-hackernews.md"; Result = "$ResultsDir\hackernews.json" },
    @{ Name = "gmail";      Prompt = "$AgentDir\prompts\team\fetch-gmail.md";      Result = "$ResultsDir\gmail.json" },
    @{ Name = "security";   Prompt = "$AgentDir\prompts\team\fetch-security.md";   Result = "$ResultsDir\security.json" },
    @{ Name = "chatroom";   Prompt = "$AgentDir\prompts\team\fetch-chatroom.md";   Result = "$ResultsDir\fetch-chatroom.json" }
)

$jobs = @()
foreach ($agent in $fetchAgents) {
    if (-not (Test-Path $agent.Prompt)) {
        Write-Log "[ERROR] Prompt not found: $($agent.Prompt)"
        continue
    }

    # 檢查預檢查結果（security agent 不在 API 對照表中，總是執行）
    $agentName = $agent.Name
    $precheckState = $precheckResults[$agentName]

    if ($precheckState -eq "open") {
        # API 為 open 狀態，建立降級結果並跳過執行
        Write-Log "[Phase1] Skipped: $agentName (Circuit Breaker: OPEN) - 使用降級模式"

        if (Test-Path $utilsPath) {
            $apiName = $apiMapping[$agentName]
            New-DegradedResult -APIName $apiName -OutputPath $agent.Result -State "open"
        } else {
            # fallback: 手動建立降級結果
            $fallbackResult = @{
                status = "cache_degraded"
                source = "cache"
                circuit_breaker = "open"
                message = "Circuit Breaker 預檢查發現 API 為 open 狀態（fallback mode）"
                timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
                precheck_skipped = $true
            }
            $fallbackResult | ConvertTo-Json -Depth 10 | Set-Content $agent.Result -Encoding UTF8
        }

        continue  # 跳過這個 agent
    }

    # 正常執行（closed 或 half_open）
    if ($precheckState -eq "half_open") {
        Write-Log "[Phase1] Starting: $agentName (Circuit Breaker: HALF_OPEN, trial mode)"
    } else {
        Write-Log "[Phase1] Starting: $agentName (Circuit Breaker: CLOSED)"
    }

    $promptContent = Get-Content -Path $agent.Prompt -Raw -Encoding UTF8
    $agentName = $agent.Name

    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($Content, $agentName, $logDir, $timestamp, $traceId, $apiToken)

        # 明確設定 Process 級別環境變數（會傳遞到子 process）
        [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
        [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
        [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase1", "Process")
        [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
        if ($apiToken) {
            [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
        }

        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        $stderrFile = "$logDir\$agentName-stderr-$timestamp.log"
        $output = $Content | claude -p --allowedTools "Read,Bash,Write" 2>$stderrFile

        # 執行成功且 stderr 為空 → 刪除
        if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
            $stderrSize = (Get-Item $stderrFile).Length
            if ($stderrSize -eq 0) {
                Remove-Item $stderrFile -Force
            }
        }

        return $output
    } -ArgumentList $promptContent, $agentName, $LogDir, $Timestamp, $traceId, $todoistToken

    $job | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $agentName
    $jobs += $job
    Write-Log "[Phase1] Started: $agentName (Job $($job.Id))"
}

# Wait for all Phase 1 jobs
if ($jobs.Count -gt 0) {
    Write-Log "[Phase1] Waiting for $($jobs.Count) agents (timeout: ${Phase1TimeoutSeconds}s)..."
    $jobs | Wait-Job -Timeout $Phase1TimeoutSeconds | Out-Null
}

# Collect results
$sections = @{}
foreach ($job in $jobs) {
    $agentName = $job.AgentName
    $output = Receive-Job -Job $job -ErrorAction SilentlyContinue

    if ($job.State -eq "Completed") {
        # Log last 5 lines of output (avoid flooding)
        if ($output) {
            $outputLines = @($output)
            $startIdx = [Math]::Max(0, $outputLines.Count - 5)
            for ($i = $startIdx; $i -lt $outputLines.Count; $i++) {
                Write-Log "  [$agentName] $($outputLines[$i])"
            }
        }

        # Check if result file was created
        $resultFile = ($fetchAgents | Where-Object { $_.Name -eq $agentName }).Result
        if (Test-Path $resultFile) {
            try {
                $resultJson = Get-Content -Path $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json
                $sections[$agentName] = $resultJson.status
                Write-Log "[Phase1] $agentName OK: status=$($resultJson.status), source=$($resultJson.source)"
            }
            catch {
                $sections[$agentName] = "failed"
                Write-Log "[Phase1] ${agentName} - result file parse error"
            }
        }
        else {
            $sections[$agentName] = "failed"
            Write-Log "[Phase1] ${agentName} - result file not found"
        }
    }
    elseif ($job.State -eq "Running") {
        Write-Log "[Phase1] $agentName TIMEOUT - stopping"
        Stop-Job -Job $job
        $sections[$agentName] = "failed"
        Update-FailureStats "timeout" "phase1" "daily-digest"
    }
    else {
        Write-Log "[Phase1] $agentName failed (state: $($job.State))"
        if ($output) { Write-Log "  $output" }
        $sections[$agentName] = "failed"
        Update-FailureStats "phase_failure" "phase1" "daily-digest"
    }
}

# Clean up Phase 1 jobs
$jobs | Remove-Job -Force -ErrorAction SilentlyContinue

# Clean up stderr files (empty or containing only benign warnings)
Get-ChildItem "$LogDir\*-stderr-$Timestamp.log" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-StderrIfBenign $_.FullName
}

$phase1End = Get-Date
$phase1Seconds = [int]($phase1End - $phase1Start).TotalSeconds
$phase1Duration = [int]($phase1End - $startTime).TotalSeconds
Write-Log ""
Write-Log "=== Phase 1 complete (${phase1Duration}s from start, ${phase1Seconds}s phase-only) ==="
Write-Log "Results: todoist=$($sections['todoist']) | news=$($sections['news']) | hackernews=$($sections['hackernews']) | gmail=$($sections['gmail']) | security=$($sections['security']) | chatroom=$($sections['chatroom'])"

# FSM Phase 1 結果
$phase1Failed = ($sections.Values | Where-Object { $_ -eq "failed" }).Count
if ($phase1Failed -gt 0) {
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "completed" -AgentType "daily-digest" -Detail "$($jobs.Count - $phase1Failed) agents OK, $phase1Failed failed"
} else {
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "completed" -AgentType "daily-digest" -Detail "$($jobs.Count) agents completed"
}

# Level 3-A: 記錄 per-agent span + Phase 1 span
foreach ($agentKey in $sections.Keys) {
    Write-Span -TraceId $traceId -SpanType "agent" -Phase "phase1" -Agent $agentKey `
        -StartTime $phase1Start -EndTime $phase1End -Status ($sections[$agentKey] -ne $null ? $sections[$agentKey] : "unknown")
}
Write-Span -TraceId $traceId -SpanType "phase" -Phase "phase1" `
    -StartTime $phase1Start -EndTime $phase1End `
    -Status (if ($phase1Failed -gt 0) { "failed" } else { "ok" })

# ─── Circuit Breaker 自動更新（基於 Phase 1 結果）───
if (Get-Command Update-CircuitBreaker -ErrorAction SilentlyContinue) {
    $apiMapping = @{
        "todoist"     = "todoist"
        "news"        = "pingtung-news"
        "hackernews"  = "hackernews"
        "gmail"       = "gmail"
        "chatroom"    = "gun-bot"
    }
    foreach ($agentKey in $apiMapping.Keys) {
        $apiName = $apiMapping[$agentKey]
        $success = ($sections[$agentKey] -eq "success") -or ($sections[$agentKey] -eq "cache")
        Update-CircuitBreaker -ApiName $apiName -Success $success
    }
    Write-Log "[Circuit Breaker] Phase 1 結果已更新（todoist/$($sections['todoist']), news/$($sections['news']), hn/$($sections['hackernews']), gmail/$($sections['gmail']), chatroom/$($sections['chatroom'])）"
}

# ============================================
# Phase 2: Assembly (1 agent, with retry)
# ============================================
Write-Log ""
Write-Log "=== Phase 2: Assembly start ==="
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "running" -AgentType "daily-digest"

$assemblePrompt = "$AgentDir\prompts\team\assemble-digest.md"
if (-not (Test-Path $assemblePrompt)) {
    Write-Log "[ERROR] Assembly prompt not found: $assemblePrompt"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "assembly prompt not found" -Sections $sections
    exit 1
}

$assembleContent = Get-Content -Path $assemblePrompt -Raw -Encoding UTF8
$phase2Success = $false
$phase2Seconds = 0
$attempt = 0
$phase2StartOuter = Get-Date

while ($attempt -le $MaxPhase2Retries) {
    if ($attempt -gt 0) {
        $backoff = [math]::Min(60 * [math]::Pow(2, $attempt), 300)
        $jitter = Get-Random -Minimum 0 -Maximum 15
        $waitSec = [int]($backoff + $jitter)
        Write-Log "[Phase2] Retry attempt $($attempt + 1) in ${waitSec}s (backoff=${backoff}+jitter=${jitter})..."
        Start-Sleep -Seconds $waitSec
    }

    Write-Log "[Phase2] Running assembly agent (attempt $($attempt + 1))..."
    $phase2Start = Get-Date

    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        # Set trace ID and phase marker for Phase 2
        $env:DIGEST_TRACE_ID = $traceId
        $env:AGENT_PHASE = "phase2"
        $env:AGENT_NAME = "assemble-digest"

        $stderrFile = "$LogDir\assemble-stderr-$Timestamp-$($traceId.Substring(0,8)).log"
        $output = $assembleContent | claude -p --allowedTools "Read,Bash,Write" 2>$stderrFile

        # 清理 stderr（空檔或僅含已知無害警告）
        Remove-StderrIfBenign $stderrFile

        $output | ForEach-Object {
            Write-Log "  [assemble] $_"
        }

        if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
            $phase2Success = $true
            $phase2Seconds = [int]((Get-Date) - $phase2Start).TotalSeconds
            Write-Log "[Phase2] Assembly completed (${phase2Seconds}s)"
            Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "completed" -AgentType "daily-digest"
            break
        }
        else {
            Write-Log "[Phase2] Assembly exited with code: $LASTEXITCODE"
            Update-FailureStats "phase_failure" "phase2" "daily-digest"
            Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "failed" -AgentType "daily-digest" -Detail "exit code $LASTEXITCODE"
        }
    }
    catch {
        Write-Log "[Phase2] Assembly failed: $_"
        Update-FailureStats "phase_failure" "phase2" "daily-digest"
        Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "failed" -AgentType "daily-digest" -Detail "$_"
    }

    $attempt++
}

# 若 phase2 未成功完成（失敗/未賦值），用外層計時作為估算
if ($phase2Seconds -eq 0) {
    $phase2Seconds = [int]((Get-Date) - $phase2StartOuter).TotalSeconds
}

# ============================================
# Final status
# ============================================
$totalDuration = [int]((Get-Date) - $startTime).TotalSeconds

# 組合 phase_breakdown
$phaseBreakdown = [PSCustomObject]@{
    phase1_seconds = $phase1Seconds
    phase2_seconds = $phase2Seconds
    phase1_agents  = @("todoist", "news", "hackernews", "gmail", "security")
}

# Level 3-A: 記錄 Phase 2 span + Overall span
$runEnd = Get-Date
Write-Span -TraceId $traceId -SpanType "phase" -Phase "phase2" `
    -StartTime $phase2StartOuter -EndTime $runEnd `
    -Status (if ($phase2Success) { "ok" } else { "failed" })
Write-Span -TraceId $traceId -SpanType "phase" -Phase "overall" `
    -StartTime $startTime -EndTime $runEnd `
    -Status (if ($phase2Success) { "ok" } else { "failed" })

if ($phase2Success) {
    Write-Log ""
    Write-Log "=== Agent Team done (success): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Write-Log "Total: ${totalDuration}s (Phase1: ${phase1Seconds}s + Phase2: ${phase2Seconds}s)"
    Update-State -Status "success" -Duration $totalDuration -ErrorMsg $null -Sections $sections -PhaseBreakdown $phaseBreakdown
}
else {
    Write-Log ""
    Write-Log "=== Agent Team done (failed): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Write-Log "Total: ${totalDuration}s"
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "assembly failed after $($MaxPhase2Retries + 1) attempts" -Sections $sections -PhaseBreakdown $phaseBreakdown
}

# Clean up logs older than 7 days
Get-ChildItem -Path $LogDir -Filter "*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force

# Clean up spans files older than 7 days
Get-ChildItem "$ResultsDir\spans-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force

# Clean up stale loop-state files older than 48 hours
$loopStateFiles = Get-ChildItem "$AgentDir\state\loop-state-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-48) }
if ($loopStateFiles) {
    $loopStateFiles | Remove-Item -Force
    Write-Log "[Cleanup] Removed $($loopStateFiles.Count) stale loop-state files (>48h)"
}

# Clean up stale stop-alert files older than 7 days
$stopAlertFiles = Get-ChildItem "$AgentDir\state\stop-alert-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
if ($stopAlertFiles) {
    $stopAlertFiles | Remove-Item -Force
    Write-Log "[Cleanup] Removed $($stopAlertFiles.Count) stale stop-alert files (>7d)"
}

# Clean up stale results files older than 7 days (exclude spans, handled above)
$staleResults = Get-ChildItem "$ResultsDir\*" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notlike "spans-*" -and $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
if ($staleResults) {
    $staleResults | Remove-Item -Force
    Write-Log "[Cleanup] Removed $($staleResults.Count) stale result files (>7d)"
}

# 清理 Instance Lock
Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
