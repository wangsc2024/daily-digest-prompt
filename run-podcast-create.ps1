# ============================================================
# run-podcast-create.ps1
# Podcast 生成任務（podcast_create）：非佛學類知識庫筆記 → AI 雙主持人 MP3
# ============================================================
# 用法：
#   pwsh -ExecutionPolicy Bypass -File run-podcast-create.ps1
#   pwsh -ExecutionPolicy Bypass -File run-podcast-create.ps1 -SkipTts  # 僅選材與腳本，不 TTS/R2
# ============================================================

param(
    [switch]$SkipTts = $false,
    [switch]$DryRun = $false
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = $PSScriptRoot
$LogDir = Join-Path $AgentDir "logs"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "podcast-create_$Timestamp.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log($Message) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "=== run-podcast-create 啟動 ==="
Write-Log "SkipTts=$SkipTts, DryRun=$DryRun"

# ─── 確認 KB 服務 ───
try {
    $null = Invoke-RestMethod -Uri "http://localhost:3000/api/health" -TimeoutSec 5
    Write-Log "KB 服務正常"
} catch {
    Write-Log "[ERROR] 知識庫服務 (localhost:3000) 未啟動，請先啟動 KB"
    exit 1
}

# ─── 執行 run_podcast_create.py ───
$args = @()
if ($SkipTts) { $args += "--skip-tts" }
if ($DryRun)  { $args += "--dry-run" }

Write-Log "執行 tools/run_podcast_create.py..."
$rc = 0
try {
    & uv run --project $AgentDir python (Join-Path $AgentDir "tools\run_podcast_create.py") @args
    $rc = $LASTEXITCODE
} catch {
    Write-Log "[ERROR] 執行失敗: $_"
    $rc = 1
}

Write-Log "=== 結束 (exit $rc) ==="
exit $rc
