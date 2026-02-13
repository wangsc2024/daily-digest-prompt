# ============================================
# Claude Agent Scheduled Script (Windows PowerShell)
# ============================================
# Usage:
#   Manual: powershell -ExecutionPolicy Bypass -File run-agent.ps1
#   Task Scheduler: same command
# ============================================

# Set UTF-8 (console + code page)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# Set paths
$AgentDir = "D:\Source\daily-digest-prompt"
$LogDir = "$AgentDir\logs"
$PromptFile = "$AgentDir\daily-digest-prompt.md"
$StateFile = "$AgentDir\state\scheduler-state.json"

# Config
$MaxRetries = 1
$RetryDelaySeconds = 120

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\context" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\cache" | Out-Null

# Generate log filename
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\$Timestamp.log"

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
        agent            = "daily-digest"
        status           = $Status
        duration_seconds = $Duration
        error            = $ErrorMsg
        log_file         = (Split-Path -Leaf $LogFile)
    }

    if (Test-Path $StateFile) {
        $stateJson = Get-Content -Path $StateFile -Raw -Encoding UTF8
        $state = $stateJson | ConvertFrom-Json
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
Write-Log "=== Claude Agent start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

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

# Call Claude Code with retry
$attempt = 0
$success = $false

while ($attempt -le $MaxRetries) {
    if ($attempt -gt 0) {
        Write-Log "[RETRY] Attempt $($attempt + 1) after $RetryDelaySeconds seconds delay..."
        Start-Sleep -Seconds $RetryDelaySeconds
    }

    Write-Log "--- calling Claude Code (attempt $($attempt + 1)) ---"
    $attemptStart = Get-Date

    try {
        $PromptContent | claude -p --allowedTools "Read,Bash,Write" 2>&1 | ForEach-Object {
            Write-Log $_
        }

        if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
            $success = $true
            break
        }
        else {
            Write-Log "[WARN] Claude exited with code: $LASTEXITCODE"
        }
    }
    catch {
        Write-Log "[ERROR] Claude failed: $_"
    }

    $attempt++
}

# Calculate duration
$duration = [int]((Get-Date) - $startTime).TotalSeconds

# Update state
if ($success) {
    Write-Log "=== done (success): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Update-State -Status "success" -Duration $duration -ErrorMsg $null
}
else {
    Write-Log "=== done (failed after $($MaxRetries + 1) attempts): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Update-State -Status "failed" -Duration $duration -ErrorMsg "all attempts failed"
}

# Clean up logs older than 7 days
Get-ChildItem -Path $LogDir -Filter "*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force
