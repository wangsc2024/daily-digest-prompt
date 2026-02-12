# ============================================
# 一鍵設定 Claude Agent 工作排程器
# 以系統管理員身份執行此腳本
# ============================================
param(
    [string]$Time,
    [string]$TaskName,
    [string]$Script
)

if (-not $TaskName) {
    $TaskName = Read-Host "請輸入排程名稱（預設 ClaudeDailyDigest）"
    if ([string]::IsNullOrWhiteSpace($TaskName)) {
        $TaskName = "ClaudeDailyDigest"
    }
}
$AgentDir = "D:\Source\daily-digest-prompt"

# 決定執行腳本
if (-not $Script) {
    $ScriptPath = "$AgentDir\run-agent.ps1"
} else {
    $ScriptPath = "$AgentDir\$Script"
}

# 檢查腳本是否存在
if (-not (Test-Path $ScriptPath)) {
    Write-Host "[錯誤] 找不到 $ScriptPath，請先將檔案放到正確位置" -ForegroundColor Red
    exit 1
}

# 刪除舊排程（如果存在）
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "移除舊排程..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# 建立排程
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`"" `
    -WorkingDirectory $AgentDir

# 決定執行時間
if (-not $Time) {
    $Time = Read-Host "請輸入每日執行時間（格式 HH:mm，預設 08:00）"
    if ([string]::IsNullOrWhiteSpace($Time)) {
        $Time = "08:00"
    }
}

# 驗證時間格式
if ($Time -notmatch '^\d{1,2}:\d{2}$') {
    Write-Host "[錯誤] 時間格式不正確，請使用 HH:mm（例如 08:00、17:30）" -ForegroundColor Red
    exit 1
}

try {
    [datetime]::ParseExact($Time, "HH:mm", $null) | Out-Null
} catch {
    Write-Host "[錯誤] 無效的時間值: $Time" -ForegroundColor Red
    exit 1
}

$Trigger = New-ScheduledTaskTrigger -Daily -At $Time

# 設定：即使未登入也執行、錯過時間立即補執行
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# 註冊排程
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "每日 $Time Claude Agent 摘要通知" `
    -RunLevel Highest

Write-Host ""
Write-Host "✅ 排程建立成功！" -ForegroundColor Green
Write-Host "   名稱: $TaskName" 
Write-Host "   時間: 每天 $Time"
Write-Host "   腳本: $ScriptPath"
Write-Host ""
Write-Host "常用指令：" -ForegroundColor Cyan
Write-Host "  手動執行:  schtasks /run /tn $TaskName"
Write-Host "  查看排程:  schtasks /query /tn $TaskName /v"
Write-Host "  刪除排程:  schtasks /delete /tn $TaskName /f"
Write-Host ""

# 詢問是否立即測試
$test = Read-Host "是否立即測試執行？(y/n)"
if ($test -eq "y") {
    Write-Host "開始測試..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File $ScriptPath
}
