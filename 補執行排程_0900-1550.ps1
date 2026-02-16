# 補執行 2026-02-16 09:00-15:50 未執行的排程
# 請在獨立 PowerShell 7 窗口中執行此腳本

$AgentDir = "d:\Source\daily-digest-prompt"
Set-Location $AgentDir

Write-Host "=== 開始補執行排程 ===" -ForegroundColor Cyan
Write-Host "時間範圍: 09:00-15:50" -ForegroundColor Cyan
Write-Host "總計: 15 個排程 (1 摘要 + 7 單一 + 7 團隊)" -ForegroundColor Cyan
Write-Host ""

$schedules = @(
    @{ Time = "09:00"; Script = "run-todoist-agent.ps1"; Name = "Todoist 單一" }
    @{ Time = "09:30"; Script = "run-todoist-agent-team.ps1"; Name = "Todoist 團隊" }
    @{ Time = "10:00"; Script = "run-todoist-agent.ps1"; Name = "Todoist 單一" }
    @{ Time = "10:30"; Script = "run-todoist-agent-team.ps1"; Name = "Todoist 團隊" }
    @{ Time = "11:00"; Script = "run-todoist-agent.ps1"; Name = "Todoist 單一" }
    @{ Time = "11:15"; Script = "run-agent-team.ps1"; Name = "每日摘要" }
    @{ Time = "11:30"; Script = "run-todoist-agent-team.ps1"; Name = "Todoist 團隊" }
    @{ Time = "12:00"; Script = "run-todoist-agent.ps1"; Name = "Todoist 單一" }
    @{ Time = "12:30"; Script = "run-todoist-agent-team.ps1"; Name = "Todoist 團隊" }
    @{ Time = "13:00"; Script = "run-todoist-agent.ps1"; Name = "Todoist 單一" }
    @{ Time = "13:30"; Script = "run-todoist-agent-team.ps1"; Name = "Todoist 團隊" }
    @{ Time = "14:00"; Script = "run-todoist-agent.ps1"; Name = "Todoist 單一" }
    @{ Time = "14:30"; Script = "run-todoist-agent-team.ps1"; Name = "Todoist 團隊" }
    @{ Time = "15:00"; Script = "run-todoist-agent.ps1"; Name = "Todoist 單一" }
    @{ Time = "15:30"; Script = "run-todoist-agent-team.ps1"; Name = "Todoist 團隊" }
)

$total = $schedules.Count
$current = 0

foreach ($schedule in $schedules) {
    $current++
    Write-Host "[$current/$total] $($schedule.Time) - $($schedule.Name)" -ForegroundColor Yellow

    $startTime = Get-Date
    & ".\$($schedule.Script)"
    $duration = (Get-Date) - $startTime

    Write-Host "  完成 (耗時: $($duration.TotalSeconds.ToString('F1'))s)" -ForegroundColor Green
    Write-Host ""

    # 短暫延遲避免過載
    if ($current -lt $total) {
        Start-Sleep -Seconds 3
    }
}

Write-Host "=== 全部完成 ===" -ForegroundColor Green
Write-Host "總耗時: $((Get-Date) - $startTime).TotalMinutes.ToString('F1') 分鐘" -ForegroundColor Green
