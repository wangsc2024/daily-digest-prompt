# ============================================================
# Bot + Groq-Relay 開機啟動腳本
# 由 Windows 工作排程器（Claude_bot-startup）呼叫
# 順序：① 背景啟動 groq-relay → ② 前景執行 bot.js（任務保持執行）
# ============================================================
$BotDir  = $PSScriptRoot
$NodeExe = "D:\nodejs\node.exe"
$LogDir  = Join-Path $BotDir "logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"

# ── ① 背景啟動 groq-relay（Start-Process，不阻塞）──────────
$groqLog = Join-Path $LogDir "groq-relay.log"
Start-Process -FilePath $NodeExe `
    -ArgumentList "groq-relay.js" `
    -WorkingDirectory $BotDir `
    -RedirectStandardOutput $groqLog `
    -RedirectStandardError  $groqLog `
    -WindowStyle Hidden

# 等待 3002 埠就緒（最多 15 秒）
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    if (Get-NetTCPConnection -LocalPort 3002 -ErrorAction SilentlyContinue) {
        $ready = $true; break
    }
    Start-Sleep -Seconds 1
}
$status = if ($ready) { "OK (port 3002 ready)" } else { "WARN (port 3002 not ready after 15s)" }
Add-Content -Path (Join-Path $LogDir "startup_$Stamp.log") `
    -Value "[$Stamp] groq-relay: $status" -Encoding UTF8

# ── ② 前景執行 bot.js（任務存活期間 = bot.js 執行期間）──────
Set-Location $BotDir
& $NodeExe bot.js
