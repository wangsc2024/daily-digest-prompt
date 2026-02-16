# ============================================
# Daily System Audit Agent (PowerShell 7)
# ============================================
# Usage:
#   Manual: pwsh -ExecutionPolicy Bypass -File run-system-audit.ps1
#   Task Scheduler: same command (daily 00:40)
# ============================================

# PowerShell 7 defaults to UTF-8, explicit set for safety
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Set paths
$AgentDir = $PSScriptRoot
$LogDir = "$AgentDir\logs"
$PromptFile = "$AgentDir\daily-system-audit-prompt.md"
$StateFile = "$AgentDir\state\scheduler-state.json"
$AuditStateFile = "$AgentDir\state\last-audit.json"

# Config
$MaxRetries = 1
$RetryDelaySeconds = 60
$TimeoutSeconds = 1800  # 30 minutes

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$LogDir\structured" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\results" | Out-Null
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
        agent = "system-audit"
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
$logFile = "$LogDir\system-audit-$timestamp.log"

Write-Log "=== Daily System Audit Started ===" "INFO"
Write-Log "Log file: $logFile" "INFO"
Write-Log "Prompt: $PromptFile" "INFO"

# Check if prompt file exists
if (-not (Test-Path $PromptFile)) {
    Write-Log "Prompt file not found: $PromptFile" "ERROR"
    Update-SchedulerState -Status "error" -Message "Prompt file not found" -ExitCode 1
    exit 1
}

# Execute Claude Agent
$attempt = 1
$maxAttempts = $MaxRetries + 1
$success = $false

while ($attempt -le $maxAttempts -and -not $success) {
    if ($attempt -gt 1) {
        Write-Log "Retry attempt $attempt of $maxAttempts after $RetryDelaySeconds seconds delay..." "WARN"
        Start-Sleep -Seconds $RetryDelaySeconds
    }

    Write-Log "Starting system audit (attempt $attempt)..." "INFO"

    try {
        # Start Claude agent with timeout
        $job = Start-Job -ScriptBlock {
            param($promptFile, $agentDir)
            Set-Location $agentDir
            $OutputEncoding = [System.Text.Encoding]::UTF8
            claude -p $promptFile --allowedTools "Read,Bash,Glob,Grep,Write,Edit,Task" 2>&1
        } -ArgumentList $PromptFile, $AgentDir -WorkingDirectory $AgentDir

        # Wait with timeout
        $completed = Wait-Job -Job $job -Timeout $TimeoutSeconds

        if ($null -eq $completed) {
            Write-Log "Agent timed out after $TimeoutSeconds seconds" "ERROR"
            Stop-Job -Job $job
            Remove-Job -Job $job -Force
            $attempt++
            continue
        }

        # Get output
        $output = Receive-Job -Job $job
        Remove-Job -Job $job -Force

        # Save output to log
        $output | Out-File -FilePath $logFile -Encoding UTF8

        # Check if successful (look for success indicators)
        $outputStr = $output -join "`n"
        if ($outputStr -match "審查完成|Phase 6.*成功|知識庫.*成功") {
            Write-Log "System audit completed successfully" "INFO"
            Update-SchedulerState -Status "success" -Message "Audit completed" -ExitCode 0
            $success = $true
        } else {
            Write-Log "Agent execution completed but may have issues" "WARN"
            if ($attempt -eq $maxAttempts) {
                Update-SchedulerState -Status "warning" -Message "Completed with warnings" -ExitCode 0
                $success = $true
            }
        }
    } catch {
        Write-Log "Error executing agent: $_" "ERROR"
        if ($attempt -eq $maxAttempts) {
            Update-SchedulerState -Status "error" -Message $_.Exception.Message -ExitCode 1
        }
    }

    $attempt++
}

if (-not $success) {
    Write-Log "System audit failed after $maxAttempts attempts" "ERROR"
    exit 1
}

Write-Log "=== Daily System Audit Completed ===" "INFO"
Write-Log "Log saved to: $logFile" "INFO"

# Check if audit state was updated
if (Test-Path $AuditStateFile) {
    $auditState = Get-Content $AuditStateFile -Encoding UTF8 | ConvertFrom-Json
    Write-Log "Last audit score: $($auditState.total_score)" "INFO"
    Write-Log "Grade: $($auditState.grade)" "INFO"
}

exit 0
