# ============================================
# System Audit Agent Team - Parallel Orchestrator (PowerShell 7)
# ============================================
# Usage:
#   Manual: pwsh -ExecutionPolicy Bypass -File run-system-audit-team.ps1
#   Task Scheduler: same command (daily 00:40)
# ============================================
# Architecture:
#   Phase 1: 4 parallel audit agents (dim1+5, dim2+6, dim3+7, dim4)
#   Phase 2: 1 assembly agent (collect + fix + report + RAG)
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
$Phase1TimeoutSeconds = 600  # 10 minutes per agent
$Phase2TimeoutSeconds = 1200  # 20 minutes

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$LogDir\structured" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\docs" | Out-Null

# ============================================
# Helper Functions
# ============================================

function Get-Timestamp {
    return Get-Date -Format "yyyy-MM-dd HH:mm:ss"
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Timestamp
    $logMessage = "[$timestamp] [$Level] $Message"
    Write-Host $logMessage
}

function Update-SchedulerState {
    param(
        [string]$Status,
        [string]$Message = "",
        [int]$ExitCode = 0
    )

    if (-not (Test-Path $StateFile)) {
        $state = @{ executions = @() }
    } else {
        $state = Get-Content $StateFile -Encoding UTF8 | ConvertFrom-Json
    }

    $execution = @{
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        agent = "system-audit-team"
        status = $Status
        message = $Message
        exit_code = $ExitCode
    }

    $state.executions += $execution

    # Keep last 200 executions
    if ($state.executions.Count -gt 200) {
        $state.executions = $state.executions[-200..-1]
    }

    $state | ConvertTo-Json -Depth 10 | Set-Content $StateFile -Encoding UTF8
}

# ============================================
# Main Execution
# ============================================

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$phase1LogFile = "$LogDir\audit-phase1-$timestamp.log"
$phase2LogFile = "$LogDir\audit-phase2-$timestamp.log"

# Distributed tracing: generate trace ID for this execution
$TraceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
$env:DIGEST_TRACE_ID = $TraceId

# Security level: strict for scheduled runs
if (-not $env:DIGEST_SECURITY_LEVEL) {
    $env:DIGEST_SECURITY_LEVEL = "strict"
}

Write-Log "=== System Audit Team Mode Started ===" "INFO"
Write-Log "TraceId: $TraceId | SecurityLevel: $($env:DIGEST_SECURITY_LEVEL)" "INFO"

# ============================================
# Phase 1: Parallel Audit (4 Agents)
# ============================================

Write-Log "Phase 1: Starting 4 parallel audit agents..." "INFO"

