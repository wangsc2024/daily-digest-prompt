# ============================================
# 每日佛偈推播 — 回歸本性・借假修真
# ============================================
# Usage:
#   Manual: pwsh -ExecutionPolicy Bypass -File run-morning-verse.ps1 [-Session morning|evening]
#   Task Scheduler: same command (cron: "30 6 * * *" for morning, "5 17 * * *" for evening)
# ============================================
# 從 data/buddhist-verses.json 選取未使用偈頌，
# 透過 ntfy.sh 推播到 wangsc2025，並記錄送出狀態。
# 支援 -Session 參數：morning（晨間）/ evening（黃昏），同日可各送一次。
# ============================================

param(
    [ValidateSet("morning", "evening")]
    [string]$Session = "morning"
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# UTF-8 without BOM — BOM causes ntfy HTTP 400
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

# ─── Session config ───
$SessionLabel = if ($Session -eq "morning") { "晨間" } else { "黃昏" }
$SessionTime = if ($Session -eq "morning") { "06:30" } else { "17:05" }

# ─── Paths ───
$AgentDir = $PSScriptRoot
$VersesFile = "$AgentDir\data\buddhist-verses.json"
$LogFile = "$AgentDir\state\verse-log.json"
$LogDir = "$AgentDir\logs"
$NtfyTopic = "wangsc2025"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$DateKey = Get-Date -Format "yyyy-MM-dd"

Write-Host "[$Timestamp] Daily Verse ($SessionLabel $SessionTime) - Start"

# ─── Step 1: Load verse database ───
if (-not (Test-Path $VersesFile)) {
    Write-Host "[ERROR] Verses file not found: $VersesFile"
    exit 1
}
$db = Get-Content $VersesFile -Raw -Encoding UTF8 | ConvertFrom-Json
$allVerses = $db.verses
Write-Host "[INFO] Loaded $($allVerses.Count) verses"

# ─── Step 2: Load send log ───
$log = @{ "entries" = @() }
if (Test-Path $LogFile) {
    try {
        $log = Get-Content $LogFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $log.entries) { $log = @{ "entries" = @() } }
    } catch {
        $log = @{ "entries" = @() }
    }
}

# Check if already sent today for THIS SESSION
$todayEntry = $log.entries | Where-Object { $_.date -eq $DateKey -and $_.status -eq "success" -and $_.session -eq $Session }
if ($todayEntry) {
    Write-Host "[SKIP] Already sent today ($DateKey, $Session). Verse ID: $($todayEntry.verse_id)"
    exit 0
}

# ─── Step 3: Pick unused verse (round-robin) ───
$usedIds = @($log.entries | Where-Object { $_.status -eq "success" } | ForEach-Object { $_.verse_id })
$unusedVerses = $allVerses | Where-Object { $_.id -notin $usedIds }

if (-not $unusedVerses -or $unusedVerses.Count -eq 0) {
    # All used → reset cycle
    Write-Host "[INFO] All verses used ($($usedIds.Count)). Resetting cycle."
    $usedIds = @()
    $unusedVerses = $allVerses
    # Mark cycle reset in log
    $log.entries = @($log.entries) + @(@{
        date = $DateKey
        time = $Timestamp
        verse_id = 0
        session = $Session
        status = "cycle_reset"
        note = "All $($allVerses.Count) verses used, starting new cycle"
    })
}

# Pick first unused (sequential order for fairness)
$verse = $unusedVerses | Select-Object -First 1
Write-Host "[INFO] Selected verse #$($verse.id): $($verse.source)"

# ─── Step 4: Send via ntfy ───
$sourceLine = if ($verse.author) { "來源：$($verse.source)（$($verse.author)）" } else { "來源：$($verse.source)" }
$message = "$($verse.verse)`n`n$sourceLine"
# 任務規格：建議 ≤150 字元（含來源），避免推播平台截斷
if ($message.Length -gt 150) {
    $message = $message.Substring(0, 147) + "..."
}
$payloadFile = "$AgentDir\ntfy_verse.json"

# 晨間用「早安佛偈」、黃昏用「回歸本性 借假修真」（任務規格：主旨可簡述「早安佛偈」）
$ntfyTitle = if ($Session -eq "morning") { "早安佛偈" } else { "回歸本性 借假修真" }
$payload = @{
    topic = $NtfyTopic
    title = $ntfyTitle
    message = $message
    tags = @("lotus_position", "pray")
} | ConvertTo-Json -Depth 3

