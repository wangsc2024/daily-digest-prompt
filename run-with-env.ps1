# ============================================
# 排程用 Wrapper：先載入 .env 再執行目標腳本
# ============================================
# 解決 Windows 排程器執行時未載入 .env 的問題。
# Usage: pwsh -File run-with-env.ps1 <script> [args...]
# 例:   pwsh -File run-with-env.ps1 run-todoist-agent-team.ps1
# ============================================

$AgentDir = $PSScriptRoot
$envFile = Join-Path $AgentDir ".env"

if (-not (Test-Path $envFile)) {
    Write-Host "[WARN] run-with-env: .env 不存在於 $envFile" -ForegroundColor Yellow
} else {
    # 使用 UTF-8 無 BOM 讀取，避免排程環境下第一行因 BOM 導致變數無法解析
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $raw = [System.IO.File]::ReadAllText($envFile, $utf8NoBom)
    $lines = $raw -split "`r?`n"
    foreach ($line in $lines) {
        $line = $line.Trim()
        # 若首行含 BOM（僅影響第一行），移除
        if ($line.Length -gt 0 -and [int][char]$line[0] -eq 0xFEFF) { $line = $line.Substring(1) }
        if ($line -match '^\s*#|^\s*$') { continue }
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $key = $Matches[1]
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
            $logKeys = @("TODOIST_API_TOKEN", "OPENROUTER_API_KEY", "BOT_API_SECRET", "NTFY_TOPIC")
            if ($key -in $logKeys -and $val) {
                Write-Host "[run-with-env] $key loaded from .env (length=$($val.Length))" -ForegroundColor DarkCyan
            }
        }
    }
}

# 切換到專案目錄，確保後續相對路徑正確
Set-Location $AgentDir

$scriptName = $args[0]
if (-not $scriptName) {
    Write-Host "[錯誤] 用法: pwsh -File run-with-env.ps1 <script> [args...]" -ForegroundColor Red
    exit 1
}

$scriptPath = Join-Path $AgentDir $scriptName
# 路徑遍歷防護：確保解析後的絕對路徑仍在專案目錄內
$resolvedPath = [System.IO.Path]::GetFullPath($scriptPath)
if (-not $resolvedPath.StartsWith($AgentDir)) {
    Write-Host "[錯誤] 路徑遍歷攻擊偵測: $scriptName 超出專案目錄" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $resolvedPath)) {
    Write-Host "[錯誤] 找不到腳本: $resolvedPath" -ForegroundColor Red
    exit 1
}

$scriptArgs = $args[1..($args.Length - 1)]
& $resolvedPath @scriptArgs
exit $LASTEXITCODE
