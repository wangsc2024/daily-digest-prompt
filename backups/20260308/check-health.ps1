# ============================================
# Claude Agent Health Check (PowerShell 7)
# ============================================
# Usage:
#   pwsh -ExecutionPolicy Bypass -File check-health.ps1
#   pwsh -ExecutionPolicy Bypass -File check-health.ps1 -Scheduled
# ============================================

param([switch]$Scheduled)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = $PSScriptRoot

# 排程模式：spawn 子進程捕捉輸出 → 寫 log → 推 ntfy → 早退
if ($Scheduled) {
    $logTimestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $scheduledLogFile = "$AgentDir\logs\health-$logTimestamp.log"
    if (-not (Test-Path "$AgentDir\logs")) { New-Item -ItemType Directory -Path "$AgentDir\logs" -Force | Out-Null }

    # 以無色模式重新執行自身（不帶 -Scheduled），捕捉所有輸出
    $output = & pwsh -ExecutionPolicy Bypass -File $PSCommandPath 2>&1
    $output | Out-File -FilePath $scheduledLogFile -Encoding UTF8

    # 從輸出解析關鍵指標
    $srMatch    = ($output | Select-String '成功率: (\d+\.?\d*)%') | Select-Object -First 1
    $taskMatch  = ($output | Select-String '總計: (\d+)/(\d+) 次') | Select-Object -First 1
    $srText     = if ($srMatch)   { $srMatch.Matches[0].Groups[1].Value + "%" } else { "N/A" }
    $taskText   = if ($taskMatch) { $taskMatch.Matches[0].Groups[1].Value + "/" + $taskMatch.Matches[0].Groups[2].Value } else { "N/A" }

    $issues = @()
    if ($output | Select-String '逾時\s+(\d+) 次' | Where-Object { [int]$_.Matches[0].Groups[1].Value -gt 0 }) { $issues += "逾時" }
    if ($output | Select-String 'Phase 失敗\s+(\d+) 次' | Where-Object { [int]$_.Matches[0].Groups[1].Value -gt 0 }) { $issues += "Phase失敗" }
    if ($output | Select-String '攔截事件: (\d+)' | Where-Object { [int]$_.Matches[0].Groups[1].Value -gt 0 }) { $issues += "攔截" }
    $issueStr  = if ($issues.Count -gt 0) { $issues -join ", " } else { "無" }

    $priority  = if ($issues.Count -gt 0) { 3 } else { 2 }
    $tagsArr   = if ($issues.Count -gt 0) { @("warning","stethoscope") } else { @("white_check_mark","stethoscope") }
    $title     = "健康報告 $(Get-Date -Format 'MM/dd HH:mm')"
    $logName   = Split-Path $scheduledLogFile -Leaf
    $body      = "成功率 ${srText} | 自動任務 ${taskText}`n問題: ${issueStr}`nLog: ${logName}"

    $ntfyPayload = [ordered]@{
        topic    = "wangsc2025"
        title    = $title
        message  = $body
        priority = $priority
        tags     = $tagsArr
    } | ConvertTo-Json -Compress
    $ntfyFile = "$AgentDir\logs\ntfy_health_temp.json"
    [System.IO.File]::WriteAllText($ntfyFile, $ntfyPayload, [System.Text.Encoding]::UTF8)
    curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyFile" https://ntfy.sh | Out-Null
    Remove-Item $ntfyFile -Force -ErrorAction SilentlyContinue

    Write-Host "[Scheduled] Log: $logName" -ForegroundColor Green
    Write-Host "[Scheduled] ntfy 已推播：$body" -ForegroundColor Green
    exit 0
}
$StateFile = "$AgentDir\state\scheduler-state.json"
$MemoryFile = "$AgentDir\context\digest-memory.json"
$CacheDir = "$AgentDir\cache"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Claude Agent Health Report" -ForegroundColor Cyan

Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Scheduler State ---
Write-Host "[排程狀態]" -ForegroundColor Yellow

if (-not (Test-Path $StateFile)) {
    Write-Host "  尚無執行記錄" -ForegroundColor Gray
}
else {
    $stateJson = Get-Content -Path $StateFile -Raw -Encoding UTF8
    $state = $stateJson | ConvertFrom-Json
    $runs = $state.runs

    if ($runs.Count -eq 0) {
        Write-Host "  尚無執行記錄" -ForegroundColor Gray
    }
    else {
        # Last 7 days
        $sevenDaysAgo = (Get-Date).AddDays(-7)
        $recentRuns = $runs | Where-Object {
            try {
                [datetime]::Parse($_.timestamp) -gt $sevenDaysAgo
            }
            catch {
                $false  # Skip records with invalid timestamps
            }
        }

        $totalRuns = $recentRuns.Count
        $successRuns = ($recentRuns | Where-Object { $_.status -eq "success" }).Count
        $failedRuns = ($recentRuns | Where-Object { $_.status -eq "failed" }).Count

        if ($totalRuns -gt 0) {
            $successRate = [math]::Round(($successRuns / $totalRuns) * 100, 1)
            $avgDuration = [math]::Round(($recentRuns | Measure-Object -Property duration_seconds -Average).Average, 0)
        }
        else {
            $successRate = 0
            $avgDuration = 0
        }

        Write-Host "  近 7 天執行次數: $totalRuns" -ForegroundColor White
        if ($successRate -ge 90) {
            Write-Host "  成功率: $successRate%" -ForegroundColor Green
        }
        elseif ($successRate -ge 70) {
            Write-Host "  成功率: $successRate%" -ForegroundColor Yellow
        }
        else {
            Write-Host "  成功率: $successRate%" -ForegroundColor Red
        }
        Write-Host "  平均耗時: ${avgDuration} 秒" -ForegroundColor White

        # Termination Mode 分佈（如果有記錄）
        $withTerminationMode = @($recentRuns | Where-Object { $_.termination_mode })
        if ($withTerminationMode.Count -gt 0) {
            $goalCount = @($withTerminationMode | Where-Object { $_.termination_mode -eq "GOAL" }).Count
            $errorCount = @($withTerminationMode | Where-Object { $_.termination_mode -eq "ERROR" }).Count
            $timeoutCount = @($withTerminationMode | Where-Object { $_.termination_mode -eq "TIMEOUT" }).Count
            $maxTurnsCount = @($withTerminationMode | Where-Object { $_.termination_mode -eq "MAX_TURNS" }).Count
            $abortedCount = @($withTerminationMode | Where-Object { $_.termination_mode -eq "ABORTED" }).Count

            $total = $withTerminationMode.Count
            Write-Host ""
            Write-Host "  [終止模式分佈] (近 7 天，共 $total 筆)" -ForegroundColor Cyan
            if ($goalCount -gt 0) {
                $pct = [math]::Round(($goalCount / $total) * 100, 1)
                Write-Host "    GOAL (成功):     $goalCount 次 ($pct%)" -ForegroundColor Green
            }
            if ($errorCount -gt 0) {
                $pct = [math]::Round(($errorCount / $total) * 100, 1)
                Write-Host "    ERROR (錯誤):    $errorCount 次 ($pct%)" -ForegroundColor Red
            }
            if ($timeoutCount -gt 0) {
                $pct = [math]::Round(($timeoutCount / $total) * 100, 1)
                Write-Host "    TIMEOUT (超時):  $timeoutCount 次 ($pct%)" -ForegroundColor Yellow
            }
            if ($maxTurnsCount -gt 0) {
                $pct = [math]::Round(($maxTurnsCount / $total) * 100, 1)
                Write-Host "    MAX_TURNS:       $maxTurnsCount 次 ($pct%)" -ForegroundColor Yellow
            }
            if ($abortedCount -gt 0) {
                $pct = [math]::Round(($abortedCount / $total) * 100, 1)
                Write-Host "    ABORTED (中止):  $abortedCount 次 ($pct%)" -ForegroundColor Magenta
            }
        }

        Write-Host ""

        # Last failure
        $lastFailed = $recentRuns | Where-Object { $_.status -eq "failed" } | Select-Object -Last 1
        if ($lastFailed) {
            $terminationInfo = if ($lastFailed.termination_mode) { " ($($lastFailed.termination_mode))" } else { "" }
            Write-Host "  最近失敗: $($lastFailed.timestamp)$terminationInfo - $($lastFailed.error)" -ForegroundColor Red
        }
        else {
            Write-Host "  最近失敗: 無" -ForegroundColor Green
        }

        # Last run
        $lastRun = $runs | Select-Object -Last 1
        Write-Host "  上次執行: $($lastRun.timestamp) ($($lastRun.status))" -ForegroundColor White

        # All runs table
        Write-Host ""
        Write-Host "  [近期執行記錄]" -ForegroundColor Yellow
        Write-Host "  時間                  | 狀態    | 耗時   | 錯誤" -ForegroundColor Gray
        Write-Host "  ----------------------|---------|--------|------" -ForegroundColor Gray
        $runs | Select-Object -Last 10 | ForEach-Object {
            $statusColor = if ($_.status -eq "success") { "Green" } elseif ($_.status -eq "failed") { "Red" } else { "Yellow" }
            $statusText = $_.status.PadRight(7)
            $durationText = "$($_.duration_seconds)s".PadRight(6)
            $errorText = if ($_.error) { $_.error } else { "-" }
            Write-Host "  $($_.timestamp) | " -NoNewline -ForegroundColor White
            Write-Host "$statusText" -NoNewline -ForegroundColor $statusColor
            Write-Host " | $durationText | $errorText" -ForegroundColor White
        }
    }
}

