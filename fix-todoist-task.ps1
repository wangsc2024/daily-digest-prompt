#Requires -RunAsAdministrator
# Claude_todoist-agent: 改為執行 Todoist 團隊並行模式腳本

$task = Get-ScheduledTask -TaskName "Claude_todoist-agent"
$task.Actions[0].Arguments = '-ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\Source\daily-digest-prompt\run-todoist-agent-team.ps1"'
$task | Set-ScheduledTask | Out-Null

# 驗證
$updated = Get-ScheduledTask -TaskName "Claude_todoist-agent"
Write-Host "OK  Execute: $($updated.Actions[0].Execute)" -ForegroundColor Green
Write-Host "OK  Args:    $($updated.Actions[0].Arguments)" -ForegroundColor Green
Write-Host "`nDone. Press Enter to close..."
Read-Host
