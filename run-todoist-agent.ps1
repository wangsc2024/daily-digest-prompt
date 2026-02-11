# ============================================
# Todoist Task Planner Agent (Windows PowerShell)
# ============================================
# Usage:
#   Manual: powershell -ExecutionPolicy Bypass -File run-todoist-agent.ps1
#   Task Scheduler: same command
# ============================================

# Set UTF-8 (console + code page)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# Set paths
$AgentDir = "D:\Source\daily-digest-prompt"
$LogDir = "$AgentDir\logs"
$PromptFile = "$AgentDir\hour-todoist-prompt.md"

# Create logs directory
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Generate log filename
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\todoist_$Timestamp.log"

# Write-Log function (UTF-8 without BOM, fixes Tee-Object UTF-16LE issue)
function Write-Log {
    param([string]$Message)
    Write-Host $Message
    [System.IO.File]::AppendAllText($LogFile, "$Message`r`n", [System.Text.Encoding]::UTF8)
}

# Start execution
Write-Log "=== Todoist Agent start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

# Check prompt file exists
if (-not (Test-Path $PromptFile)) {
    Write-Log "[ERROR] prompt file not found: $PromptFile"
    exit 1
}

# Read prompt content
$PromptContent = Get-Content -Path $PromptFile -Raw -Encoding UTF8

# Check if claude is installed
$claudePath = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudePath) {
    Write-Log "[ERROR] claude not found, install: npm install -g @anthropic-ai/claude-code"
    exit 1
}

# Call Claude Code
Write-Log "--- calling Claude Code ---"
try {
    $PromptContent | claude -p --allowedTools "Read,Bash,Write" 2>&1 | ForEach-Object {
        Write-Log $_
    }
}
catch {
    Write-Log "[ERROR] Claude failed: $_"
}

Write-Log "=== done: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

# Clean up logs older than 7 days
Get-ChildItem -Path $LogDir -Filter "todoist_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force
