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

# Update scheduler state
function Update-State {
    param(
        [string]$Status,
        [int]$Duration,
        [string]$ErrorMsg,
        [hashtable]$Sections
    )

    $run = @{
        timestamp        = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")
        agent            = "daily-digest-team"
        status           = $Status
        duration_seconds = $Duration
        error            = $ErrorMsg
        sections         = $Sections
        log_file         = (Split-Path -Leaf $LogFile)
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
Write-Log "Mode: parallel (Phase 1 x5 + Phase 2 x1)"

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

$fetchAgents = @(
    @{ Name = "todoist";    Prompt = "$AgentDir\prompts\team\fetch-todoist.md";    Result = "$ResultsDir\todoist.json" },
    @{ Name = "news";       Prompt = "$AgentDir\prompts\team\fetch-news.md";       Result = "$ResultsDir\news.json" },
    @{ Name = "hackernews"; Prompt = "$AgentDir\prompts\team\fetch-hackernews.md"; Result = "$ResultsDir\hackernews.json" },
    @{ Name = "gmail";      Prompt = "$AgentDir\prompts\team\fetch-gmail.md";      Result = "$ResultsDir\gmail.json" },
    @{ Name = "security";   Prompt = "$AgentDir\prompts\team\fetch-security.md";   Result = "$ResultsDir\security.json" }
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
    }
    else {
        Write-Log "[Phase1] $agentName failed (state: $($job.State))"
        if ($output) { Write-Log "  $output" }
        $sections[$agentName] = "failed"
    }
}

# Clean up Phase 1 jobs
$jobs | Remove-Job -Force -ErrorAction SilentlyContinue

$phase1Duration = [int]((Get-Date) - $startTime).TotalSeconds
Write-Log ""
Write-Log "=== Phase 1 complete (${phase1Duration}s) ==="
Write-Log "Results: todoist=$($sections['todoist']) | news=$($sections['news']) | hackernews=$($sections['hackernews']) | gmail=$($sections['gmail']) | security=$($sections['security'])"

# ─── Circuit Breaker 自動更新（基於 Phase 1 結果）───
if (Get-Command Update-CircuitBreaker -ErrorAction SilentlyContinue) {
    $apiMapping = @{
        "todoist"     = "todoist"
        "news"        = "pingtung-news"
        "hackernews"  = "hackernews"
        "gmail"       = "gmail"
    }
    foreach ($agentKey in $apiMapping.Keys) {
        $apiName = $apiMapping[$agentKey]
        $success = ($sections[$agentKey] -eq "success") -or ($sections[$agentKey] -eq "cache")
        Update-CircuitBreaker -ApiName $apiName -Success $success
    }
    Write-Log "[Circuit Breaker] Phase 1 結果已更新（todoist/$($sections['todoist']), news/$($sections['news']), hn/$($sections['hackernews']), gmail/$($sections['gmail'])）"
}

# ============================================
# Phase 2: Assembly (1 agent, with retry)
# ============================================
Write-Log ""
Write-Log "=== Phase 2: Assembly start ==="

$assemblePrompt = "$AgentDir\prompts\team\assemble-digest.md"
if (-not (Test-Path $assemblePrompt)) {
    Write-Log "[ERROR] Assembly prompt not found: $assemblePrompt"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "assembly prompt not found" -Sections $sections
    exit 1
}

$assembleContent = Get-Content -Path $assemblePrompt -Raw -Encoding UTF8
$phase2Success = $false
$attempt = 0

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

        # Set trace ID for Phase 2 (same as Phase 1)
        $env:DIGEST_TRACE_ID = $traceId

        $stderrFile = "$LogDir\assemble-stderr-$Timestamp.log"
        $output = $assembleContent | claude -p --allowedTools "Read,Bash,Write" 2>$stderrFile

        # 執行成功且 stderr 為空 → 刪除
        if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
            $stderrSize = (Get-Item $stderrFile).Length
            if ($stderrSize -eq 0) {
                Remove-Item $stderrFile -Force
            }
        }

        $output | ForEach-Object {
            Write-Log "  [assemble] $_"
        }

        if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
            $phase2Success = $true
            $phase2Duration = [int]((Get-Date) - $phase2Start).TotalSeconds
            Write-Log "[Phase2] Assembly completed (${phase2Duration}s)"
            break
        }
        else {
            Write-Log "[Phase2] Assembly exited with code: $LASTEXITCODE"
        }
    }
    catch {
        Write-Log "[Phase2] Assembly failed: $_"
    }

    $attempt++
}

# ============================================
# Final status
# ============================================
$totalDuration = [int]((Get-Date) - $startTime).TotalSeconds

if ($phase2Success) {
    Write-Log ""
    Write-Log "=== Agent Team done (success): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Write-Log "Total: ${totalDuration}s (Phase1: ${phase1Duration}s)"
    Update-State -Status "success" -Duration $totalDuration -ErrorMsg $null -Sections $sections
}
else {
    Write-Log ""
    Write-Log "=== Agent Team done (failed): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Write-Log "Total: ${totalDuration}s"
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "assembly failed after $($MaxPhase2Retries + 1) attempts" -Sections $sections
}

# Clean up logs older than 7 days
Get-ChildItem -Path $LogDir -Filter "*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force
