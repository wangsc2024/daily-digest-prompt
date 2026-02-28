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

    # 清理超過 24 小時的 runs（只保留近期）
    $cutoff = (Get-Date).AddHours(-24).ToString("yyyy-MM-ddTHH:mm:ss")
    $oldKeys = @($fsm.runs.PSObject.Properties | Where-Object {
        $_.Value.started -lt $cutoff
    } | Select-Object -ExpandProperty Name)
    foreach ($k in $oldKeys) {
        $fsm.runs.PSObject.Properties.Remove($k)
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

        $stderrFile = "$LogDir\assemble-stderr-$Timestamp.log"
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
