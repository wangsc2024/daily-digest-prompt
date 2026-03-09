# ============================================
# 每日 19:00 模型執行狀態報告
# 掃描當日 todoist-team 日誌，統計各後端執行結果，推送 ntfy 通知
# Usage:
#   pwsh -ExecutionPolicy Bypass -File report-model-status.ps1
#   （由 Windows Task Scheduler 在 19:00 觸發）
# ============================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir  = $PSScriptRoot
$LogDir    = "$AgentDir\logs"
$Today     = Get-Date -Format "yyyyMMdd"
$NowStr    = Get-Date -Format "MM/dd HH:mm"

# ── 後端顯示名稱對照 ──────────────────────────────────────
$BackendLabel = @{
    "codex_exec"         = "Codex gpt-5.4"
    "codex_standard"     = "Codex gpt-5.3"
    "claude_sonnet45"    = "claude-sonnet-4-5"
    "claude_haiku"       = "claude-haiku"
    "openrouter_research"= "OpenRouter研究"
    "openrouter_standard"= "OpenRouter維護"
    "claude_sonnet"      = "Claude預設"
}
$BackendEmoji = @{
    "codex_exec"         = "🔬"
    "codex_standard"     = "🎮"
    "claude_sonnet45"    = "🤖"
    "claude_haiku"       = "⚡"
    "openrouter_research"= "🌐"
    "openrouter_standard"= "🔧"
    "claude_sonnet"      = "💬"
}

# ── 掃描今日所有 todoist-team 日誌 ────────────────────────
$logFiles = Get-ChildItem "$LogDir\todoist-team_${Today}_*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime

if ($logFiles.Count -eq 0) {
    Write-Host "[WARN] 今日無 todoist-team 日誌（$Today）"
}

# 彙整資料結構
$taskBackend   = @{}   # task_key -> backend
$taskStatus    = @{}   # task_key -> "completed" | "failed" | "timeout" | "skipped"
$taskName      = @{}   # task_key -> 中文名稱
$qualityScores = @{}   # task_key -> score
$backendDist   = @{}   # backend -> count
$tokenLevel    = "normal"
$totalRuns     = 0
$successRuns   = 0
$failedRuns    = 0

foreach ($logFile in $logFiles) {
    $lines = Get-Content $logFile.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $lines) { continue }
    $totalRuns++

    $runSuccess = $false
    foreach ($line in $lines) {
        # [ModelSelect] fahua -> codex_exec (token_level=warn)
        if ($line -match '\[ModelSelect\]\s+(\w+)\s+->\s+(\w+)\s+\(token_level=(\w+)\)') {
            $tk = $Matches[1]; $be = $Matches[2]
            $taskBackend[$tk] = $be
            $tokenLevel = $Matches[3]
            if (-not $backendDist.ContainsKey($be)) { $backendDist[$be] = 0 }
        }
        # [ModelSelect] backend 分布: codex_exec=2, claude_sonnet45=1
        if ($line -match '\[ModelSelect\] backend 分布: (.+)') {
            $parts = $Matches[1] -split ',\s*'
            foreach ($p in $parts) {
                if ($p -match '(\w+)=(\d+)') {
                    $be = $Matches[1]; $cnt = [int]$Matches[2]
                    if (-not $backendDist.ContainsKey($be)) { $backendDist[$be] = 0 }
                    $backendDist[$be] += $cnt
                }
            }
        }
        # [Phase2] Started: auto-fahua (法華經研究) backend=codex_exec
        if ($line -match '\[Phase2\] Started: auto-(\w+)\s+\((.+?)\)\s+backend=(\w+)') {
            $tk = $Matches[1]; $nm = $Matches[2]; $be = $Matches[3]
            $taskName[$tk]    = $nm
            $taskBackend[$tk] = $be
            $taskStatus[$tk]  = "running"
        }
        # [Phase2] auto-fahua completed
        if ($line -match '\[Phase2\] auto-(\w+) completed') {
            $tk = $Matches[1]
            $taskStatus[$tk] = "completed"
        }
        # [Phase2] auto-fahua TIMEOUT
        if ($line -match '\[Phase2\] auto-(\w+) TIMEOUT') {
            $tk = $Matches[1]
            $taskStatus[$tk] = "timeout"
        }
        # [Phase2] auto-fahua failed
        if ($line -match '\[Phase2\] auto-(\w+) failed') {
            $tk = $Matches[1]
            $taskStatus[$tk] = "failed"
        }
        # [QualityScore] fahua=30 avg=30
        if ($line -match '\[QualityScore\]\s+(.+)') {
            $parts = $Matches[1] -split '\s+'
            foreach ($p in $parts) {
                if ($p -match '(\w+)=(\d+)') {
                    $tk = $Matches[1]
                    if ($tk -ne "avg") { $qualityScores[$tk] = [int]$Matches[2] }
                }
            }
        }
        # 成功判定
        if ($line -match 'Todoist Agent Team done \(success\)') {
            $runSuccess = $true
            $successRuns++
        }
    }
    if (-not $runSuccess) { $failedRuns++ }
}