# --- Memory State ---
Write-Host ""
Write-Host "[記憶狀態]" -ForegroundColor Yellow

if (-not (Test-Path $MemoryFile)) {
    Write-Host "  尚無記憶檔案（首次執行後建立）" -ForegroundColor Gray
}
else {
    $memJson = Get-Content -Path $MemoryFile -Raw -Encoding UTF8
    $mem = $memJson | ConvertFrom-Json

    Write-Host "  連續執行: $($mem.run_count) 次" -ForegroundColor White
    Write-Host "  上次執行: $($mem.last_run)" -ForegroundColor White
    Write-Host "  習慣提示連續: $($mem.habits.streak_days) 天" -ForegroundColor White
    Write-Host "  學習技巧連續: $($mem.learning.streak_days) 天" -ForegroundColor White
    Write-Host "  上次摘要: $($mem.digest_summary)" -ForegroundColor White
}

# --- Cache Effectiveness (Phase 2.4) ---
Write-Host ""
Write-Host "[快取效益分析]" -ForegroundColor Yellow

if (-not (Test-Path $CacheDir)) {
    Write-Host "  快取目錄不存在" -ForegroundColor Gray
}
else {
    $cacheFiles = Get-ChildItem -Path $CacheDir -Filter "*.json" -ErrorAction SilentlyContinue
    if ($cacheFiles.Count -eq 0) {
        Write-Host "  無快取檔案" -ForegroundColor Gray
    }
    else {
        foreach ($f in $cacheFiles) {
            try {
                $cache = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
                $cachedAt = [DateTime]::Parse($cache.cached_at)
                $nowUtc = (Get-Date).ToUniversalTime()
                $ageMinutes = [math]::Round(($nowUtc - $cachedAt).TotalMinutes, 1)
                $ttl = if ($cache.ttl_minutes) { $cache.ttl_minutes } else { 30 }
                $sizeKB = [math]::Round($f.Length / 1024, 1)

                $valid = $ageMinutes -le $ttl
                $status = if ($valid) { "有效" } else { "過期" }
                $color = if ($valid) { "Green" } else { "Red" }

                $sourceName = $f.BaseName
                Write-Host "  $sourceName (${sizeKB}KB): " -NoNewline -ForegroundColor White
                Write-Host "年齡 $ageMinutes 分鐘 / TTL $ttl 分鐘 " -NoNewline -ForegroundColor White
                Write-Host "($status)" -ForegroundColor $color
            }
            catch {
                # JSON 損壞或格式錯誤
                $sizeKB = [math]::Round($f.Length / 1024, 1)
                $age = [math]::Round(((Get-Date) - $f.LastWriteTime).TotalMinutes, 0)
                Write-Host "  $($f.Name) (${sizeKB}KB): ${age} 分鐘前更新 " -NoNewline -ForegroundColor White
                Write-Host "(格式錯誤)" -ForegroundColor Red
            }
        }
    }
}

# --- Log Analysis ---
Write-Host ""
Write-Host "[日誌分析]" -ForegroundColor Yellow

$LogDir = "$AgentDir\logs"
if (-not (Test-Path $LogDir)) {
    Write-Host "  日誌目錄不存在" -ForegroundColor Gray
}
else {
    $logFiles = Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-7) } |
        Sort-Object LastWriteTime -Descending

    if ($logFiles.Count -eq 0) {
        Write-Host "  無近 7 天日誌" -ForegroundColor Gray
    }
    else {
        Write-Host "  近 7 天日誌數量: $($logFiles.Count)" -ForegroundColor White

        # 統計問題類型
        $errorCount = 0
        $warnCount = 0
        $retryCount = 0
        $timeoutCount = 0
        $recentErrors = @()

        foreach ($logFile in $logFiles | Select-Object -First 10) {
            $content = Get-Content -Path $logFile.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if ($content) {
                # 統計錯誤
                $errors = [regex]::Matches($content, '\[ERROR\]')
                $errorCount += $errors.Count

                # 統計警告
                $warns = [regex]::Matches($content, '\[WARN\]')
                $warnCount += $warns.Count

                # 統計重試
                $retries = [regex]::Matches($content, 'RETRY')
                $retryCount += $retries.Count

                # 統計超時
                $timeouts = [regex]::Matches($content, 'TIMEOUT')
                $timeoutCount += $timeouts.Count

                # 收集最近的錯誤訊息
                if ($recentErrors.Count -lt 3) {
                    $errorLines = $content -split "`n" | Where-Object { $_ -match '\[ERROR\]' } | Select-Object -First 2
                    foreach ($errLine in $errorLines) {
                        if ($recentErrors.Count -lt 3) {
                            $recentErrors += @{
                                file = $logFile.Name
                                message = $errLine.Trim().Substring(0, [Math]::Min(60, $errLine.Trim().Length))
                            }
                        }
                    }
                }
            }
        }

        # 輸出統計
        $totalIssues = $errorCount + $warnCount + $timeoutCount
        if ($totalIssues -eq 0) {
            Write-Host "  問題統計: " -NoNewline -ForegroundColor White
            Write-Host "無問題發現" -ForegroundColor Green
        }
        else {
            Write-Host "  問題統計:" -ForegroundColor White
            if ($errorCount -gt 0) {
                Write-Host "    🔴 ERROR: $errorCount 次" -ForegroundColor Red
            }
            if ($warnCount -gt 0) {
                Write-Host "    🟡 WARN: $warnCount 次" -ForegroundColor Yellow
            }
            if ($retryCount -gt 0) {
                Write-Host "    🔄 RETRY: $retryCount 次" -ForegroundColor Yellow
            }
            if ($timeoutCount -gt 0) {
                Write-Host "    ⏰ TIMEOUT: $timeoutCount 次" -ForegroundColor Red
            }
        }

        # 輸出最近錯誤
        if ($recentErrors.Count -gt 0) {
            Write-Host ""
            Write-Host "  [最近錯誤]" -ForegroundColor Yellow
            foreach ($err in $recentErrors) {
                Write-Host "    $($err.file): $($err.message)..." -ForegroundColor Red
            }
        }
    }
}