# Write JSON file (UTF-8 without BOM)
[System.IO.File]::WriteAllText($payloadFile, $payload, $utf8NoBom)

$sendStatus = "success"
$sendError = ""
try {
    $result = curl -s -o /dev/null -w "%{http_code}" -H "Content-Type: application/json; charset=utf-8" -d "@$payloadFile" https://ntfy.sh
    if ($result -ne "200") {
        $sendStatus = "failed"
        $sendError = "HTTP $result"
        Write-Host "[ERROR] ntfy returned HTTP $result"
    } else {
        Write-Host "[OK] Notification sent successfully"
    }
} catch {
    $sendStatus = "failed"
    $sendError = $_.Exception.Message
    Write-Host "[ERROR] Failed to send: $sendError"
}

# Cleanup temp file
Remove-Item $payloadFile -Force -ErrorAction SilentlyContinue

# ─── Step 5: Log result ───
$entry = @{
    date = $DateKey
    time = $Timestamp
    verse_id = $verse.id
    verse_text = $verse.verse
    source = $verse.source
    author = $verse.author
    session = $Session
    channel = "ntfy/$NtfyTopic"
    status = $sendStatus
}
if ($sendError) { $entry.error = $sendError }

$log.entries = @($log.entries) + @($entry)

# Keep max 90 entries (3 months)
if ($log.entries.Count -gt 90) {
    $log.entries = $log.entries | Select-Object -Last 90
}

$logJson = $log | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($LogFile, $logJson, $utf8NoBom)
Write-Host "[INFO] Log updated: $LogFile"

# ─── Step 6: Retry on failure ───
if ($sendStatus -eq "failed") {
    Write-Host "[RETRY] Attempting retry in 30 seconds..."
    Start-Sleep -Seconds 30

    $retryTitle = if ($Session -eq "morning") { "早安佛偈（重試）" } else { "回歸本性 借假修真（重試）" }
    $payload2 = @{
        topic = $NtfyTopic
        title = $retryTitle
        message = $message
        tags = @("lotus_position", "pray")
    } | ConvertTo-Json -Depth 3
    [System.IO.File]::WriteAllText($payloadFile, $payload2, $utf8NoBom)

    try {
        $result2 = curl -s -o /dev/null -w "%{http_code}" -H "Content-Type: application/json; charset=utf-8" -d "@$payloadFile" https://ntfy.sh
        if ($result2 -eq "200") {
            Write-Host "[OK] Retry succeeded"
            # Update last entry status
            $log.entries[-1].status = "success"
            $log.entries[-1].note = "Succeeded on retry"
            $retryJson = $log | ConvertTo-Json -Depth 4
            [System.IO.File]::WriteAllText($LogFile, $retryJson, $utf8NoBom)
        } else {
            Write-Host "[ERROR] Retry also failed: HTTP $result2"
            # 任務規格：重試仍失敗時發送 ntfy 告警
            $alertPayload = @{
                topic = $NtfyTopic
                title = "早安佛偈送訊失敗"
                message = "晨間偈頌推播失敗（重試後仍 HTTP $result2），請檢查網路或手動執行 run-morning-verse.ps1"
                tags = @("warning", "x")
                priority = 4
            } | ConvertTo-Json -Depth 3
            $alertFile = "$AgentDir\ntfy_verse_alert.json"
            [System.IO.File]::WriteAllText($alertFile, $alertPayload, $utf8NoBom)
            curl -s -o /dev/null -H "Content-Type: application/json; charset=utf-8" -d "@$alertFile" https://ntfy.sh | Out-Null
            Remove-Item $alertFile -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Host "[ERROR] Retry failed: $($_.Exception.Message)"
        # 重試拋錯時也發送告警
        $alertPayload = @{
            topic = $NtfyTopic
            title = "早安佛偈送訊失敗"
            message = "晨間偈頌推播失敗（重試異常：$($_.Exception.Message)），請手動執行 run-morning-verse.ps1"
            tags = @("warning", "x")
            priority = 4
        } | ConvertTo-Json -Depth 3
        $alertFile = "$AgentDir\ntfy_verse_alert.json"
        [System.IO.File]::WriteAllText($alertFile, $alertPayload, $utf8NoBom)
        curl -s -o /dev/null -H "Content-Type: application/json; charset=utf-8" -d "@$alertFile" https://ntfy.sh | Out-Null
        Remove-Item $alertFile -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $payloadFile -Force -ErrorAction SilentlyContinue
}

$EndTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$EndTime] Daily Verse ($SessionLabel $SessionTime) - Done (Status: $sendStatus)"
