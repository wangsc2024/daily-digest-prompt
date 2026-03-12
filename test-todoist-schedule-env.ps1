# ============================================
# 模擬排程環境下 Todoist API Token 測試
# ============================================
# 用法（與排程相同路徑，由 run-with-env.ps1 載入 .env 後執行）:
#   pwsh -ExecutionPolicy Bypass -File run-with-env.ps1 test-todoist-schedule-env.ps1
# 或手動（腳本會自行從 .env 載入）:
#   pwsh -ExecutionPolicy Bypass -File test-todoist-schedule-env.ps1
#
# 註冊「僅執行一次」測試排程（約 1 分鐘後執行，結果寫入 logs/todoist-schedule-test.log）:
#   pwsh -ExecutionPolicy Bypass -File setup-scheduler.ps1 -RegisterTestTodoistEnv
# ============================================

$AgentDir = $PSScriptRoot
$envFile = Join-Path $AgentDir ".env"

# 若尚未從 run-with-env 載入，則從 .env 讀取（與 run-with-env 相同邏輯）
if (-not $env:TODOIST_API_TOKEN) {
    if (Test-Path $envFile) {
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        $raw = [System.IO.File]::ReadAllText($envFile, $utf8NoBom)
        $lines = $raw -split "`r?`n"
        foreach ($line in $lines) {
            $line = $line.Trim()
            if ($line.Length -gt 0 -and [int][char]$line[0] -eq 0xFEFF) { $line = $line.Substring(1) }
            if ($line -match '^\s*#|^\s*$') { continue }
            if ($line -match '^TODOIST_API_TOKEN=(.*)$') {
                $env:TODOIST_API_TOKEN = $Matches[1].Trim().Trim('"').Trim("'")
                break
            }
        }
    }
}

$token = $env:TODOIST_API_TOKEN
Write-Host "[test-todoist-schedule-env] TODOIST_API_TOKEN present: $(if ($token) { "yes (length=$($token.Length))" } else { "NO" })"

if (-not $token) {
    Write-Host "[test-todoist-schedule-env] [FAIL] No token - exit 1"
    exit 1
}

# 使用與專案一致的 api/v1 端點（rest/v2 已 410 Gone）
try {
    $headers = @{ "Authorization" = "Bearer $token" }
    $response = Invoke-RestMethod -Uri "https://api.todoist.com/api/v1/tasks/filter?query=today" -Method Get -Headers $headers -ErrorAction Stop
    $count = if ($response -is [array]) { $response.Count } else { 0 }
    Write-Host "[test-todoist-schedule-env] [OK] Todoist API 200 - today tasks: $count"
    exit 0
}
catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 401) {
        Write-Host "[test-todoist-schedule-env] [401] Todoist API Unauthorized - token 無效或過期"
        exit 1
    }
    Write-Host "[test-todoist-schedule-env] [ERROR] $($_.Exception.Message) (status: $statusCode)"
    exit 1
}
