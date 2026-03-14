# ============================================================
# Bot Server + Chatroom Scheduler 重啟腳本
# 順序：停 bot → 停 scheduler → 啟 bot → 驗證 → 啟 scheduler
# （Gun relay 已移至 Render 雲端，本機不啟動 localhost:8765）
# ============================================================
$BotDir     = $PSScriptRoot                        # d:\Source\daily-digest-prompt\bot
$ProjectDir = Split-Path $BotDir -Parent           # d:\Source\daily-digest-prompt
$NodeExe    = "D:\nodejs\node.exe"
$UvExe      = "uv"
$BotPort    = 3001

$LogDir  = Join-Path $BotDir "logs"
$LogFile = Join-Path $LogDir ("restart_" + (Get-Date -Format "yyyyMMdd") + ".log")
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-RLog([string]$msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Stop-ByPort([int]$port, [string]$name) {
    $lines = netstat -ano | Where-Object { $_ -match ":$port\s+.*LISTENING" }
    $pids = $lines | ForEach-Object {
        if ($_ -match '\s+(\d+)\s*$') { $matches[1] }
    } | Where-Object { $_ } | Sort-Object -Unique
    if ($pids) {
        foreach ($p in $pids) {
            try {
                Stop-Process -Id ([int]$p) -Force -ErrorAction Stop
                Write-RLog "已停止 $name (PID $p, port $port)"
            } catch {
                Write-RLog "停止 $name PID $p 失敗: $_"
            }
        }
        Start-Sleep -Seconds 1
    } else {
        Write-RLog "$name (port $port) 未在執行，略過"
    }
}

function Test-BotHealth {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$BotPort/api/health" -TimeoutSec 5
        return $r
    } catch { return $null }
}

Write-RLog "====== Bot 重啟開始 ======"

# ---- Step 1: 停止 bot server ----
Stop-ByPort -port $BotPort -name "bot server"

# ---- Step 2: 停止 chatroom-scheduler（完整 process tree 清除）----
# 搜尋所有 process（python / uv / pwsh）CommandLine 含 "chatroom-scheduler"
$killedCount = 0
$allProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "chatroom-scheduler" -and $_.ProcessId -ne $PID }
foreach ($p in $allProcs) {
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-RLog "已停止 $($p.Name) (PID $($p.ProcessId)) [chatroom-scheduler]"
        $killedCount++
    } catch {
        Write-RLog "停止 PID $($p.ProcessId) 失敗: $_"
    }
}
if ($killedCount -eq 0) { Write-RLog "chatroom-scheduler 未在執行，略過" }
else { Start-Sleep -Seconds 1 }  # 等進程完全退出

# ---- Step 3: 啟動 bot server ----
$ts2 = Get-Date -Format "yyyyMMdd_HHmmss"
Start-Process -FilePath $NodeExe `
    -ArgumentList "bot.js" `
    -WorkingDirectory $BotDir `
    -RedirectStandardOutput (Join-Path $LogDir "bot_${ts2}_out.log") `
    -RedirectStandardError  (Join-Path $LogDir "bot_${ts2}_err.log") `
    -WindowStyle Hidden
Write-RLog "bot server 已啟動 (port $BotPort)"

# ---- Step 6: 等待 bot 初始化後驗證（指數退避重試 3 次）----
$health = $null
$waitSecs = @(8, 12, 15)   # bot init 需 10~15s：SEA 金鑰 + Gun 握手 + 224 筆快取
for ($i = 0; $i -lt $waitSecs.Count; $i++) {
    Write-RLog "健康檢查等待 $($waitSecs[$i])s（嘗試 $($i+1)/$($waitSecs.Count)）..."
    Start-Sleep -Seconds $waitSecs[$i]
    $health = Test-BotHealth
    if ($null -ne $health) { break }
}

if ($null -eq $health) {
    $errMsg = "[ERROR] bot server 健康檢查失敗（已重試 $($waitSecs.Count) 次），chatroom-scheduler 未啟動"
    Write-RLog $errMsg

    # ntfy 告警
    $ntfyFile = Join-Path $ProjectDir "ntfy_restart_fail.json"
    $ntfyPayload = @{
        topic    = "wangsc2025"
        title    = "🔴 Bot 重啟失敗"
        message  = "chatroom-scheduler 未啟動。$errMsg`n時間: $(Get-Date -Format 'MM-dd HH:mm')`n請手動執行 restart-bot.ps1"
        priority = 5
        tags     = @("rotating_light", "robot")
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($ntfyFile, $ntfyPayload, [System.Text.UTF8Encoding]::new($false))
    try {
        curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyFile" https://ntfy.sh 2>/dev/null
    } catch {}
    Remove-Item $ntfyFile -Force -ErrorAction SilentlyContinue
    exit 1
}

$gunStatus = if ($health.gunConnected) { "已連線" } else { "未連線（Gun 握手中，稍後自動重試）" }
Write-RLog "bot server 狀態: $($health.status) | Gun: $gunStatus | 任務佇列: pending=$($health.pendingTasks)"

# ---- Step 7: 啟動 chatroom-scheduler（統一用 uv）----
# 不使用 -RedirectStandardOutput/-RedirectStandardError（會導致 Python 長駐進程提前結束）。
# 日誌由 chatroom-scheduler.py 自行寫入 bot/logs/chatroom-scheduler.log。
$schedulerScript = Join-Path $ProjectDir "chatroom-scheduler.py"
if (Test-Path $schedulerScript) {
    Start-Process -FilePath "pwsh.exe" `
        -ArgumentList "-NoProfile","-WindowStyle","Hidden","-Command","uv run --project '$ProjectDir' python '$schedulerScript'" `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden
    Write-RLog "chatroom-scheduler 已啟動（uv，日誌→ bot/logs/chatroom-scheduler.log）"
} else {
    Write-RLog "[WARN] chatroom-scheduler.py 不存在，略過"
}

Write-RLog "====== Bot 重啟完成 ======"
