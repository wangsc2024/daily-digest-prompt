# ================================
# Bot.js 健康檢查腳本
# ================================
# 用途：檢查 bot.js 是否運行，若離線則發送 ntfy 告警
# 執行：pwsh -ExecutionPolicy Bypass -File check-bot-health.ps1

param(
    [switch]$AutoRestart,  # 若離線則嘗試自動重啟
    [switch]$Silent        # 靜默模式（僅返回 exit code）
)

$AgentDir = $PSScriptRoot
$BotPidFile = "$AgentDir\bot\bot.pid"
$BotLogFile = "$AgentDir\bot\bot.log"
$BotScriptPath = "$AgentDir\bot\bot.js"

# ──────────────────────────────────
# 步驟 1：檢查 bot.js process 是否運行
# ──────────────────────────────────

$isRunning = $false
$pid = $null

if (Test-Path $BotPidFile) {
    try {
        $pid = Get-Content $BotPidFile -Raw -ErrorAction SilentlyContinue | Out-String | ForEach-Object { $_.Trim() }
        if ($pid -match '^\d+$') {
            $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($process) {
                $isRunning = $true
                if (-not $Silent) {
                    Write-Host "✅ bot.js is running (PID: $pid)" -ForegroundColor Green
                }
            }
        }
    } catch {
        # PID 檔案損壞或 process 不存在
    }
}

# ──────────────────────────────────
# 步驟 2：若離線且 AutoRestart，嘗試重啟
# ──────────────────────────────────

if (-not $isRunning) {
    if (-not $Silent) {
        Write-Host "❌ bot.js is NOT running" -ForegroundColor Red
    }

    if ($AutoRestart) {
        if (Test-Path $BotScriptPath) {
            Write-Host "🔄 嘗試重啟 bot.js..." -ForegroundColor Yellow
            try {
                # 啟動 bot.js（背景執行）
                $proc = Start-Process -FilePath "node" -ArgumentList "$BotScriptPath" -WorkingDirectory "$AgentDir\bot" -PassThru -WindowStyle Hidden
                Start-Sleep -Seconds 3
                if ($proc -and -not $proc.HasExited) {
                    Write-Host "✅ bot.js 已重啟 (PID: $($proc.Id))" -ForegroundColor Green
                    $isRunning = $true
                    # 寫入新 PID
                    $proc.Id | Out-File $BotPidFile -Encoding UTF8 -Force
                } else {
                    Write-Host "❌ bot.js 重啟失敗" -ForegroundColor Red
                }
            } catch {
                Write-Host "❌ bot.js 重啟異常: $_" -ForegroundColor Red
            }
        } else {
            Write-Host "❌ bot.js 腳本不存在: $BotScriptPath" -ForegroundColor Red
        }
    }

    # ──────────────────────────────────
    # 步驟 3：發送 ntfy 告警（若仍離線）
    # ──────────────────────────────────

    if (-not $isRunning) {
        $alertJson = @{
            topic    = "wangsc2025"
            title    = "🚨 bot.js 離線告警"
            message  = "bot.js process 未運行，chatroom-plan.json 無法生成。請手動檢查並重啟。"
            priority = 4
            tags     = @("warning", "bot", "health-check")
        } | ConvertTo-Json -Compress

        $alertFile = "$AgentDir\temp\bot-health-alert.json"
        [System.IO.File]::WriteAllText($alertFile, $alertJson, [System.Text.Encoding]::UTF8)

        try {
            curl -s -X POST "https://ntfy.sh/wangsc2025" `
                -H "Content-Type: application/json; charset=utf-8" `
                -d "@$alertFile" > /dev/null 2>&1
            if (-not $Silent) {
                Write-Host "📤 ntfy 告警已發送" -ForegroundColor Cyan
            }
        } catch {
            # 靜默失敗
        } finally {
            Remove-Item $alertFile -Force -ErrorAction SilentlyContinue
        }

        exit 1
    }
}

exit 0
