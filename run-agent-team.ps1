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

# Distributed tracing: generate trace ID for this execution
$TraceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
$env:DIGEST_TRACE_ID = $TraceId

# Security level: strict for scheduled runs (can override via env var)
if (-not $env:DIGEST_SECURITY_LEVEL) {
    $env:DIGEST_SECURITY_LEVEL = "strict"
}

Write-Log "=== Agent Team start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Log "Mode: parallel (Phase 1 x5 + Phase 2 x1)"
Write-Log "TraceId: $TraceId | SecurityLevel: $($env:DIGEST_SECURITY_LEVEL)"

# Check if claude is installed
$claudePath = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudePath) {
    Write-Log "[ERROR] claude not found, install: npm install -g @anthropic-ai/claude-code"
    Update-State -Status "failed" -Duration 0 -ErrorMsg "claude not found" -Sections @{}
    exit 1
}

# ============================================
# Phase 1: Parallel Data Fetch (3 agents)
# ============================================
Write-Log ""
Write-Log "=== Phase 1: Parallel fetch start ==="

# Circuit breaker: check API health before launching agents
$ApiHealthFile = "$AgentDir\state\api-health.json"
$ApiHealth = @{}
if (Test-Path $ApiHealthFile) {
    try {
        $ApiHealth = Get-Content -Path $ApiHealthFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Log "[WARN] api-health.json parse failed, skipping circuit breaker check"
    }
}

$fetchAgents = @(
    @{ Name = "todoist";    Prompt = "$AgentDir\prompts\team\fetch-todoist.md";    Result = "$ResultsDir\todoist.json"; ApiSource = "todoist" },
    @{ Name = "news";       Prompt = "$AgentDir\prompts\team\fetch-news.md";       Result = "$ResultsDir\news.json";    ApiSource = "pingtung-news" },
    @{ Name = "hackernews"; Prompt = "$AgentDir\prompts\team\fetch-hackernews.md"; Result = "$ResultsDir\hackernews.json"; ApiSource = "hackernews" },
    @{ Name = "gmail";      Prompt = "$AgentDir\prompts\team\fetch-gmail.md";      Result = "$ResultsDir\gmail.json";   ApiSource = "gmail" },
    @{ Name = "security";   Prompt = "$AgentDir\prompts\team\fetch-security.md";   Result = "$ResultsDir\security.json"; ApiSource = "" }
)

$jobs = @()
foreach ($agent in $fetchAgents) {
    if (-not (Test-Path $agent.Prompt)) {
        Write-Log "[ERROR] Prompt not found: $($agent.Prompt)"
        continue
    }

    # Circuit breaker: skip agents whose API is in open state
    $apiSource = $agent.ApiSource
    if ($apiSource -and $ApiHealth.$apiSource.circuit_state -eq "open") {
        $cooldownUntil = $ApiHealth.$apiSource.cooldown_until
        Write-Log "[Phase1] SKIP $($agent.Name) — circuit open (cooldown until $cooldownUntil)"
        $sections[$agent.Name] = "circuit_open"
        continue
    }

    $promptContent = Get-Content -Path $agent.Prompt -Raw -Encoding UTF8
    $agentName = $agent.Name

    # Set phase tag for distributed tracing
    $env:DIGEST_PHASE = "phase1-$agentName"

    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($Content, $TraceId, $Phase, $SecurityLevel)
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
        $env:DIGEST_TRACE_ID = $TraceId
        $env:DIGEST_PHASE = $Phase
        $env:DIGEST_SECURITY_LEVEL = $SecurityLevel
        $Content | claude -p --allowedTools "Read,Bash,Write" 2>&1
    } -ArgumentList $promptContent, $TraceId, "phase1-$agentName", $env:DIGEST_SECURITY_LEVEL

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

    # Set phase tag for distributed tracing
    $env:DIGEST_PHASE = "phase2-assemble"

    try {
        $assembleContent | claude -p --allowedTools "Read,Bash,Write" 2>&1 | ForEach-Object {
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
