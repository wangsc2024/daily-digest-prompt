# ============================================================
# Chatroom-Scheduler Watchdog
# 職責：每 10 分鐘由 Windows Task Scheduler 觸發，確保
#       chatroom-scheduler.py 持續運行；死掉即自動重啟 + ntfy 告警。
# ============================================================
$ProjectDir = Split-Path $PSScriptRoot -Parent   # d:\Source\daily-digest-prompt
$LogDir     = Join-Path $PSScriptRoot "logs"
$LogFile    = Join-Path $LogDir "watchdog.log"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-WLog([string]$msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [watchdog] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Send-NtfyAlert([string]$title, [string]$message, [int]$priority = 4) {
    $ntfyFile = Join-Path $ProjectDir "ntfy_watchdog_tmp.json"
    $payload = @{
        topic    = "wangsc2025"
        title    = $title
        message  = $message
        priority = $priority
        tags     = @("warning", "robot")
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($ntfyFile, $payload, [System.Text.UTF8Encoding]::new($false))
    try {
        curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyFile" https://ntfy.sh 2>/dev/null
    } catch {}
    Remove-Item $ntfyFile -Force -ErrorAction SilentlyContinue
}

# ---- 1. 進程存活檢查（以 heartbeat PID 為準）----
$HeartbeatFile = Join-Path $ProjectDir "state\scheduler-heartbeat.json"
$schedAlive = $false
if (Test-Path $HeartbeatFile) {
    try {
        $hb = Get-Content $HeartbeatFile -Raw | ConvertFrom-Json
        $hbPid = [int]$hb.pid
        $hbProc = Get-Process -Id $hbPid -ErrorAction SilentlyContinue
        if ($hbProc) {
            $elapsed = (Get-Date) - $hbProc.StartTime
            $elapsedStr = "{0:hh\:mm\:ss}" -f $elapsed
            Write-WLog "chatroom-scheduler 正常運行 (PID $hbPid, 已運行 $elapsedStr)"
            $schedAlive = $true
        }
    } catch {}
}
if ($schedAlive) { exit 0 }

# ---- 2. 進程已死：計算心跳過期時間 ----
$staleMinutes = 999
if (Test-Path $HeartbeatFile) {
    try {
        $hb2 = Get-Content $HeartbeatFile -Raw | ConvertFrom-Json
        $lastTs = [datetime]$hb2.timestamp
        $staleMinutes = [int]((Get-Date) - $lastTs).TotalMinutes
    } catch {}
}
Write-WLog "[WARN] chatroom-scheduler 未運行！最後心跳：${staleMinutes} 分鐘前"

# ---- 3. 先確認 bot server 健康，再決定是否重啟 scheduler ----
$botOk = $false
try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/health" -TimeoutSec 5 -ErrorAction Stop
    $botOk = ($r.status -eq "ok" -or $r.status -eq "running")
} catch {}

if (-not $botOk) {
    Write-WLog "[WARN] bot server 未健康，跳過 scheduler 重啟（等 restart-bot.ps1 處理）"
    exit 0
}

# ---- 4. 重啟 chatroom-scheduler ----
$schedulerScript = Join-Path $ProjectDir "chatroom-scheduler.py"
if (-not (Test-Path $schedulerScript)) {
    Write-WLog "[ERROR] chatroom-scheduler.py 不存在，無法重啟"
    exit 1
}

Start-Process -FilePath "pwsh.exe" `
    -ArgumentList "-NoProfile","-WindowStyle","Hidden","-Command",
        "uv run --project '$ProjectDir' python '$schedulerScript'" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden

Write-WLog "已送出重啟指令，等待 8 秒確認..."
Start-Sleep -Seconds 8

# 以 heartbeat PID 驗證（比 CimInstance 更可靠）
$checkAlive = $false
if (Test-Path $HeartbeatFile) {
    try {
        $checkHb = Get-Content $HeartbeatFile -Raw | ConvertFrom-Json
        $checkPid = [int]$checkHb.pid
        $checkProc = Get-Process -Id $checkPid -ErrorAction SilentlyContinue
        if ($checkProc) { $checkAlive = $true }
    } catch {}
}

if ($checkAlive) {
    Write-WLog "chatroom-scheduler 重啟成功 (PID $checkPid)"
    Send-NtfyAlert `
        "ℹ️ Chatroom-Scheduler 已自動重啟" `
        "Watchdog 偵測到 scheduler 停止（最後心跳 ${staleMinutes} 分前），已自動恢復。`n時間: $(Get-Date -Format 'MM-dd HH:mm')" `
        3
} else {
    Write-WLog "[ERROR] 重啟後仍未偵測到進程（heartbeat PID 無效）！"
    Send-NtfyAlert `
        "🔴 Chatroom-Scheduler Watchdog 重啟失敗" `
        "自動重啟嘗試失敗，請手動執行 bot\restart-bot.ps1`n時間: $(Get-Date -Format 'MM-dd HH:mm')" `
        5
    exit 1
}
