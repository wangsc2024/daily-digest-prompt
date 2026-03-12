# Check and optionally set Claude_todoist-team ExecutionTimeLimit to 4000s (67 min)
# 若僅有 7 分鐘會導致 Phase 1 被強制結束，需改為 4000 秒。執行修正時請「以系統管理員身分」執行 PowerShell。
param([switch]$SetTo4000)

$taskName = 'Claude_todoist-team'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Task $taskName not found."
    exit 1
}

$info = Get-ScheduledTaskInfo -InputObject $task
$limit = $info.ExecutionTimeLimit
$totalSec = $limit.TotalSeconds

Write-Host "Current ExecutionTimeLimit: $($limit.ToString())"
Write-Host "TotalSeconds: $totalSec"
Write-Host "Interpretation: $([math]::Round($totalSec/60, 1)) minutes"

if ($totalSec -lt 600) {
    Write-Host "WARN: Limit is under 10 minutes - Phase 1 can be killed! Run with -SetTo4000 as Administrator to fix."
}

if ($SetTo4000) {
    $newSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 4000) `
        -MultipleInstances IgnoreNew
    Set-ScheduledTask -TaskName $taskName -Settings $newSettings -ErrorAction Stop
    Write-Host "Updated ExecutionTimeLimit to 4000s (about 67 min). Verify with: schtasks /Query /TN Claude_todoist-team /FO LIST /V | findstr Stop"
}