# --- Hooks Structured Logs ---
Write-Host ""
Write-Host "[Hooks 結構化日誌]" -ForegroundColor Yellow

$StructuredDir = "$AgentDir\logs\structured"
if (-not (Test-Path $StructuredDir)) {
    Write-Host "  結構化日誌目錄不存在" -ForegroundColor Gray
}
else {
    # 今日 JSONL
    $todayFile = "$StructuredDir\$(Get-Date -Format 'yyyy-MM-dd').jsonl"
    if (Test-Path $todayFile) {
        $entries = @(Get-Content -Path $todayFile -Encoding UTF8 | ForEach-Object {
            try { $_ | ConvertFrom-Json } catch { $null }
        } | Where-Object { $_ })

        $totalCalls = $entries.Count
        $apiCalls = @($entries | Where-Object { $_.tags -contains "api-call" }).Count
        $cacheReads = @($entries | Where-Object { $_.tags -contains "cache-read" }).Count
        $cacheWrites = @($entries | Where-Object { $_.tags -contains "cache-write" }).Count
        $blocked = @($entries | Where-Object { $_.tags -contains "blocked" }).Count
        $errors = @($entries | Where-Object { $_.tags -contains "error" }).Count
        $skillReads = @($entries | Where-Object { $_.tags -contains "skill-read" }).Count

        Write-Host "  今日工具呼叫: $totalCalls 次" -ForegroundColor White
        Write-Host "  API 呼叫: $apiCalls | 快取讀取: $cacheReads | 快取寫入: $cacheWrites" -ForegroundColor White
        Write-Host "  Skill 讀取: $skillReads" -ForegroundColor White

        if ($blocked -gt 0) {
            Write-Host "  攔截事件: $blocked 次" -ForegroundColor Red
            # 顯示攔截詳情
            $blockedEntries = @($entries | Where-Object { $_.tags -contains "blocked" })
            foreach ($b in $blockedEntries | Select-Object -First 3) {
                $summary = if ($b.summary) { $b.summary } else { $b.tool }
                Write-Host "    - $($b.ts): $summary" -ForegroundColor Red
            }
        }
        else {
            Write-Host "  攔截事件: 0 次" -ForegroundColor Green
        }

        if ($errors -gt 0) {
            Write-Host "  錯誤事件: $errors 次" -ForegroundColor Red
        }
        else {
            Write-Host "  錯誤事件: 0 次" -ForegroundColor Green
        }
    }
    else {
        Write-Host "  今日無結構化日誌" -ForegroundColor Gray
    }

    # Session Summary（近 7 天）
    $summaryFile = "$StructuredDir\session-summary.jsonl"
    if (Test-Path $summaryFile) {
        $cutoff = (Get-Date).AddDays(-7).ToString("yyyy-MM-ddTHH:mm:ss")
        $summaries = @(Get-Content -Path $summaryFile -Encoding UTF8 | ForEach-Object {
            try { $_ | ConvertFrom-Json } catch { $null }
        } | Where-Object { $_ -and $_.ts -ge $cutoff })

        if ($summaries.Count -gt 0) {
            Write-Host ""
            Write-Host "  [近 7 天 Session 健康趨勢]" -ForegroundColor Yellow
            $totalSessions = $summaries.Count
            $healthySessions = @($summaries | Where-Object { $_.blocked -eq 0 -and $_.errors -eq 0 }).Count
            $healthRate = [math]::Round(($healthySessions / $totalSessions) * 100, 1)
            Write-Host "  Session 數量: $totalSessions | 健康率: $healthRate%" -ForegroundColor White

            $totalBlocked = ($summaries | Measure-Object -Property blocked -Sum -ErrorAction SilentlyContinue).Sum
            $totalErrors = ($summaries | Measure-Object -Property errors -Sum -ErrorAction SilentlyContinue).Sum
            if ($totalBlocked -gt 0) {
                Write-Host "  累計攔截: $totalBlocked 次" -ForegroundColor Yellow
            }
            if ($totalErrors -gt 0) {
                Write-Host "  累計錯誤: $totalErrors 次" -ForegroundColor Yellow
            }
        }
    }

    # SKILL.md 修改歷史（近 7 天）
    Write-Host ""
    Write-Host "  [SKILL.md 修改記錄]" -ForegroundColor Yellow

    $cutoff7d = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
    $skillModifications = @()

    # 掃描近 7 天的 JSONL 日誌
    for ($i = 0; $i -lt 7; $i++) {
        $date = (Get-Date).AddDays(-$i).ToString("yyyy-MM-dd")
        $logFile = "$StructuredDir\$date.jsonl"
        if (Test-Path $logFile) {
            $dayEntries = @(Get-Content -Path $logFile -Encoding UTF8 | ForEach-Object {
                try { $_ | ConvertFrom-Json } catch { $null }
            } | Where-Object { $_ -and ($_.tags -contains "skill-modified") })

            foreach ($entry in $dayEntries) {
                # Extract file path from summary (format: "path (<N> chars)" or just "path")
                $summary = $entry.summary
                $pathMatch = $summary -match '^(.*?)(?:\s+\(|$)'
                if ($pathMatch) {
                    $path = $matches[1]
                    $skillModifications += [PSCustomObject]@{
                        Date = ([string]$entry.ts).Substring(0, 16)  # YYYY-MM-DDTHH:MM
                        Path = $path
                        Tool = $entry.tool
                    }
                }
            }
        }
    }

    if ($skillModifications.Count -gt 0) {
        Write-Host "  近 7 天共修改 $($skillModifications.Count) 次：" -ForegroundColor White
        $skillModifications | Sort-Object -Property Date -Descending | Select-Object -First 10 | ForEach-Object {
            $shortPath = $_.Path -replace '.*[\\/]skills[\\/]', 'skills/'
            Write-Host "    $($_.Date) | $shortPath" -ForegroundColor Cyan
        }
        if ($skillModifications.Count -gt 10) {
            Write-Host "    ... 以及其他 $($skillModifications.Count - 10) 筆修改" -ForegroundColor Gray
        }
        Write-Host ""
        Write-Host "  建議檢查: git diff skills/*/SKILL.md" -ForegroundColor Magenta
    }
    else {
        Write-Host "  近 7 天無 SKILL.md 修改" -ForegroundColor Green
    }
}

