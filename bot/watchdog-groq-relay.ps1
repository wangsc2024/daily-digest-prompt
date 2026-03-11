# ============================================
# Groq-Relay 哨兵進程（Phase E）
# ============================================
# 監控 groq-relay.js 進程，若未啟動則自動重啟並發送 ntfy 通知。
#
# 用法：
#   pwsh -ExecutionPolicy Bypass -File bot/watchdog-groq-relay.ps1
#
# 建議加入 HEARTBEAT.md 排程（每 5 分鐘），例如：
#   pwsh -ExecutionPolicy Bypass -File "D:\Source\daily-digest-prompt\bot\watchdog-groq-relay.ps1"
# ============================================

param(
    [string]$AgentDir = $PSScriptRoot ? (Split-Path $PSScriptRoot -Parent) : "D:\Source\daily-digest-prompt",
    [int]$HealthPort  = 3002,                    # groq-relay.js 監聽 port（預設 3002）
    [string]$RelayScript = "bot\groq-relay.js",  # 相對於 AgentDir 的 relay 腳本路徑
    [int]$StartupWaitSec = 5,                     # 重啟後等待秒數（讓服務完全就緒）
    [switch]$DryRun                               # 僅偵測，不實際重啟
)

$ErrorActionPreference = "SilentlyContinue"

# --- 路徑 ---
$RelayScriptPath = Join-Path $AgentDir $RelayScript
$LogDir          = Join-Path $AgentDir "bot\logs"
$LogFile         = Join-Path $LogDir "watchdog-groq-relay.log"
$LockFile        = Join-Path $AgentDir "state\watchdog-groq-relay.lock"
$HealthEndpoint  = "http://localhost:${HealthPort}/groq/health"

# --- 確保 logs 目錄存在 ---
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# --- 日誌工具 ---
function Write-WLog {
    param([string]$Msg, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts][$Level] $Msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    switch ($Level) {
        "WARN"  { Write-Host $line -ForegroundColor Yellow }
        "ERROR" { Write-Host $line -ForegroundColor Red }
        default { Write-Host $line -ForegroundColor Gray }
    }
}

# --- 防止哨兵重複執行（lock 檔） ---
if (Test-Path $LockFile) {
    $lockPid = [int](Get-Content $LockFile -Raw -ErrorAction SilentlyContinue)
    if ($lockPid -gt 0 -and (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
        # 另一個哨兵實例仍在執行，靜默退出
        exit 0
    }
    # lock 檔過時（舊進程已不存在），移除並繼續
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
$PID | Set-Content $LockFile -Encoding UTF8

try {
    Write-WLog "Groq-Relay 哨兵啟動（PID: $PID）"

    # ====================================================
    # 步驟 1：偵測 groq-relay 進程
    # ====================================================
    $relayProcess = Get-Process -Name "node" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*groq-relay*" -or $_.MainWindowTitle -like "*groq-relay*" }

    # Windows 的 Get-Process 不一定能讀 CommandLine，改用 WMI 查詢
    if (-not $relayProcess) {
        $wmiProcs = Get-WmiObject Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue
        $relayProcess = $wmiProcs | Where-Object { $_.CommandLine -like "*groq-relay*" }
    }

    $isRunning = $null -ne $relayProcess

    # ====================================================
    # 步驟 2：若進程存在，確認 HTTP 健康端點
    # ====================================================
    if ($isRunning) {
        try {
            $healthResp = Invoke-RestMethod -Uri $HealthEndpoint -Method Get -TimeoutSec 3 -ErrorAction Stop
            Write-WLog "Groq-Relay 正常（進程存在，health 回應 OK）"
            exit 0
        } catch {
            Write-WLog "Groq-Relay 進程存在但 /groq/health 無回應，視為異常" "WARN"
            $isRunning = $false   # 強制重啟
        }
    }

    # ====================================================
    # 步驟 3：進程不存在或健康檢查失敗 → 重啟
    # ====================================================
    Write-WLog "Groq-Relay 離線，準備重啟..." "WARN"

    if ($DryRun) {
        Write-WLog "DryRun 模式 — 跳過實際重啟" "WARN"
        exit 1
    }

    if (-not (Test-Path $RelayScriptPath)) {
        Write-WLog "找不到 Relay 腳本：$RelayScriptPath" "ERROR"
        exit 1
    }

    # 啟動 groq-relay（背景執行，不繼承 window）
    $nodeExe = (Get-Command node -ErrorAction SilentlyContinue)?.Source
    if (-not $nodeExe) {
        Write-WLog "找不到 node 執行檔，無法重啟" "ERROR"
        exit 1
    }

    $restartArgs = @{
        FilePath         = $nodeExe
        ArgumentList     = "`"$RelayScriptPath`""
        WorkingDirectory = $AgentDir
        WindowStyle      = "Hidden"
        PassThru         = $true
    }
    $newProc = Start-Process @restartArgs
    Write-WLog "Groq-Relay 已重啟（新 PID: $($newProc.Id)）"

    # 等待服務就緒
    Start-Sleep -Seconds $StartupWaitSec

    # 驗證重啟是否成功
    $restartOk = $false
    try {
        $healthResp = Invoke-RestMethod -Uri $HealthEndpoint -Method Get -TimeoutSec 5 -ErrorAction Stop
        $restartOk = $true
        Write-WLog "Groq-Relay 重啟成功（/groq/health 回應 OK）"
    } catch {
        Write-WLog "Groq-Relay 重啟後健康檢查仍失敗：$($_.Exception.Message)" "ERROR"
    }

    # ====================================================
    # 步驟 4：發送 ntfy 通知
    # ====================================================
    $ntfyTitle   = if ($restartOk) { "✅ Groq-Relay 已重啟" } else { "❌ Groq-Relay 重啟失敗" }
    $ntfyMessage = if ($restartOk) {
        "groq-relay.js 離線後已自動重啟（PID $($newProc.Id)），/groq/health 回應正常"
    } else {
        "groq-relay.js 離線，自動重啟後健康檢查仍失敗，請手動確認"
    }
    $ntfyPriority = if ($restartOk) { 3 } else { 5 }
    $ntfyTags     = if ($restartOk) { @("white_check_mark", "electric_plug") } else { @("fire", "x") }

    $ntfyPayload = @{
        topic    = "wangsc2025"
        title    = $ntfyTitle
        message  = $ntfyMessage
        priority = $ntfyPriority
        tags     = $ntfyTags
    }

    $tempDir = Join-Path $AgentDir "temp"
    if (-not (Test-Path $tempDir)) { New-Item -ItemType Directory -Path $tempDir -Force | Out-Null }
    $ntfyTmpFile = Join-Path $tempDir "watchdog-ntfy-$(Get-Date -Format 'HHmmss').json"

    try {
        $ntfyPayload | ConvertTo-Json -Compress | Set-Content $ntfyTmpFile -Encoding UTF8
        curl -s -X POST https://ntfy.sh `
            -H "Content-Type: application/json; charset=utf-8" `
            -d "@$ntfyTmpFile" 2>/dev/null | Out-Null
        Remove-Item $ntfyTmpFile -Force -ErrorAction SilentlyContinue
        Write-WLog "ntfy 通知已發送（priority=$ntfyPriority）"
    } catch {
        Write-WLog "ntfy 通知失敗：$_" "WARN"
        Remove-Item $ntfyTmpFile -Force -ErrorAction SilentlyContinue
    }

    exit ($restartOk ? 0 : 1)

} finally {
    # 清除 lock 檔
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
