# ============================================================
# Bot Server + Gun Relay + Chatroom Scheduler 重啟腳本
# 順序：停 bot → 停 relay → 停 scheduler →
#       啟 relay → 等待 → 啟 bot → 驗證 → 啟 scheduler
# ============================================================
$BotDir     = $PSScriptRoot                        # d:\Source\daily-digest-prompt\bot
$ProjectDir = Split-Path $BotDir -Parent           # d:\Source\daily-digest-prompt
$RelayDir   = "D:\Source\my-gun-relay"
$NodeExe    = "D:\nodejs\node.exe"
$UvExe      = "uv"
$BotPort    = 3001
$RelayPort  = 8765

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

# ---- Step 2: 停止 Gun relay ----
Stop-ByPort -port $RelayPort -name "Gun relay"

# ---- Step 2.5: 停止 chatroom-scheduler ----
$schedProcs = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "chatroom-scheduler" }
if ($schedProcs) {
    foreach ($p in $schedProcs) {
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            Write-RLog "已停止 chatroom-scheduler (PID $($p.Id))"
        } catch {
            Write-RLog "停止 chatroom-scheduler PID $($p.Id) 失敗: $_"
        }
    }
} else {
    Write-RLog "chatroom-scheduler 未在執行，略過"
}

# ---- Step 3: 啟動 Gun relay ----
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Start-Process -FilePath $NodeExe `
    -ArgumentList "index.js" `
    -WorkingDirectory $RelayDir `
    -RedirectStandardOutput (Join-Path $LogDir "relay_${ts}_out.log") `
    -RedirectStandardError  (Join-Path $LogDir "relay_${ts}_err.log") `
    -WindowStyle Hidden
Write-RLog "Gun relay 已啟動 (port $RelayPort)"

# ---- Step 4: 等待 relay 就緒 ----
Start-Sleep -Seconds 3

# ---- Step 5: 啟動 bot server ----
$ts2 = Get-Date -Format "yyyyMMdd_HHmmss"
Start-Process -FilePath $NodeExe `
    -ArgumentList "bot.js" `
    -WorkingDirectory $BotDir `
    -RedirectStandardOutput (Join-Path $LogDir "bot_${ts2}_out.log") `
    -RedirectStandardError  (Join-Path $LogDir "bot_${ts2}_err.log") `
    -WindowStyle Hidden
Write-RLog "bot server 已啟動 (port $BotPort)"

# ---- Step 6: 等待 bot 初始化後驗證 ----
Start-Sleep -Seconds 5

$health = Test-BotHealth
if ($null -eq $health) {
    Write-RLog "[ERROR] bot server 健康檢查失敗，請手動確認"
    exit 1
}

$gunStatus = if ($health.gunConnected) { "已連線" } else { "未連線（Gun WebSocket 握手中，稍後自動重試）" }
Write-RLog "bot server 狀態: $($health.status) | Gun: $gunStatus | 任務佇列: pending=$($health.pendingTasks)"

# ---- Step 7: 啟動 chatroom-scheduler ----
# 不使用 -RedirectStandardOutput/-RedirectStandardError（會導致 Python 長駐進程提前結束）。
# 日誌由 chatroom-scheduler.py 自行寫入 bot/logs/chatroom-scheduler.log。
$schedulerScript = Join-Path $ProjectDir "chatroom-scheduler.py"
$venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if ((Test-Path $schedulerScript) -and (Test-Path $venvPython)) {
    Start-Process -FilePath $venvPython `
        -ArgumentList $schedulerScript `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden
    Write-RLog "chatroom-scheduler 已啟動（venv python，日誌→ bot/logs/chatroom-scheduler.log）"
} elseif (Test-Path $schedulerScript) {
    Start-Process -FilePath "pwsh.exe" `
        -ArgumentList "-NoProfile","-WindowStyle","Hidden","-Command","Set-Location '$ProjectDir'; uv run python chatroom-scheduler.py" `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden
    Write-RLog "chatroom-scheduler 已啟動（uv fallback）"
} else {
    Write-RLog "[WARN] chatroom-scheduler.py 不存在，略過"
}

Write-RLog "====== Bot 重啟完成 ======"