# --- Metrics Trend (metrics-daily.json) ---
Write-Host ""
Write-Host "[指標趨勢（7 天）]" -ForegroundColor Yellow

$MetricsFile = "$AgentDir\context\metrics-daily.json"
if (-not (Test-Path $MetricsFile)) {
    Write-Host "  尚無指標歷史（首次 session 結束後建立）" -ForegroundColor Gray
}
else {
    try {
        $metricsData = Get-Content -Path $MetricsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $records = @($metricsData.records)

        if ($records.Count -eq 0) {
            Write-Host "  指標記錄為空" -ForegroundColor Gray
        }
        else {
            $today = Get-Date -Format "yyyy-MM-dd"
            $todayRec = $records | Where-Object { $_.date -eq $today } | Select-Object -Last 1

            # 計算 7 天均值（排除今日）
            $cutoff7d = (Get-Date).AddDays(-8).ToString("yyyy-MM-dd")
            $pastRecs = @($records | Where-Object { $_.date -ge $cutoff7d -and $_.date -lt $today })

            function Get-Trend {
                param([double]$current, [double]$avg, [bool]$higherIsBetter = $true)
                if ($avg -eq 0) { return "→" }
                $diff = ($current - $avg) / $avg
                if ([Math]::Abs($diff) -lt 0.05) { return "→" }
                $up = $diff -gt 0
                if ($higherIsBetter) {
                    return if ($up) { "▲" } else { "▼" }
                } else {
                    return if ($up) { "▼" } else { "▲" }
                }
            }

            function Get-TrendColor {
                param([string]$arrow, [bool]$higherIsBetter = $true)
                if ($arrow -eq "→") { return "White" }
                if ($higherIsBetter) {
                    return if ($arrow -eq "▲") { "Green" } else { "Red" }
                } else {
                    return if ($arrow -eq "▲") { "Red" } else { "Green" }
                }
            }

            $metrics = @(
                @{ key = "cache_hit_ratio";       label = "快取命中率";     fmt = "{0}%";  higherBetter = $true;  threshold = 40 }
                @{ key = "api_calls";             label = "API 呼叫數";     fmt = "{0}";   higherBetter = $false; threshold = $null }
                @{ key = "blocked_count";         label = "攔截次數";       fmt = "{0}";   higherBetter = $false; threshold = 3 }
                @{ key = "error_count";           label = "錯誤次數";       fmt = "{0}";   higherBetter = $false; threshold = 5 }
                @{ key = "loop_suspected_count";  label = "迴圈疑似";       fmt = "{0}";   higherBetter = $false; threshold = $null }
                @{ key = "session_success_rate";  label = "Session成功率"; fmt = "{0}%";  higherBetter = $true;  threshold = 90 }
            )

            if ($todayRec) {
                Write-Host "  [今日 vs 7 天均值]" -ForegroundColor Cyan
                Write-Host ("  {0,-20} {1,8}  {2,8}  {3}" -f "指標", "今日", "7d均值", "趨勢") -ForegroundColor Gray
                Write-Host ("  " + "-" * 48) -ForegroundColor Gray

                foreach ($m in $metrics) {
                    $val = $todayRec.($m.key)
                    if ($null -eq $val) { continue }

                    $avg7d = if ($pastRecs.Count -gt 0) {
                        $vals = @($pastRecs | ForEach-Object { $_.($m.key) } | Where-Object { $null -ne $_ })
                        if ($vals.Count -gt 0) { [math]::Round(($vals | Measure-Object -Average).Average, 1) } else { 0 }
                    } else { 0 }

                    $arrow = Get-Trend -current ([double]$val) -avg ([double]$avg7d) -higherIsBetter $m.higherBetter
                    $arrowColor = Get-TrendColor -arrow $arrow -higherIsBetter $m.higherBetter

                    # 閾值警告色
                    $valStr = $m.fmt -f $val
                    $avg7dStr = if ($avg7d -gt 0) { $m.fmt -f $avg7d } else { "N/A" }
                    $valColor = "White"
                    if ($null -ne $m.threshold) {
                        if ($m.higherBetter -and [double]$val -lt $m.threshold) { $valColor = "Red" }
                        elseif (-not $m.higherBetter -and [double]$val -ge $m.threshold) { $valColor = "Yellow" }
                    }

                    Write-Host ("  {0,-20} " -f $m.label) -NoNewline -ForegroundColor Gray
                    Write-Host ("{0,8}" -f $valStr) -NoNewline -ForegroundColor $valColor
                    Write-Host ("  {0,8}  " -f $avg7dStr) -NoNewline -ForegroundColor Gray
                    Write-Host $arrow -ForegroundColor $arrowColor
                }

                # 顯示資料天數
                $totalDays = $records.Count
                Write-Host ""
                Write-Host "  歷史記錄: $totalDays 天（最長 14 天）" -ForegroundColor DarkGray
            }
            else {
                Write-Host "  今日尚無指標記錄（session 結束後更新）" -ForegroundColor Gray
                if ($records.Count -gt 0) {
                    $lastRec = $records | Select-Object -Last 1
                    Write-Host "  最近一筆: $($lastRec.date) — 快取命中率 $($lastRec.cache_hit_ratio)%" -ForegroundColor DarkGray
                }
            }
        }
    }
    catch {
        Write-Host "  指標讀取失敗: $_" -ForegroundColor Red
    }
}

# --- SLO / Error Budget ---
Write-Host ""
Write-Host "[SLO / Error Budget]" -ForegroundColor Cyan

$sloFile    = "$AgentDir\config\slo.yaml"
$metricsFile = "$AgentDir\context\metrics-daily.json"

