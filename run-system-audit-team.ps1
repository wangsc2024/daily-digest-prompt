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
Write-Log "[Security] HOOK_SECURITY_PRESET = $($env:HOOK_SECURITY_PRESET)" "INFO"

# Generate trace ID for distributed tracing
$traceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
Write-Log "=== System Audit Team Mode Started ===" "INFO"
Write-Log "Trace ID: $traceId" "INFO"

# ============================================
# Phase 0: Circuit Breaker 預檢查
# ============================================

Write-Log "Phase 0: Circuit Breaker precheck..." "INFO"

# 載入預檢查工具
$utilsPath = "$AgentDir\circuit-breaker-utils.ps1"
$knowledgeAvailable = $true

if (Test-Path $utilsPath) {
    . $utilsPath
    Write-Log "  Loaded circuit-breaker-utils.ps1" "INFO"

    # 檢查 knowledge API 狀態（用於 RAG 寫入）
    $knowledgeState = Test-CircuitBreaker "knowledge"

    if ($knowledgeState -eq "open") {
        Write-Log "  ✗ Knowledge API is OPEN - RAG import will be skipped" "WARN"
        $knowledgeAvailable = $false
    }
    elseif ($knowledgeState -eq "half_open") {
        Write-Log "  ⚠ Knowledge API is HALF_OPEN - RAG import will proceed (trial)" "WARN"
    }
    else {
        Write-Log "  ✓ Knowledge API is CLOSED - RAG import will proceed" "INFO"
    }
}
else {
    Write-Log "  circuit-breaker-utils.ps1 not found, skipping precheck" "WARN"
}

# Set environment variable to inform Phase 2 assembly agent
if ($knowledgeAvailable) {
    $env:KNOWLEDGE_API_AVAILABLE = "1"
}
else {
    $env:KNOWLEDGE_API_AVAILABLE = "0"
}

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
        param($promptFile, $agentDir, $agentName, $logDir, $timestamp, $traceId, $apiToken)

        # 明確設定 Process 級別環境變數（會傳遞到子 process）
        [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
        [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
        if ($apiToken) {
            [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
        }

        Set-Location $agentDir
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        Write-Host "[$agentName] Starting audit..." -ForegroundColor Cyan

        $stderrFile = "$logDir\$agentName-stderr-$timestamp.log"
        $output = claude -p $promptFile --allowedTools "Read,Bash,Glob,Grep,Write" 2>$stderrFile

        # 執行成功且 stderr 為空 → 刪除
        if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
            $stderrSize = (Get-Item $stderrFile).Length
            if ($stderrSize -eq 0) {
                Remove-Item $stderrFile -Force
            }
        }

        Write-Host "[$agentName] Completed" -ForegroundColor Green
        return @{
            Name = $agentName
            Output = $output
            ExitCode = $LASTEXITCODE
        }
    } -ArgumentList $agent.Prompt, $AgentDir, $agent.Name, $LogDir, $timestamp, $traceId, $todoistToken -WorkingDirectory $AgentDir

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

# Clean up stderr files from Phase 1
Get-ChildItem "$LogDir\*-stderr-*.log" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-StderrIfBenign $_.FullName
}

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
            param($promptFile, $agentDir, $logDir, $timestamp, $traceId, $apiToken)

            # 明確設定 Process 級別環境變數（會傳遞到子 process）
            [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
            [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
            if ($apiToken) {
                [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
            }

            Set-Location $agentDir
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $OutputEncoding = [System.Text.Encoding]::UTF8

            $stderrFile = "$logDir\assemble-stderr-$timestamp.log"
            $output = claude -p $promptFile --allowedTools "Read,Bash,Glob,Grep,Write,Edit" 2>$stderrFile

            # 執行成功且 stderr 為空 → 刪除
            if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                $stderrSize = (Get-Item $stderrFile).Length
                if ($stderrSize -eq 0) {
                    Remove-Item $stderrFile -Force
                }
            }

            return $output
        } -ArgumentList $phase2Prompt, $AgentDir, $LogDir, $timestamp, $traceId, $todoistToken -WorkingDirectory $AgentDir

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

        # Clean up Phase 2 stderr
        Get-ChildItem "$LogDir\assemble-stderr-*.log" -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-StderrIfBenign $_.FullName
        }

        # Save output to log
        $output | Out-File -FilePath $phase2LogFile -Encoding UTF8

        # Check if successful (look for completion indicators)
        $outputStr = $output -join "`n"
        if ($outputStr -match "審查完成|Step 8.*清理|知識庫.*成功|state/last-audit.json.*已更新") {
            Write-Log "Phase 2 completed successfully" "INFO"
            $phase2Success = $true

            # ─── Circuit Breaker 自動更新（knowledge API）───
            if ($knowledgeAvailable) {
                if (Get-Command Update-CircuitBreaker -ErrorAction SilentlyContinue) {
                    Update-CircuitBreaker -ApiName "knowledge" -Success $true
                    Write-Log "Circuit Breaker knowledge 更新: success（Phase 2 完成）" "INFO"
                }
            }
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
