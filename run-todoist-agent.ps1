# ============================================
# Todoist Task Planner Agent (PowerShell 7)
# ============================================
# Usage:
#   Manual: pwsh -ExecutionPolicy Bypass -File run-todoist-agent.ps1
#   Task Scheduler: same command
# ============================================

# PowerShell 7 defaults to UTF-8, explicit set for safety
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Config
$MaxDurationSeconds = 2100  # 35 minutes timeout (配合 max_tasks_per_run=3)

# Set paths
$AgentDir = "D:\Source\daily-digest-prompt"
$LogDir = "$AgentDir\logs"
$PromptFile = "$AgentDir\hour-todoist-prompt.md"
$StateFile = "$AgentDir\state\scheduler-state.json"

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$LogDir\structured" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null

# Generate log filename
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\todoist_$Timestamp.log"

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
        [string]$ErrorMsg
    )

    $run = @{
        timestamp        = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")
        agent            = "todoist"
        status           = $Status
        duration_seconds = $Duration
        error            = $ErrorMsg
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

# Start execution
$startTime = Get-Date
Write-Log "=== Todoist Agent start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

# Check prompt file exists
if (-not (Test-Path $PromptFile)) {
    Write-Log "[ERROR] prompt file not found: $PromptFile"
    Update-State -Status "failed" -Duration 0 -ErrorMsg "prompt file not found"
    exit 1
}

# Read prompt content
$PromptContent = Get-Content -Path $PromptFile -Raw -Encoding UTF8

# Check if claude is installed
$claudePath = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudePath) {
    Write-Log "[ERROR] claude not found, install: npm install -g @anthropic-ai/claude-code"
    Update-State -Status "failed" -Duration 0 -ErrorMsg "claude not found"
    exit 1
}

# Call Claude Code (with timeout protection)
Write-Log "--- calling Claude Code (timeout: ${MaxDurationSeconds}s) ---"
$success = $false
$timedOut = $false

try {
    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($prompt)
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
        $prompt | claude -p --allowedTools "Read,Bash,Write" 2>&1
    } -ArgumentList $PromptContent

    $completed = $job | Wait-Job -Timeout $MaxDurationSeconds

    if ($null -eq $completed) {
        # Timeout: retrieve partial output, then kill
        $timedOut = $true
        $partialOutput = Receive-Job $job -ErrorAction SilentlyContinue
        if ($partialOutput) {
            foreach ($line in $partialOutput) {
                Write-Log $line
            }
        }
        Stop-Job $job
        Write-Log "[TIMEOUT] Claude exceeded ${MaxDurationSeconds}s (30 min), forcefully terminated"
    }
    else {
        # Completed within timeout
        $output = Receive-Job $job
        foreach ($line in $output) {
            Write-Log $line
        }

        if ($job.State -eq 'Completed') {
            $success = $true
        }
        else {
            Write-Log "[WARN] Job ended with state: $($job.State)"
        }
    }

    Remove-Job $job -Force
}
catch {
    Write-Log "[ERROR] Claude failed: $_"
}

# Calculate duration
$duration = [int]((Get-Date) - $startTime).TotalSeconds

# Update state
if ($success) {
    Write-Log "=== done (success): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Update-State -Status "success" -Duration $duration -ErrorMsg $null
}
elseif ($timedOut) {
    Write-Log "=== done (timeout): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Update-State -Status "timeout" -Duration $duration -ErrorMsg "exceeded ${MaxDurationSeconds}s limit"
}
else {
    Write-Log "=== done (failed): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Update-State -Status "failed" -Duration $duration -ErrorMsg "claude execution failed"
}

# Clean up logs older than 7 days
Get-ChildItem -Path $LogDir -Filter "todoist_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force
