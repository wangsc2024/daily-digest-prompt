# ============================================
# Claude Agent Health Check (PowerShell 7)
# ============================================
# Usage:
#   pwsh -ExecutionPolicy Bypass -File check-health.ps1
# ============================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = $PSScriptRoot
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
                # Extract file path from summary (format: "path (XXX chars)" or just "path")
                $summary = $entry.summary
                $pathMatch = $summary -match '^(.*?)(?:\s+\(|$)'
                if ($pathMatch) {
                    $path = $matches[1]
                    $skillModifications += [PSCustomObject]@{
                        Date = $entry.ts.Substring(0, 16)  # YYYY-MM-DDTHH:MM
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

# --- Configuration Validation ---
Write-Host ""
Write-Host "[配置驗證]" -ForegroundColor Yellow

try {
    $validatePath = "$AgentDir\hooks\validate_config.py"
    if (Test-Path $validatePath) {
        # 執行配置驗證
        $jsonOutput = python $validatePath --json 2>&1 | Out-String
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

# --- Skill 品質評分 ---
Write-Host ""
Write-Host "[Skill 品質評分]" -ForegroundColor Yellow

try {
    # 呼叫 validate_config.py --check-skills --json
    $validatePath = "$AgentDir\hooks\validate_config.py"
    if (Test-Path $validatePath) {
        $jsonOutput = python $validatePath --check-skills --json 2>&1 | Out-String
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

# --- Loop State 清理 ---
Write-Host ""
Write-Host "[Loop State 清理]" -ForegroundColor Yellow
$loopStateDir = "$AgentDir\state"
$loopFiles = Get-ChildItem -Path $loopStateDir -Filter "loop-state-*.json" -ErrorAction SilentlyContinue
if ($loopFiles.Count -gt 0) {
    $cutoff = (Get-Date).AddHours(-6)
    $oldFiles = $loopFiles | Where-Object { $_.LastWriteTime -lt $cutoff }
    if ($oldFiles.Count -gt 0) {
        $oldFiles | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "  清理 $($oldFiles.Count) 個過期 loop-state 檔案（>6 小時）" -ForegroundColor Green
    }
    $remaining = ($loopFiles.Count - $oldFiles.Count)
    Write-Host "  目前 loop-state 檔案：$remaining 個" -ForegroundColor White
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
Write-Host "========================================" -ForegroundColor Cyan