# ── 讀取 Token 使用量 ──────────────────────────────────────
$tokenUsed = 0
$tokenPath = "$AgentDir\state\token-usage.json"
if (Test-Path $tokenPath) {
    try {
        $tu = Get-Content $tokenPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $todayKey = Get-Date -Format "yyyy-MM-dd"
        $tokenUsed = [long]($tu.daily.$todayKey.estimated_tokens ?? 0)
    } catch {}
}
$tokenStr = if ($tokenUsed -ge 1000000) {
    "$([math]::Round($tokenUsed/1000000, 1))M"
} elseif ($tokenUsed -ge 1000) {
    "$([math]::Round($tokenUsed/1000, 0))K"
} else { "$tokenUsed" }

# ── 按後端彙整任務清單 ────────────────────────────────────
$backendTasks = @{}  # backend -> list of "task(status emoji)"

foreach ($tk in $taskStatus.Keys) {
    $be     = $taskBackend[$tk] ?? "claude_sonnet"
    $status = $taskStatus[$tk]
    $nm     = if ($taskName.ContainsKey($tk)) { $taskName[$tk] } else { $tk }

    $statusEmoji = switch ($status) {
        "completed" { "✅" }
        "failed"    { "❌" }
        "timeout"   { "⏱️" }
        "skipped"   { "⏭️" }
        default     { "❓" }
    }
    $qScore = if ($qualityScores.ContainsKey($tk)) { " [${qualityScores[$tk]}分]" } else { "" }
    $entry  = "${nm}${qScore}${statusEmoji}"

    if (-not $backendTasks.ContainsKey($be)) { $backendTasks[$be] = @() }
    $backendTasks[$be] += $entry
}

# ── 組裝通知訊息 ──────────────────────────────────────────
$lines = @()

# 執行概況
$srPct = if ($totalRuns -gt 0) { [math]::Round($successRuns / $totalRuns * 100) } else { 0 }
$lines += "📊 執行 ${totalRuns} 次 | 成功 ${successRuns} | 失敗 ${failedRuns} | 成功率 ${srPct}%"

# Token 使用
$tokenEmoji = switch ($tokenLevel) {
    "emergency" { "🔴" } "critical" { "🟠" } "warn" { "🟡" } default { "🟢" }
}
$lines += "${tokenEmoji} Token: ${tokenStr} (${tokenLevel})"

# 各後端任務
if ($backendTasks.Count -gt 0) {
    $lines += "━━━━━━━━━━━━"
    foreach ($be in ($backendTasks.Keys | Sort-Object)) {
        $emoji = $BackendEmoji[$be] ?? "•"
        $label = $BackendLabel[$be]  ?? $be
        $tasks = $backendTasks[$be] -join " | "
        $lines += "${emoji} ${label}："
        $lines += "  ${tasks}"
    }
}

# 品質警示
$lowScores = $qualityScores.GetEnumerator() | Where-Object { $_.Value -lt 60 }
if ($lowScores) {
    $lines += "━━━━━━━━━━━━"
    $lines += "⚠️ 低品質: " + ($lowScores | ForEach-Object { "$($_.Key)=$($_.Value)分" } | Join-String -Separator ", ")
}

$msgBody  = $lines -join "`n"
$priority = if ($failedRuns -gt 0 -or $tokenLevel -in @("critical","emergency")) { 4 } elseif ($tokenLevel -eq "warn") { 3 } else { 2 }
$tags     = if ($failedRuns -gt 0) { @("bar_chart","warning") } else { @("bar_chart","white_check_mark") }

# ── 發送 ntfy 通知 ─────────────────────────────────────────
$ntfyPayload = [ordered]@{
    topic    = "wangsc2025"
    title    = "模型執行報告 $NowStr"
    message  = $msgBody
    priority = $priority
    tags     = $tags
} | ConvertTo-Json -Compress -Depth 3

$ntfyFile = "$LogDir\ntfy_model_report_temp.json"
[System.IO.File]::WriteAllText($ntfyFile, $ntfyPayload, [System.Text.Encoding]::UTF8)
curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyFile" https://ntfy.sh | Out-Null
Remove-Item $ntfyFile -Force -ErrorAction SilentlyContinue

# ── 寫入報告日誌 ───────────────────────────────────────────
$reportFile = "$LogDir\model-report_${Today}_$(Get-Date -Format 'HHmmss').log"
$reportContent = @"
=== 模型執行狀態報告 $NowStr ===
執行次數: $totalRuns  成功: $successRuns  失敗: $failedRuns
Token: $tokenStr ($tokenLevel)

後端分布:
$($backendDist.GetEnumerator() | Sort-Object Key | ForEach-Object { "  $($BackendLabel[$_.Key] ?? $_.Key): $($_.Value) 次" } | Out-String)
任務狀態:
$($taskStatus.GetEnumerator() | Sort-Object Key | ForEach-Object { "  $($_.Key): $($_.Value)" } | Out-String)
品質評分:
$($qualityScores.GetEnumerator() | Sort-Object Key | ForEach-Object { "  $($_.Key): $($_.Value)分" } | Out-String)
"@
$reportContent | Out-File -FilePath $reportFile -Encoding UTF8

Write-Host "[report-model-status] 完成"
Write-Host "  Log: $(Split-Path $reportFile -Leaf)"
Write-Host "  ntfy: $msgBody"
