# ============================================
# Cisco AI Defense Skill Scanner (PowerShell 7)
# ============================================
# Usage:
#   .\scan-skills.ps1                          # 快速總覽（預設）
#   .\scan-skills.ps1 -Format markdown         # 完整報告
#   .\scan-skills.ps1 -Format json             # JSON 輸出
#   .\scan-skills.ps1 -UseLLM                  # 啟用 LLM 語義分析
#   .\scan-skills.ps1 -UseBehavioral           # 啟用行為分析
#   .\scan-skills.ps1 -FailOnFindings          # CI 模式（有風險則失敗）
#   .\scan-skills.ps1 -SkillName todoist       # 掃描單一 Skill
# ============================================

param(
    [ValidateSet("summary", "markdown", "json", "table", "sarif")]
    [string]$Format = "summary",
    [switch]$UseLLM,
    [switch]$UseBehavioral,
    [switch]$FailOnFindings,
    [string]$SkillName = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = "D:\Source\daily-digest-prompt"
$SkillsDir = "$AgentDir\skills"
$ScannerExe = "D:\Python311\Scripts\skill-scanner.exe"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Skill Security Scanner Report" -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verify skill-scanner is installed
if (-not (Test-Path $ScannerExe)) {
    $ScannerExe = (Get-Command skill-scanner -ErrorAction SilentlyContinue).Source
    if (-not $ScannerExe) {
        Write-Host "[ERROR] skill-scanner not found." -ForegroundColor Red
        Write-Host "  Install: uv pip install cisco-ai-skill-scanner --python D:/Python311/python.exe" -ForegroundColor Yellow
        exit 1
    }
}

# Build arguments
$scanArgs = @()
if ($UseBehavioral) { $scanArgs += "--use-behavioral" }
if ($UseLLM) { $scanArgs += "--use-llm" }
if ($FailOnFindings) { $scanArgs += "--fail-on-findings" }
$scanArgs += "--format"
$scanArgs += $Format

# Single skill or all skills
if ($SkillName) {
    $targetPath = "$SkillsDir\$SkillName"
    if (-not (Test-Path $targetPath)) {
        Write-Host "[ERROR] Skill not found: $targetPath" -ForegroundColor Red
        exit 1
    }
    Write-Host "[Scanning] $SkillName" -ForegroundColor Yellow
    & $ScannerExe scan $targetPath @scanArgs
}
else {
    Write-Host "[Scanning all skills] $SkillsDir" -ForegroundColor Yellow
    & $ScannerExe scan-all $SkillsDir --recursive @scanArgs
}

$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "  Result: ALL CLEAR" -ForegroundColor Green
}
else {
    Write-Host "  Result: FINDINGS DETECTED" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Cyan

exit $exitCode
