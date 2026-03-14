# ============================================
# 一鍵設定 Claude Agent 工作排程器
# 以系統管理員身份執行此腳本
# ============================================
param(
    [string]$Time,
    [string]$TaskName,
    [string]$Script,
    [switch]$FromHeartbeat,
    [switch]$RegisterTestTodoistEnv
)

$AgentDir = $PSScriptRoot

# ============================================
# -RegisterTestTodoistEnv: 註冊「僅執行一次」Todoist 排程環境測試（約 1 分鐘後執行，結果寫入 logs/todoist-schedule-test.log）
# ============================================
if ($RegisterTestTodoistEnv) {
    $taskName = "Claude_test-todoist-env-once"
    $logDir = "$AgentDir\logs"
    $logFile = "$logDir\todoist-schedule-test.log"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $wrapperPath = "$AgentDir\run-with-env.ps1"
    $testScript = "$AgentDir\test-todoist-schedule-env.ps1"
    if (-not (Test-Path $wrapperPath) -or -not (Test-Path $testScript)) {
        Write-Host "[錯誤] 找不到 run-with-env.ps1 或 test-todoist-schedule-env.ps1" -ForegroundColor Red
        exit 1
    }
    $runAt = (Get-Date).AddMinutes(1).ToString("HH:mm")
    $action = New-ScheduledTaskAction -Execute "pwsh.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"& { Set-Location '$AgentDir'; & '$wrapperPath' 'test-todoist-schedule-env.ps1' *> '$logFile' }`"" `
        -WorkingDirectory $AgentDir
    $trigger = New-ScheduledTaskTrigger -Once -At $runAt
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Description "一次性測試：排程環境下 Todoist API Token（run-with-env）" -RunLevel Highest | Out-Null
    Write-Host "已註冊一次性測試排程：約 $runAt 執行，結果寫入 $logFile" -ForegroundColor Green
    Write-Host "執行後請查看: Get-Content $logFile" -ForegroundColor Cyan
    exit 0
}

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
            $currentSchedule = @{ Name = $Matches[1]; Cron = ""; Script = ""; Args = ""; Description = ""; Interval = ""; Timeout = 0; Trigger = ""; Command = ""; WorkDir = ""; Delay = 0; Retry = 0; Disabled = $false }
        }
        elseif ($currentSchedule) {
            if ($line -match '^\s{4}cron:\s*"(.+)"') { $currentSchedule.Cron = $Matches[1] }
            if ($line -match '^\s{4}script:\s*(\S+)') { $currentSchedule.Script = $Matches[1] }
            if ($line -match '^\s{4}args:\s*"(.+)"') { $currentSchedule.Args = $Matches[1] }
            if ($line -match '^\s{4}description:\s*"(.+)"') { $currentSchedule.Description = $Matches[1] }
            if ($line -match '^\s{4}interval:\s*(\S+)') { $currentSchedule.Interval = $Matches[1] }
            if ($line -match '^\s{4}timeout:\s*(\d+)') { $currentSchedule.Timeout = [int]$Matches[1] }
            if ($line -match '^\s{4}trigger:\s*(\S+)') { $currentSchedule.Trigger = $Matches[1] }
            if ($line -match '^\s{4}command:\s*"(.+)"') { $currentSchedule.Command = $Matches[1] }
            if ($line -match '^\s{4}workdir:\s*"(.+)"') { $currentSchedule.WorkDir = $Matches[1] }
            if ($line -match '^\s{4}delay:\s*(\d+)') { $currentSchedule.Delay = [int]$Matches[1] }
            if ($line -match '^\s{4}retry:\s*(\d+)') { $currentSchedule.Retry = [int]$Matches[1] }
            if ($line -match '^\s{4}disabled:\s*true') { $currentSchedule.Disabled = $true }
            if ($line -match '^\s{4}disabled:\s*false') { $currentSchedule.Disabled = $false }
        }
    }
    if ($currentSchedule -and $currentSchedule.Name) { $schedules += $currentSchedule }
    # 過濾停用的排程
    $disabledCount = ($schedules | Where-Object { $_.Disabled }).Count
    $schedules = $schedules | Where-Object { -not $_.Disabled }
    if ($disabledCount -gt 0) {
        Write-Host "[略過] $disabledCount 個停用排程（disabled: true）" -ForegroundColor DarkGray
    }

    if ($schedules.Count -eq 0) {
        Write-Host "[錯誤] HEARTBEAT.md 中未找到排程定義" -ForegroundColor Red
        exit 1
    }

    Write-Host "從 HEARTBEAT.md 讀取到 $($schedules.Count) 個排程：" -ForegroundColor Cyan
    foreach ($s in $schedules) {
        # 從 cron 提取時間（分鐘 + 小時）
        # 支援 */N 格式（如 "*/5 * * * *"）→ 自動轉為 interval 模式
        if ($s.Cron -match '^\*/(\d+)\s') {
            $autoInterval = [int]$Matches[1]
            if (-not $s.Interval) {
                $s | Add-Member -NotePropertyName 'Interval' -NotePropertyValue "${autoInterval}m" -Force
            }
            $cronTime = "00:00"  # 從午夜起算，持續全天
        } elseif ($s.Cron -match '^(\d+)\s+(\d+)') {
            $minute = [int]$Matches[1]
            $hour = [int]$Matches[2]
            $cronTime = "{0:D2}:{1:D2}" -f $hour, $minute
        } else {
            $cronTime = "08:00"
        }
        $taskNameFromHB = "Claude_$($s.Name)"
        $timeoutInfo = if ($s.Timeout -gt 0) { "$($s.Timeout)s" } else { "無限制" }
        $timeStr   = if ($s.Trigger -eq 'startup') { "開機啟動" } else { $cronTime }
        $scriptStr = if ($s.Command) { $s.Command } else { $s.Script }
        Write-Host "  - $taskNameFromHB | $timeStr | $scriptStr | timeout=$timeoutInfo | $($s.Description)" -ForegroundColor White

        $scriptPath = "$AgentDir\$($s.Script)"
        if (-not $s.Command -and -not (Test-Path $scriptPath)) {
            Write-Host "    [警告] 腳本不存在: $scriptPath，跳過" -ForegroundColor Yellow
            continue
        }

        # 移除舊排程
        $existing = Get-ScheduledTask -TaskName $taskNameFromHB -ErrorAction SilentlyContinue
        if ($existing) { Unregister-ScheduledTask -TaskName $taskNameFromHB -Confirm:$false }

        # Action：command 欄位（node/uv 等）優先，其次 pwsh Script
        if ($s.Command) {
            $workDir = if ($s.WorkDir) { $s.WorkDir } else { $AgentDir }
            $action = New-ScheduledTaskAction -Execute "pwsh.exe" `
                -Argument "-NoProfile -WindowStyle Hidden -Command `"Set-Location '$workDir'; $($s.Command)`"" `
                -WorkingDirectory $workDir
        } else {
            # 經由 run-with-env.ps1 載入 .env，確保排程時 Token 等變數可用
            $wrapperPath = "$AgentDir\run-with-env.ps1"
            $argStr = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wrapperPath`" `"$($s.Script)`""
            if ($s.Args) {
                $argStr += " $($s.Args)"
            }
            $action = New-ScheduledTaskAction -Execute "pwsh.exe" `
                -Argument $argStr `
                -WorkingDirectory $AgentDir
        }

        # Trigger：startup 或 daily cron
        if ($s.Trigger -eq 'startup') {
            $trigger = New-ScheduledTaskTrigger -AtStartup
            if ($s.Delay -gt 0) {
                $trigger.Delay = "PT$($s.Delay)S"
                Write-Host "    觸發條件：開機啟動（延遲 $($s.Delay)s）" -ForegroundColor DarkCyan
            } else {
                Write-Host "    觸發條件：開機啟動" -ForegroundColor DarkCyan
            }
        } else {
            $trigger = New-ScheduledTaskTrigger -Daily -At $cronTime
        }

        # 支援間隔排程（如 interval: 60m → 每小時重複）
        if ($s.Interval -match '^(\d+)m$') {
            $intervalMinutes = [int]$Matches[1]
            # 從 cron 解析小時範圍（如 "0 9-22 * * *" → 起始 9, 結束 22）
            # */N 格式 → 全天 24h
            $durationHours = 14  # 預設持續時間
            if ($s.Cron -match '^\*/\d+') {
                $durationHours = 24  # */N 全天持續
            } elseif ($s.Cron -match '^\d+\s+(\d+)-(\d+)') {
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

        $settingsParams = @{
            AllowStartIfOnBatteries    = $true
            DontStopIfGoingOnBatteries = $true
            StartWhenAvailable         = $true
            RunOnlyIfNetworkAvailable  = $true
        }
        if ($s.Timeout -gt 0) {
            $settingsParams.ExecutionTimeLimit = New-TimeSpan -Seconds $s.Timeout
            Write-Host "    超時限制：$($s.Timeout)s ($([math]::Round($s.Timeout / 60, 1)) min)" -ForegroundColor DarkCyan
        }
        if ($s.Interval) {
            $settingsParams.MultipleInstances = "IgnoreNew"
            Write-Host "    防重疊：IgnoreNew" -ForegroundColor DarkCyan
        }
        $settings = New-ScheduledTaskSettingsSet @settingsParams

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
    -Execute "pwsh.exe" `
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
    & pwsh -ExecutionPolicy Bypass -File $ScriptPath
}
