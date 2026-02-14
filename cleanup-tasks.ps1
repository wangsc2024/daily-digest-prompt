#Requires -RunAsAdministrator
# 排程任務整理（需以系統管理員身分執行）
# 1) 刪除舊排程  2) 修改引擎  3) 重建觸發時間

Write-Host "=== Step 1: 刪除舊排程 ===" -ForegroundColor Yellow
$toDelete = @("MyDigest01", "MyDigest", "ClaudeDailyDigest", "MyDigest02", "MyDigest03", "MyDigest04")
foreach ($name in $toDelete) {
    try {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction Stop
        Write-Host "  OK  deleted: $name" -ForegroundColor Green
    } catch {
        Write-Host "  ERR $name : $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`n=== Step 2: MyDigest05 / MyDigest06 引擎改為 pwsh.exe ===" -ForegroundColor Yellow
foreach ($name in @("MyDigest05", "MyDigest06")) {
    try {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
        $task.Actions[0].Execute = "pwsh.exe"
        $task | Set-ScheduledTask | Out-Null
        Write-Host "  OK  $name -> pwsh.exe" -ForegroundColor Green
    } catch {
        Write-Host "  ERR $name : $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`n=== Step 3: 重建 Claude_daily-digest (02:15, 11:15, 16:15) ===" -ForegroundColor Yellow
try {
    Unregister-ScheduledTask -TaskName "Claude_daily-digest" -Confirm:$false -ErrorAction SilentlyContinue

    $action = New-ScheduledTaskAction `
        -Execute "pwsh.exe" `
        -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\Source\daily-digest-prompt\run-agent-team.ps1"' `
        -WorkingDirectory "D:\Source\daily-digest-prompt"

    $triggers = @(
        New-ScheduledTaskTrigger -Daily -At "02:15"
        New-ScheduledTaskTrigger -Daily -At "11:15"
        New-ScheduledTaskTrigger -Daily -At "16:15"
    )

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

    Register-ScheduledTask `
        -TaskName "Claude_daily-digest" `
        -Action $action `
        -Trigger $triggers `
        -Settings $settings `
        -Description "每日摘要（團隊並行 5 Agent + 組裝）02:15, 11:15, 16:15" | Out-Null

    Write-Host "  OK  Claude_daily-digest registered (02:15, 11:15, 16:15)" -ForegroundColor Green
} catch {
    Write-Host "  ERR Claude_daily-digest : $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Step 4: 重建 Claude_todoist-agent (每 30 分鐘, 02:00-23:00) ===" -ForegroundColor Yellow
try {
    Unregister-ScheduledTask -TaskName "Claude_todoist-agent" -Confirm:$false -ErrorAction SilentlyContinue

    $action = New-ScheduledTaskAction `
        -Execute "pwsh.exe" `
        -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\Source\daily-digest-prompt\run-todoist-agent.ps1"' `
        -WorkingDirectory "D:\Source\daily-digest-prompt"

    # Daily trigger at 02:00 with 30-min repetition for 21 hours (02:00 - 23:00)
    $trigger = New-ScheduledTaskTrigger -Daily -At "02:00"
    $trigger.Repetition = (New-CimInstance -ClassName MSFT_TaskRepetitionPattern `
        -Namespace Root/Microsoft/Windows/TaskScheduler -ClientOnly -Property @{
        Interval    = "PT30M"
        Duration    = "PT21H"
        StopAtDurationEnd = $false
    })

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName "Claude_todoist-agent" `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Todoist 任務規劃（每 30 分鐘，02:00-23:00）" | Out-Null

    Write-Host "  OK  Claude_todoist-agent registered (every 30min, 02:00-23:00)" -ForegroundColor Green
} catch {
    Write-Host "  ERR Claude_todoist-agent : $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== 驗證結果 ===" -ForegroundColor Yellow
Get-ScheduledTask | Where-Object { $_.TaskName -match "Claude|MyDigest" } |
    ForEach-Object {
        $info = $_ | Get-ScheduledTaskInfo
        Write-Host ("  {0,-25} | {1,-6} | Execute: {2} | Next: {3}" -f $_.TaskName, $_.State, $_.Actions[0].Execute, $info.NextRunTime) -ForegroundColor Cyan
    }

Write-Host "`nDone. Press Enter to close..." -ForegroundColor Green
Read-Host
