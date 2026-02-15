# ============================================
# Claude Agent Health Check (PowerShell 7)
# ============================================
# Usage:
#   pwsh -ExecutionPolicy Bypass -File check-health.ps1
# ============================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = "D:\Source\daily-digest-prompt"
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

        # Last failure
        $lastFailed = $recentRuns | Where-Object { $_.status -eq "failed" } | Select-Object -Last 1
        if ($lastFailed) {
            Write-Host "  最近失敗: $($lastFailed.timestamp) - $($lastFailed.error)" -ForegroundColor Red
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

# --- Cache State ---
Write-Host ""
Write-Host "[快取狀態]" -ForegroundColor Yellow

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
            $age = [math]::Round(((Get-Date) - $f.LastWriteTime).TotalMinutes, 0)
            $sizeKB = [math]::Round($f.Length / 1024, 1)
            $freshness = if ($age -le 30) { "新鮮" } elseif ($age -le 360) { "有效" } else { "過期" }
            $color = if ($freshness -eq "新鮮") { "Green" } elseif ($freshness -eq "有效") { "Yellow" } else { "Red" }
            Write-Host "  $($f.Name): ${sizeKB}KB, ${age} 分鐘前更新 " -NoNewline -ForegroundColor White
            Write-Host "($freshness)" -ForegroundColor $color
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
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
