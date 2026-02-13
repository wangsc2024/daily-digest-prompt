# ============================================
# 一鍵設定 Claude Agent 工作排程器
# 以系統管理員身份執行此腳本
# ============================================
param(
    [string]$Time,
    [string]$TaskName,
    [string]$Script,
    [switch]$FromHeartbeat
)

$AgentDir = "D:\Source\daily-digest-prompt"

# ============================================
# -FromHeartbeat: 從 HEARTBEAT.md 讀取並批次建立排程
# ============================================
if ($FromHeartbeat) {
    $heartbeatFile = "$AgentDir\HEARTBEAT.md"
    if (-not (Test-Path $heartbeatFile)) {
        Write-Host "[錯誤] 找不到 HEARTBEAT.md" -ForegroundColor Red
        exit 1
    }

    $content = Get-Content -Path $heartbeatFile -Raw -Encoding UTF8
    # 從 YAML frontmatter 解析排程（簡易 regex）
    $schedules = @()
    $inYaml = $false
    $currentSchedule = $null

    foreach ($line in (Get-Content -Path $heartbeatFile -Encoding UTF8)) {
        if ($line -match '^---') {
            if ($inYaml) { break }
            $inYaml = $true
            continue
        }
        if (-not $inYaml) { continue }

        if ($line -match '^\s{2}(\S+):$') {
            if ($currentSchedule -and $currentSchedule.Name) {
                $schedules += $currentSchedule
            }
            $currentSchedule = @{ Name = $Matches[1]; Cron = ""; Script = ""; Description = ""; Interval = "" }
        }
        elseif ($currentSchedule) {
            if ($line -match '^\s{4}cron:\s*"(.+)"') { $currentSchedule.Cron = $Matches[1] }
            if ($line -match '^\s{4}script:\s*(\S+)') { $currentSchedule.Script = $Matches[1] }
            if ($line -match '^\s{4}description:\s*"(.+)"') { $currentSchedule.Description = $Matches[1] }
            if ($line -match '^\s{4}interval:\s*(\S+)') { $currentSchedule.Interval = $Matches[1] }
        }
    }
    if ($currentSchedule -and $currentSchedule.Name) { $schedules += $currentSchedule }

    if ($schedules.Count -eq 0) {
        Write-Host "[錯誤] HEARTBEAT.md 中未找到排程定義" -ForegroundColor Red
        exit 1
    }

    Write-Host "從 HEARTBEAT.md 讀取到 $($schedules.Count) 個排程：" -ForegroundColor Cyan
    foreach ($s in $schedules) {
        # 從 cron 提取時間（簡易：取分鐘和小時）
        if ($s.Cron -match '^\d+\s+(\d+)') {
            $hour = $Matches[1]
            $cronTime = "{0:D2}:00" -f [int]$hour
        } else {
            $cronTime = "08:00"
        }
        $taskNameFromHB = "Claude_$($s.Name)"
        Write-Host "  - $taskNameFromHB | $cronTime | $($s.Script) | $($s.Description)" -ForegroundColor White

        $scriptPath = "$AgentDir\$($s.Script)"
        if (-not (Test-Path $scriptPath)) {
            Write-Host "    [警告] 腳本不存在: $scriptPath，跳過" -ForegroundColor Yellow
            continue
        }

        # 移除舊排程
        $existing = Get-ScheduledTask -TaskName $taskNameFromHB -ErrorAction SilentlyContinue
        if ($existing) { Unregister-ScheduledTask -TaskName $taskNameFromHB -Confirm:$false }

        $action = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`"" `
            -WorkingDirectory $AgentDir
        $trigger = New-ScheduledTaskTrigger -Daily -At $cronTime

        # 支援間隔排程（如 interval: 60m → 每小時重複）
        if ($s.Interval -match '^(\d+)m$') {
            $intervalMinutes = [int]$Matches[1]
            # 從 cron 解析小時範圍（如 "0 9-22 * * *" → 起始 9, 結束 22）
            $durationHours = 14  # 預設持續時間
            if ($s.Cron -match '^\d+\s+(\d+)-(\d+)') {
                $startHour = [int]$Matches[1]
                $endHour = [int]$Matches[2]
                $durationHours = $endHour - $startHour
            }
            # 從 -Once 觸發器借用 Repetition 物件（-Daily 不直接支援 -RepetitionInterval）
            $tempTrigger = New-ScheduledTaskTrigger -Once -At $cronTime `
                -RepetitionInterval (New-TimeSpan -Minutes $intervalMinutes) `
                -RepetitionDuration (New-TimeSpan -Hours $durationHours)
            $trigger.Repetition = $tempTrigger.Repetition
            Write-Host "    間隔模式：每 ${intervalMinutes} 分鐘，持續 ${durationHours} 小時" -ForegroundColor DarkCyan
        }

        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable

        Register-ScheduledTask -TaskName $taskNameFromHB -Action $action -Trigger $trigger `
            -Settings $settings -Description $s.Description -RunLevel Highest | Out-Null

        Write-Host "    ✅ 已建立" -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "全部完成！" -ForegroundColor Green
    exit 0
}

# ============================================
# 傳統模式：手動指定參數
# ============================================
if (-not $TaskName) {
    $TaskName = Read-Host "請輸入排程名稱（預設 ClaudeDailyDigest）"
    if ([string]::IsNullOrWhiteSpace($TaskName)) {
        $TaskName = "ClaudeDailyDigest"
    }
}

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