if ((Test-Path $sloFile) -and (Test-Path $metricsFile)) {
    try {
        # 用 Python 計算（重用 on_stop_alert._compute_error_budget 邏輯）
        $sloScript = @"
import json, sys, os
sys.path.insert(0, r'$($AgentDir.Replace("\","\\"))\hooks')
try:
    from on_stop_alert import _compute_error_budget
    results = _compute_error_budget()
    print(json.dumps(results, ensure_ascii=False))
except Exception as e:
    print(json.dumps([]))
"@
        $sloJson = $sloScript | uv run --project $AgentDir python - 2>$null
        if ($sloJson) {
            $sloResults = $sloJson | ConvertFrom-Json
            foreach ($slo in $sloResults) {
                $id      = $slo.id
                $name    = $slo.name
                $actual  = if ($null -ne $slo.actual)       { $slo.actual }       else { "N/A" }
                $target  = if ($null -ne $slo.target)       { $slo.target }       else { "?" }
                $remain  = if ($null -ne $slo.remaining_pct) { "$($slo.remaining_pct)%" } else { "N/A" }
                $status  = $slo.status

                $budgetColor = switch ($status) {
                    "critical" { "Red" }
                    "warning"  { "Yellow" }
                    "no_data"  { "DarkGray" }
                    default    { "Green" }
                }
                $icon = switch ($status) {
                    "critical" { "❌" }
                    "warning"  { "⚠️" }
                    "no_data"  { "—" }
                    default    { "✅" }
                }
                $label = "$icon $id $name"
                $detail = "實際=$actual  目標=$target  預算剩餘=$remain"
                Write-Host "  $label" -ForegroundColor $budgetColor -NoNewline
                Write-Host "  $detail"
            }
        } else {
            Write-Host "  SLO 計算失敗（Python 呼叫回傳空值）" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "  SLO 計算失敗: $_" -ForegroundColor DarkGray
    }
} elseif (-not (Test-Path $sloFile)) {
    Write-Host "  config/slo.yaml 不存在" -ForegroundColor DarkGray
} else {
    Write-Host "  context/metrics-daily.json 尚無資料（首次執行後生成）" -ForegroundColor DarkGray
}

# --- Configuration Validation ---
Write-Host ""
Write-Host "[配置驗證]" -ForegroundColor Yellow

try {
    $validatePath = "$AgentDir\hooks\validate_config.py"
    if (Test-Path $validatePath) {
        # 執行配置驗證
        $jsonOutput = uv run python $validatePath --json 2>&1 | Out-String
        $result = $jsonOutput | ConvertFrom-Json

        $totalConfigs = 13  # 目前有 13 個配置檔
        $errorCount = $result.errors.Count
        $warnCount = $result.warnings.Count
        $isValid = $result.valid

        # 顯示驗證統計
        $jsonSchemaUsed = $result.validation_stats.json_schema_used
        $simpleUsed = $result.validation_stats.simple_validation_used

        Write-Host "  總配置檔: $totalConfigs 個" -ForegroundColor White
        Write-Host "  JSON Schema 驗證: $jsonSchemaUsed 個 | 簡單驗證: $simpleUsed 個" -ForegroundColor White

        if ($isValid) {
            Write-Host "  驗證結果: " -NoNewline -ForegroundColor White
            Write-Host "✓ 全部通過" -ForegroundColor Green
        }
        else {
            Write-Host "  驗證結果: " -NoNewline -ForegroundColor White
            Write-Host "✗ 發現問題" -ForegroundColor Red

            if ($errorCount -gt 0) {
                Write-Host ""
                Write-Host "  錯誤 ($errorCount):" -ForegroundColor Red
                foreach ($err in $result.errors | Select-Object -First 5) {
                    Write-Host "    ❌ $err" -ForegroundColor Red
                }
                if ($errorCount -gt 5) {
                    Write-Host "    ... 以及其他 $($errorCount - 5) 個錯誤" -ForegroundColor Gray
                }
            }

            if ($warnCount -gt 0) {
                Write-Host ""
                Write-Host "  警告 ($warnCount):" -ForegroundColor Yellow
                foreach ($warn in $result.warnings | Select-Object -First 3) {
                    Write-Host "    ⚠️ $warn" -ForegroundColor Yellow
                }
                if ($warnCount -gt 3) {
                    Write-Host "    ... 以及其他 $($warnCount - 3) 個警告" -ForegroundColor Gray
                }
            }
        }

        # 如果簡單驗證數量 > 0，提示可以升級
        if ($simpleUsed -gt 0) {
            Write-Host ""
            Write-Host "  💡 有 $simpleUsed 個配置檔尚未使用 JSON Schema 驗證" -ForegroundColor Magenta
            Write-Host "     建議：檢查是否已建立對應的 .schema.json 檔案" -ForegroundColor Magenta
        }

        # 提示遷移功能
        Write-Host ""
        Write-Host "  遷移工具: python $validatePath --migrate" -ForegroundColor Cyan
    }
    else {
        Write-Host "  validate_config.py 不存在" -ForegroundColor Gray
    }
}
catch {
    Write-Host "  配置驗證失敗: $_" -ForegroundColor Red
}

# --- YAML 交叉驗證 ---
Write-Host ""
Write-Host "[YAML 交叉驗證]" -ForegroundColor Cyan

try {
    $validatePath = "$AgentDir\hooks\validate_config.py"
    if (Test-Path $validatePath) {
        $crossResult = uv run python $validatePath --cross-validate 2>&1
        if ($crossResult -match "ERROR:") {
            Write-Host "  ⚠ 發現問題" -ForegroundColor Yellow
            $crossResult | Where-Object { $_ -match "(WARN|ERROR):" } | ForEach-Object {
                Write-Host ("  " + $_) -ForegroundColor Yellow
            }
        } elseif ($crossResult -match "✓") {
            Write-Host "  ✓ 所有引用均有效" -ForegroundColor Green
        } else {
            Write-Host "  （執行中...）" -ForegroundColor DarkGray
            $crossResult | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        }
    }
    else {
        Write-Host "  validate_config.py 不存在" -ForegroundColor Gray
    }
}
catch {
    Write-Host "  交叉驗證失敗: $_" -ForegroundColor Red
}

# --- Skill 品質評分 ---
Write-Host ""
Write-Host "[Skill 品質評分]" -ForegroundColor Yellow

try {
    # 呼叫 validate_config.py --check-skills --json
    $validatePath = "$AgentDir\hooks\validate_config.py"
    if (Test-Path $validatePath) {
        $jsonOutput = uv run python $validatePath --check-skills --json 2>&1 | Out-String
        $result = $jsonOutput | ConvertFrom-Json

        if ($result.skill_scores) {
            $scores = $result.skill_scores
            $skillNames = $scores.PSObject.Properties.Name
            $total = $skillNames.Count

            # 計算統計
            $allScores = @()
            $lowScoreSkills = @()
            foreach ($name in $skillNames) {
                $score = $scores.$name.score
                $allScores += $score
                if ($score -lt 80) {
                    $lowScoreSkills += $name
                }
            }

            $avgScore = if ($total -gt 0) { ($allScores | Measure-Object -Average).Average } else { 0 }
            $avgScore = [math]::Round($avgScore, 1)

            Write-Host "  總數: $total 個 Skill | 平均分: $avgScore/100" -ForegroundColor White

            if ($lowScoreSkills.Count -gt 0) {
                Write-Host "  低分 Skill (< 80): $($lowScoreSkills.Count) 個" -ForegroundColor Red
                foreach ($name in $lowScoreSkills | Select-Object -First 5) {
                    $skillData = $scores.$name
                    Write-Host "    - $name ($($skillData.score)/100)" -ForegroundColor Yellow
                    foreach ($err in $skillData.errors) {
                        Write-Host "        ❌ $err" -ForegroundColor Red
                    }
                    foreach ($warn in $skillData.warnings) {
                        Write-Host "        ⚠️ $warn" -ForegroundColor Yellow
                    }
                }
            }
            else {
                Write-Host "  ✓ 所有 Skill 品質良好（≥ 80 分）" -ForegroundColor Green
            }

            # 顯示前 3 高分和後 3 低分
            $sortedSkills = $skillNames | Sort-Object { $scores.$_.score } -Descending
            $top3 = $sortedSkills | Select-Object -First 3
            $bottom3 = $sortedSkills | Select-Object -Last 3

            if ($total -ge 3) {
                Write-Host ""
                Write-Host "  Top 3:" -ForegroundColor Cyan
                foreach ($name in $top3) {
                    $score = $scores.$name.score
                    $status = if ($score -eq 100) { "✓" } else { "⚠️" }
                    Write-Host "    $status $name ($score/100)" -ForegroundColor White
                }

                if ($total -ge 6 -and $avgScore -lt 100) {
                    Write-Host ""
                    Write-Host "  Bottom 3:" -ForegroundColor Magenta
                    foreach ($name in $bottom3) {
                        $score = $scores.$name.score
                        $status = if ($score -lt 80) { "❌" } elseif ($score -lt 95) { "⚠️" } else { "○" }
                        Write-Host "    $status $name ($score/100)" -ForegroundColor White
                    }
                }
            }
        }
        else {
            Write-Host "  無法取得評分資料" -ForegroundColor Gray
        }
    }
    else {
        Write-Host "  validate_config.py 不存在" -ForegroundColor Gray
    }
}
catch {
    Write-Host "  評分檢查失敗: $_" -ForegroundColor Red
}

# --- Circuit Breaker 儀表板 ---
Write-Host ""
Write-Host "[Circuit Breaker 狀態]" -ForegroundColor Yellow
$apiHealthFile = "$AgentDir\state\api-health.json"
if (Test-Path $apiHealthFile) {
    try {
        $apiHealth = Get-Content -Path $apiHealthFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $apis = $apiHealth.PSObject.Properties
        if ($apis.Count -gt 0) {
            foreach ($api in $apis) {
                $name = $api.Name
                $st = $api.Value.state
                $failures = $api.Value.failures
                $cooldown = $api.Value.cooldown
                $color = switch ($st) {
                    "closed"    { "Green" }
                    "half_open" { "Yellow" }
                    "open"      { "Red" }
                    default     { "Gray" }
                }
                $statusIcon = switch ($st) {
                    "closed"    { "[OK]" }
                    "half_open" { "[PROBE]" }
                    "open"      { "[DOWN]" }
                    default     { "[?]" }
                }
                $detail = "  $statusIcon $($name.PadRight(20)) state=$st  failures=$failures"
                if ($cooldown) {
                    try {
                        $cdTime = [datetime]::Parse($cooldown)
                        $remaining = ($cdTime - (Get-Date)).TotalMinutes
                        if ($remaining -gt 0) {
                            $detail += "  cooldown=$([math]::Round($remaining,1))min"
                        } else {
                            $detail += "  cooldown=expired"
                        }
                    } catch {
                        $detail += "  cooldown=$cooldown"
                    }
                }
                Write-Host $detail -ForegroundColor $color
            }
        } else {
            Write-Host "  無 API 狀態記錄" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  api-health.json 解析失敗: $_" -ForegroundColor Red
    }
} else {
    Write-Host "  api-health.json 不存在（尚未執行團隊模式）" -ForegroundColor Gray
}

# --- Loop State 清理與摘要 ---
Write-Host ""
Write-Host "[Loop State 狀態]" -ForegroundColor Yellow
$loopStateDir = "$AgentDir\state"
$loopFiles = Get-ChildItem -Path $loopStateDir -Filter "loop-state-*.json" -ErrorAction SilentlyContinue
if ($loopFiles.Count -gt 0) {
    $cutoff = (Get-Date).AddHours(-6)
    $oldFiles = $loopFiles | Where-Object { $_.LastWriteTime -lt $cutoff }
    if ($oldFiles.Count -gt 0) {
        $oldFiles | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "  清理 $($oldFiles.Count) 個過期 loop-state 檔案（>6 小時）" -ForegroundColor Green
    }
    $activeFiles = Get-ChildItem -Path $loopStateDir -Filter "loop-state-*.json" -ErrorAction SilentlyContinue
    Write-Host "  目前 loop-state 檔案：$($activeFiles.Count) 個" -ForegroundColor White

    # 顯示最近 5 筆活躍 session 摘要
    $recent = $activeFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 5
    if ($recent.Count -gt 0) {
        Write-Host ("  {0,-20} {1,6}  {2,5}  {3}" -f "Session ID", "Calls", "Hash窗", "最後更新") -ForegroundColor DarkCyan
        Write-Host "  $('─' * 52)" -ForegroundColor DarkGray
        foreach ($f in $recent) {
            try {
                $d = Get-Content $f.FullName -Raw | ConvertFrom-Json
                $calls   = if ($null -ne $d.session_call_count) { $d.session_call_count } else { "?" }
                $hashWin = if ($d.tool_hash_window) { $d.tool_hash_window.Count } else { 0 }
                $sid     = $f.BaseName -replace "loop-state-", ""
                $updated = $f.LastWriteTime.ToString("MM/dd HH:mm")
                Write-Host ("  {0,-20} {1,6}  {2,5}  {3}" -f $sid, $calls, $hashWin, $updated) -ForegroundColor White
            } catch {
                Write-Host "  $($f.Name)  [讀取失敗]" -ForegroundColor DarkGray
            }
        }
    }
}
else {
    Write-Host "  無 loop-state 檔案" -ForegroundColor Gray
}

# --- 空 stderr log 清理 ---
$stderrFiles = Get-ChildItem -Path "$AgentDir\logs" -Filter "*-stderr-*.log" -ErrorAction SilentlyContinue
if ($stderrFiles.Count -gt 0) {
    $emptyStderr = $stderrFiles | Where-Object { $_.Length -eq 0 -and $_.LastWriteTime -lt $cutoff }
    if ($emptyStderr.Count -gt 0) {
        $emptyStderr | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "  清理 $($emptyStderr.Count) 個空 stderr 日誌" -ForegroundColor Green
    }
}

Write-Host ""

# --- Token 預算估算 ---
$tokenFile = "$AgentDir\state\token-usage.json"
Write-Host "[今日 Token 估算]" -ForegroundColor Cyan

if (Test-Path $tokenFile) {
    try {
        $tokenData = Get-Content $tokenFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $today = (Get-Date).ToString("yyyy-MM-dd")
        $dayData = $tokenData.daily.$today

        if ($dayData) {
            $estimated = [long]$dayData.estimated_tokens
            $toolCalls = [int]$dayData.tool_calls
            $limitM = 1.5
            $pct = [int]($estimated / ($limitM * 1000000) * 100)
            $barFilled = [int](($pct / 100) * 20)
            $barFilled = [Math]::Min($barFilled, 20)
            $bar = ("█" * $barFilled) + ("░" * (20 - $barFilled))

            $estimatedM = "{0:F2}" -f ($estimated / 1000000)
            $color = if ($pct -lt 80) { "Green" } elseif ($pct -lt 100) { "Yellow" } else { "Red" }

            Write-Host ("  今日估算：{0}M tokens / {1}M 上限  ({2}%)" -f $estimatedM, $limitM, $pct) -ForegroundColor $color
            Write-Host ("  進度：[{0}]  工具呼叫：{1} 次" -f $bar, $toolCalls) -ForegroundColor $color

            if ($pct -ge 100) {
                Write-Host "  ⚠ 已超過日預算！建議暫停執行" -ForegroundColor Red
            }
        }
        else {
            Write-Host "  今日尚無記錄" -ForegroundColor DarkGray
        }
    }
    catch {
        Write-Host "  讀取失敗：$_" -ForegroundColor Yellow
    }
}
else {
    Write-Host "  尚無統計資料（需執行一次 Agent 後才會出現）" -ForegroundColor DarkGray
}

# ─── 近 7 天失敗分類統計 ────────────────────────────────
$statsFile = "$AgentDir\state\failure-stats.json"
Write-Host ""
Write-Host "[失敗分類統計（近 7 天）]" -ForegroundColor Cyan

if (Test-Path $statsFile) {
    try {
        $stats = Get-Content $statsFile -Raw -Encoding UTF8 | ConvertFrom-Json

        $categories = @("timeout", "api_error", "circuit_open", "phase_failure", "parse_error")
        $catLabels  = @{
            "timeout"       = "逾時"
            "api_error"     = "API 錯誤"
            "circuit_open"  = "斷路器開啟"
            "phase_failure" = "Phase 失敗"
            "parse_error"   = "解析錯誤"
        }

        # 算近 7 天
        $last7 = @{}
        $cutoff7 = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
        foreach ($day in $stats.daily.PSObject.Properties) {
            if ($day.Name -ge $cutoff7) {
                foreach ($cat in $categories) {
                    if ($null -eq $last7[$cat]) { $last7[$cat] = 0 }
                    $val = $day.Value.$cat
                    if ($val) { $last7[$cat] += $val }
                }
            }
        }

        $total7 = ($last7.Values | Measure-Object -Sum).Sum
        Write-Host ("  近 7 天總失敗：{0} 次" -f $total7) -ForegroundColor $(if ($total7 -eq 0) { "Green" } else { "Yellow" })
        Write-Host ("  " + "-" * 40) -ForegroundColor DarkGray

        foreach ($cat in $categories) {
            $cnt = if ($last7[$cat]) { $last7[$cat] } else { 0 }
            $label = $catLabels[$cat]
            $bar = ([string]"█" * $cnt)
            $color = if ($cnt -eq 0) { "DarkGray" } elseif ($cnt -le 2) { "Yellow" } else { "Red" }
            Write-Host ("  {0,-12} {1,3} 次  {2}" -f $label, $cnt, $bar) -ForegroundColor $color
        }
    } catch {
        Write-Host "  讀取統計失敗：$_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  尚無統計資料（首次執行後才會出現）" -ForegroundColor DarkGray
}

Write-Host ""

# --- 今日自動任務看板 (VZ1) ---
Write-Host "[今日自動任務看板]" -ForegroundColor Yellow
$autoTasksFile = "$AgentDir\context\auto-tasks-today.json"
$freqLimitsFile = "$AgentDir\config\frequency-limits.yaml"

if ((Test-Path $autoTasksFile) -and (Test-Path $freqLimitsFile)) {
    try {
        $autoTasks = Get-Content -Path $autoTasksFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $freqContent = Get-Content -Path $freqLimitsFile -Raw -Encoding UTF8

        # 解析 YAML tasks（簡易 regex 解析各任務定義）
        $taskDefs = @()
        $taskMatches = [regex]::Matches($freqContent, '(?m)^\s{2}(\w+):\s*\n(?:(?!\s{2}\w+:)[\s\S])*?\s{4}name:\s*(.+?)\s*\n(?:(?!\s{2}\w+:)[\s\S])*?\s{4}daily_limit:\s*(\d+)\s*\n(?:(?!\s{2}\w+:)[\s\S])*?\s{4}counter_field:\s*"?(\w+)"?')
        foreach ($m in $taskMatches) {
            $taskDefs += @{ key = $m.Groups[1].Value; name = $m.Groups[2].Value.Trim(); counter = $m.Groups[4].Value; limit = [int]$m.Groups[3].Value }
        }

        # Fallback：若 regex 解析失敗，直接從 auto-tasks-today.json 推斷（只有計數，無限制）
        if ($taskDefs.Count -eq 0) {
            Write-Host "  （YAML 解析失敗，顯示原始計數）" -ForegroundColor Gray
            $autoTasks.PSObject.Properties | Where-Object { $_.Name -like '*_count' } | ForEach-Object {
                Write-Host ("  {0,-28} {1}" -f $_.Name, $_.Value) -ForegroundColor Cyan
            }
        }
        else {
            Write-Host "  $('━' * 54)" -ForegroundColor DarkGray
            Write-Host ("  {0,-14} {1,5}  {2,-10} {3}" -f "任務名稱", "今/限", "進度", "狀態") -ForegroundColor DarkCyan
            Write-Host "  $('─' * 54)" -ForegroundColor DarkGray

            $totalUsed = 0
            $totalLimit = 0
            foreach ($t in $taskDefs) {
                $count = if ($null -ne $autoTasks.PSObject.Properties[$t.counter]) { [int]($autoTasks.PSObject.Properties[$t.counter].Value) } else { 0 }
                $limit = $t.limit
                $totalUsed += $count
                $totalLimit += $limit
                $filled = if ($limit -gt 0) { [math]::Min($count, $limit) } else { 0 }
                $empty  = [math]::Max(0, $limit - $filled)
                $bar = ("█" * $filled) + ("░" * $empty)
                $statusStr = if ($count -eq 0) { "(今日未執行)" } elseif ($count -ge $limit) { "✓完成" } else { "✓" }
                $color = if ($count -eq 0) { "Gray" } elseif ($count -ge $limit) { "Green" } else { "Cyan" }
                $nameShort = if ($t.name.Length -gt 8) { $t.name.Substring(0,8) } else { $t.name }
                Write-Host ("  {0,-10} {1,3}/{2,-2}  {3,-7} {4}" -f $nameShort, $count, $limit, $bar, $statusStr) -ForegroundColor $color
            }

            Write-Host "  $('─' * 54)" -ForegroundColor DarkGray
            $pct = if ($totalLimit -gt 0) { [math]::Round($totalUsed / $totalLimit * 100, 0) } else { 0 }
            $barLen = 15
            $filledLen = if ($totalLimit -gt 0) { [math]::Min([math]::Round($pct / 100 * $barLen), $barLen) } else { 0 }
            $totalBarStr = ("█" * $filledLen) + ("░" * ($barLen - $filledLen))
            Write-Host ("  總計: {0}/{1} 次 ({2}%)  {3}" -f $totalUsed, $totalLimit, $pct, $totalBarStr) -ForegroundColor White
            Write-Host "  $('━' * 54)" -ForegroundColor DarkGray
        }
    }
    catch {
        Write-Host "  （讀取任務資料失敗：$($_.Exception.Message)）" -ForegroundColor Gray
    }
}
else {
    Write-Host "  （auto-tasks-today.json 或 frequency-limits.yaml 不存在）" -ForegroundColor Gray
}

# ─── FSM 執行狀態 ────────────────────────────────
$fsmFile = "$AgentDir\state\run-fsm.json"
Write-Host ""
Write-Host "[FSM 執行狀態（近期）]" -ForegroundColor Cyan

if (Test-Path $fsmFile) {
    try {
        $fsm = Get-Content $fsmFile -Raw | ConvertFrom-Json
        $runs = $fsm.runs.PSObject.Properties | Sort-Object { $_.Value.started } -Descending | Select-Object -First 5

        if ($runs.Count -eq 0) {
            Write-Host "  尚無 FSM 記錄" -ForegroundColor DarkGray
        } else {
            foreach ($run in $runs) {
                $r = $run.Value
                $startStr = if ($r.started) { ([string]$r.started).Substring(0, 16) } else { "unknown" }
                Write-Host ("  [{0}] {1}" -f $startStr, $r.agent_type) -ForegroundColor White

                foreach ($phase in $r.phases.PSObject.Properties | Sort-Object Name) {
                    $p = $phase.Value
                    $stateColor = switch ($p.state) {
                        "completed" { "Green" }
                        "running"   { "Cyan" }
                        "failed"    { "Red" }
                        default     { "DarkGray" }
                    }
                    $stateIcon = switch ($p.state) {
                        "completed" { "v" }
                        "running"   { ">" }
                        "failed"    { "x" }
                        default     { "o" }
                    }
                    $detailStr = if ($p.detail) { " ($($p.detail))" } else { "" }
                    Write-Host ("    {0} {1}: {2}{3}" -f $stateIcon, $phase.Name, $p.state, $detailStr) -ForegroundColor $stateColor
                }
            }
        }
    } catch {
        Write-Host "  讀取 FSM 狀態失敗：$_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  尚無 FSM 記錄（首次執行後才會出現）" -ForegroundColor DarkGray
}

# [OODA 工作流狀態]
Write-Host ""
Write-Host "[OODA 工作流狀態（最近一次）]" -ForegroundColor Cyan
$workflowFile = Join-Path $PSScriptRoot "context\workflow-state.json"
if (Test-Path $workflowFile) {
    try {
        $wf = Get-Content $workflowFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $stepColor = switch ($wf.status) {
            "completed" { "Green" }
            "failed"    { "Red" }
            "running"   { "Yellow" }
            "skipped"   { "DarkGray" }
            default     { "White" }
        }
        Write-Host "  當前步驟: $($wf.current_step) [$($wf.status)]" -ForegroundColor $stepColor
        if ($wf.updated_at) {
            Write-Host "  更新時間: $($wf.updated_at)"
        }
        if ($wf.history -and $wf.history.Count -gt 0) {
            Write-Host "  最近歷史:"
            $recent = $wf.history | Select-Object -Last 3
            foreach ($h in $recent) {
                Write-Host "    $($h.ts) → $($h.step) [$($h.status)]" -ForegroundColor DarkGray
            }
        }
    } catch {
        Write-Host "  無法解析 workflow-state.json" -ForegroundColor Yellow
    }
} else {
    Write-Host "  (workflow-state.json 尚未建立)" -ForegroundColor DarkGray
}

# [自動任務一致性]
Write-Host ""
Write-Host "[自動任務一致性]" -ForegroundColor Cyan
$validatePath = Join-Path $PSScriptRoot "hooks\validate_config.py"
if (Test-Path $validatePath) {
    try {
        $autoTaskOutput = uv run python $validatePath --check-auto-tasks 2>&1 | Out-String
        if ($autoTaskOutput -match "不一致：(\d+)") {
            $inconsistCount = [int]$Matches[1]
            if ($inconsistCount -gt 0) {
                Write-Host "  ⚠️  發現 $inconsistCount 個不一致" -ForegroundColor Yellow
            } else {
                Write-Host "  ✅ 所有自動任務設定一致" -ForegroundColor Green
            }
        } elseif ($autoTaskOutput -match "✅") {
            Write-Host "  ✅ 所有自動任務設定一致" -ForegroundColor Green
        } else {
            # 直接輸出驗證結果
            $autoTaskOutput.Trim() -split "`n" | ForEach-Object {
                Write-Host "  $_" -ForegroundColor Gray
            }
        }
    } catch {
        Write-Host "  無法執行自動任務一致性驗證：$_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  (validate_config.py 不存在)" -ForegroundColor DarkGray
}

# [研究註冊表健康度]
Write-Host ""
Write-Host "[研究註冊表健康度]" -ForegroundColor Cyan
$registryFile = Join-Path $PSScriptRoot "context\research-registry.json"
if (Test-Path $registryFile) {
    try {
        $registry = Get-Content $registryFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $summary = $registry.summary
        if ($summary) {
            $total = $summary.total
            $lastUpdated = $summary.last_updated
            $saturated = if ($summary.saturated_types -and $summary.saturated_types.Count -gt 0) {
                $summary.saturated_types -join ", "
            } else { "無" }
            Write-Host "  總條目：$total 筆 | 最後更新：$lastUpdated" -ForegroundColor White
            Write-Host "  飽和類型：$saturated" -ForegroundColor $(if ($summary.saturated_types -and $summary.saturated_types.Count -gt 0) { "Yellow" } else { "Green" })
            if ($total -gt 100) {
                Write-Host "  ⚠️  條目數超過 100，建議清理舊記錄" -ForegroundColor Yellow
            }
            if ($summary.recent_3d_topics -and $summary.recent_3d_topics.Count -gt 0) {
                Write-Host "  近 3 日主題（$($summary.recent_3d_topics.Count) 筆）：$($summary.recent_3d_topics[0])" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "  (summary 欄位尚未建立，讀取完整 entries...)" -ForegroundColor DarkGray
            $entryCount = if ($registry.entries) { $registry.entries.Count } else { 0 }
            Write-Host "  條目數：$entryCount" -ForegroundColor White
        }
    } catch {
        Write-Host "  無法解析 research-registry.json：$_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  (尚無研究記錄)" -ForegroundColor DarkGray
}

# [快取效率]
Write-Host ""
Write-Host "[快取效率]" -ForegroundColor Cyan
$cacheStatusFile = Join-Path $PSScriptRoot "cache\status.json"
if (Test-Path $cacheStatusFile) {
    try {
        $cacheStatus = Get-Content $cacheStatusFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $generatedAt = $cacheStatus.generated_at
        Write-Host "  快取狀態預計算於：$generatedAt" -ForegroundColor DarkGray
        if ($cacheStatus.apis) {
            foreach ($apiProp in $cacheStatus.apis.PSObject.Properties) {
                $apiName = $apiProp.Name
                $apiInfo = $apiProp.Value
                $valid = $apiInfo.valid
                $reason = $apiInfo.reason
                $ageMins = $apiInfo.age_min
                $ttlMins = $apiInfo.ttl_min
                if ($valid) {
                    Write-Host "  ✅ $apiName`: 命中（${ageMins}分鐘前，TTL ${ttlMins}分鐘）" -ForegroundColor Green
                } elseif ($reason -eq "missing") {
                    Write-Host "  ⬜ $apiName`: 快取不存在" -ForegroundColor DarkGray
                } else {
                    Write-Host "  ⚠️  $apiName`: 已過期（${ageMins}分鐘前，TTL ${ttlMins}分鐘）" -ForegroundColor Yellow
                }
            }
        }
    } catch {
        Write-Host "  無法解析 cache/status.json：$_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  (cache/status.json 尚未生成，下次執行 run-agent-team.ps1 後會建立)" -ForegroundColor DarkGray
}

# [配置膨脹指標]
Write-Host ""
Write-Host "[配置膨脹指標]" -ForegroundColor Cyan
$analyzeScript = Join-Path $PSScriptRoot "analyze-config.ps1"
if (Test-Path $analyzeScript) {
    try {
        & pwsh -NoProfile -ExecutionPolicy Bypass -File $analyzeScript -Brief 2>&1 | ForEach-Object {
            Write-Host "  $_"
        }
    } catch {
        Write-Host "  無法執行 analyze-config.ps1：$_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  (analyze-config.ps1 尚未建立)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