$phase1Jobs = @()
$phase1Prompts = @(
    @{ Name = "dim1-5"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim1-5.md" },
    @{ Name = "dim2-6"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim2-6.md" },
    @{ Name = "dim3-7"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim3-7.md" },
    @{ Name = "dim4"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim4.md" }
)

foreach ($agent in $phase1Prompts) {
    $job = Start-Job -ScriptBlock {
        param($promptFile, $agentDir, $agentName)
        Set-Location $agentDir
        $OutputEncoding = [System.Text.Encoding]::UTF8

        Write-Host "[$agentName] Starting audit..." -ForegroundColor Cyan
        $output = claude -p $promptFile --allowedTools "Read,Bash,Glob,Grep,Write" 2>&1

        Write-Host "[$agentName] Completed" -ForegroundColor Green
        return @{
            Name = $agentName
            Output = $output
            ExitCode = $LASTEXITCODE
        }
    } -ArgumentList $agent.Prompt, $AgentDir, $agent.Name -WorkingDirectory $AgentDir

    $phase1Jobs += @{
        Job = $job
        Name = $agent.Name
    }
}

Write-Log "Waiting for Phase 1 agents to complete (timeout: $Phase1TimeoutSeconds seconds)..." "INFO"

# Wait for all Phase 1 jobs
$phase1Results = @()
$phase1Success = $true

foreach ($jobInfo in $phase1Jobs) {
    $job = $jobInfo.Job
    $name = $jobInfo.Name

    $completed = Wait-Job -Job $job -Timeout $Phase1TimeoutSeconds

    if ($null -eq $completed) {
        Write-Log "Phase 1 agent $name timed out" "ERROR"
        Stop-Job -Job $job
        Remove-Job -Job $job -Force
        $phase1Success = $false
    } else {
        $result = Receive-Job -Job $job
        Remove-Job -Job $job -Force

        $phase1Results += $result
        Write-Log "Phase 1 agent $name completed (exit code: $($result.ExitCode))" "INFO"

        # Save output to log
        $result.Output | Out-File -FilePath $phase1LogFile -Append -Encoding UTF8
    }
}

# Check if all Phase 1 agents succeeded
if (-not $phase1Success) {
    Write-Log "Phase 1 failed - some agents timed out" "ERROR"
    Update-SchedulerState -Status "error" -Message "Phase 1 timeout" -ExitCode 1
    exit 1
}

# Verify Phase 1 outputs
$expectedResults = @("dim1-5", "dim2-6", "dim3-7", "dim4")
foreach ($expected in $expectedResults) {
    $resultFile = "$ResultsDir\audit-$expected.json"
    if (-not (Test-Path $resultFile)) {
        Write-Log "Phase 1 result missing: $resultFile" "ERROR"
        $phase1Success = $false
    }
}

if (-not $phase1Success) {
    Write-Log "Phase 1 failed - missing result files" "ERROR"
    Update-SchedulerState -Status "error" -Message "Phase 1 incomplete" -ExitCode 1
    exit 1
}

Write-Log "Phase 1 completed successfully" "INFO"

# ============================================
# Phase 2: Assembly & Fixing
# ============================================

Write-Log "Phase 2: Starting assembly agent..." "INFO"

$phase2Prompt = "$AgentDir\prompts\team\assemble-audit.md"
$phase2Attempt = 1
$maxPhase2Attempts = $MaxPhase2Retries + 1
$phase2Success = $false

while ($phase2Attempt -le $maxPhase2Attempts -and -not $phase2Success) {
    if ($phase2Attempt -gt 1) {
        Write-Log "Phase 2 retry attempt $phase2Attempt of $maxPhase2Attempts after 60 seconds delay..." "WARN"
        Start-Sleep -Seconds 60
    }

    try {
        $job = Start-Job -ScriptBlock {
            param($promptFile, $agentDir)
            Set-Location $agentDir
            $OutputEncoding = [System.Text.Encoding]::UTF8
            claude -p $promptFile --allowedTools "Read,Bash,Glob,Grep,Write,Edit" 2>&1
        } -ArgumentList $phase2Prompt, $AgentDir -WorkingDirectory $AgentDir

        $completed = Wait-Job -Job $job -Timeout $Phase2TimeoutSeconds

        if ($null -eq $completed) {
            Write-Log "Phase 2 timed out after $Phase2TimeoutSeconds seconds" "ERROR"
            Stop-Job -Job $job
            Remove-Job -Job $job -Force
            $phase2Attempt++
            continue
        }

        $output = Receive-Job -Job $job
        Remove-Job -Job $job -Force

        # Save output to log
        $output | Out-File -FilePath $phase2LogFile -Encoding UTF8

        # Check if successful (look for completion indicators)
        $outputStr = $output -join "`n"
        if ($outputStr -match "審查完成|Step 8.*清理|知識庫.*成功|state/last-audit.json.*已更新") {
            Write-Log "Phase 2 completed successfully" "INFO"
            $phase2Success = $true
        } else {
            Write-Log "Phase 2 completed but may have issues" "WARN"
            if ($phase2Attempt -eq $maxPhase2Attempts) {
                # Last attempt, accept as success
                $phase2Success = $true
            }
        }
    } catch {
        Write-Log "Error in Phase 2: $_" "ERROR"
        if ($phase2Attempt -eq $maxPhase2Attempts) {
            Update-SchedulerState -Status "error" -Message $_.Exception.Message -ExitCode 1
        }
    }

    $phase2Attempt++
}

if (-not $phase2Success) {
    Write-Log "Phase 2 failed after $maxPhase2Attempts attempts" "ERROR"
    Update-SchedulerState -Status "error" -Message "Phase 2 failed" -ExitCode 1
    exit 1
}

# ============================================
# Completion
# ============================================

Write-Log "=== System Audit Team Mode Completed ===" "INFO"
Write-Log "Phase 1 log: $phase1LogFile" "INFO"
Write-Log "Phase 2 log: $phase2LogFile" "INFO"

# Check if audit state was updated
$auditStateFile = "$AgentDir\state\last-audit.json"
if (Test-Path $auditStateFile) {
    $auditState = Get-Content $auditStateFile -Encoding UTF8 | ConvertFrom-Json
    Write-Log "Audit score: $($auditState.total_score) (Grade: $($auditState.grade))" "INFO"
    if ($auditState.fixes_applied) {
        Write-Log "Auto-fixes applied: $($auditState.fixes_applied)" "INFO"
    }
}

Update-SchedulerState -Status "success" -Message "Team audit completed" -ExitCode 0
exit 0
