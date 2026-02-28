# ============================================
# Claude Agent Log Query Tool (PowerShell 7)
# ============================================
# Usage:
#   .\query-logs.ps1                              # 近 7 天摘要
#   .\query-logs.ps1 -Days 3 -Agent todoist       # 近 3 天 Todoist
#   .\query-logs.ps1 -Mode detail -Date 2026-02-12
#   .\query-logs.ps1 -Mode errors
#   .\query-logs.ps1 -Mode todoist
#   .\query-logs.ps1 -Mode trend -Days 14
#   .\query-logs.ps1 -Mode summary -Format json
#   .\query-logs.ps1 -Mode health-score
#   .\query-logs.ps1 -Mode health-score -Days 3 -Format json
#   .\query-logs.ps1 -Mode trace -TraceId abc123  # 追蹤特定 trace_id
#   .\query-logs.ps1 -Mode timeline               # Phase 執行時間線（最近 5 筆）
# ============================================

param(
    [ValidateSet("summary", "detail", "errors", "todoist", "trend", "health-score", "trace", "task-board", "timeline")]
    [string]$Mode = "summary",

    [int]$Days = 7,

    [string]$Date,

    [ValidateSet("all", "daily-digest", "daily-digest-team", "todoist")]
    [string]$Agent = "all",

    [ValidateSet("table", "json")]
    [string]$Format = "table",

    [string]$TraceId
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = $PSScriptRoot
$StateFile = "$AgentDir\state\scheduler-state.json"
$HistoryFile = "$AgentDir\state\todoist-history.json"
$LogDir = "$AgentDir\logs"

# ============================================
# Utility Functions
# ============================================

function Get-Runs {
    param([int]$FilterDays, [string]$FilterAgent, [string]$FilterDate)

    if (-not (Test-Path $StateFile)) { return @() }

    $stateJson = Get-Content -Path $StateFile -Raw -Encoding UTF8
    $state = $stateJson | ConvertFrom-Json
    $runs = @($state.runs)

    if ($FilterDate) {
        $runs = $runs | Where-Object {
            try { $_.timestamp -like "$FilterDate*" } catch { $false }
        }
    }
    elseif ($FilterDays -gt 0) {
        $cutoff = (Get-Date).AddDays(-$FilterDays)
        $runs = $runs | Where-Object {
            try { [datetime]::Parse($_.timestamp) -gt $cutoff } catch { $false }
        }
    }

    if ($FilterAgent -and $FilterAgent -ne "all") {
        $runs = $runs | Where-Object { $_.agent -eq $FilterAgent }
    }

    return $runs
}

function Get-History {
    if (-not (Test-Path $HistoryFile)) { return $null }
    $json = Get-Content -Path $HistoryFile -Raw -Encoding UTF8
    return $json | ConvertFrom-Json
}

function Write-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Section {
    param([string]$Title)
    Write-Host "[$Title]" -ForegroundColor Yellow
}

function Format-StatusColor {
    param([string]$Status)
    switch ($Status) {
        "success" { "Green" }
        "failed"  { "Red" }
        default   { "Yellow" }
    }
}

# ============================================
# Mode: summary
# ============================================
function Show-Summary {
    $runs = Get-Runs -FilterDays $Days -FilterAgent $Agent

    if ($Format -eq "json") {
        $total = $runs.Count
        $successCount = @($runs | Where-Object { $_.status -eq "success" }).Count
        $failedCount = @($runs | Where-Object { $_.status -eq "failed" }).Count
        $avgDuration = if ($total -gt 0) { [math]::Round(($runs | Measure-Object -Property duration_seconds -Average).Average, 0) } else { 0 }
        $successRate = if ($total -gt 0) { [math]::Round(($successCount / $total) * 100, 1) } else { 0 }

        # 按 Agent 分組
        $byAgent = @{}
        foreach ($r in $runs) {
            $a = $r.agent
            if (-not $byAgent.ContainsKey($a)) { $byAgent[$a] = @{ total = 0; success = 0; failed = 0; durations = @() } }
            $byAgent[$a].total++
            if ($r.status -eq "success") { $byAgent[$a].success++ } else { $byAgent[$a].failed++ }
            $byAgent[$a].durations += $r.duration_seconds
        }

        $agentStats = @{}
        foreach ($key in $byAgent.Keys) {
            $s = $byAgent[$key]
            $agentStats[$key] = @{
                total = $s.total
                success = $s.success
                failed = $s.failed
                success_rate = if ($s.total -gt 0) { [math]::Round(($s.success / $s.total) * 100, 1) } else { 0 }
                avg_duration = if ($s.durations.Count -gt 0) { [math]::Round(($s.durations | Measure-Object -Average).Average, 0) } else { 0 }
            }
        }

        $result = @{
            period = "近 $Days 天"
            total_runs = $total
            success_rate = $successRate
            avg_duration = $avgDuration
            by_agent = $agentStats
        }

        # Todoist 自動任務
        $history = Get-History
        if ($history -and $history.daily_summary) {
            $cutoff = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
            $recentSummary = @($history.daily_summary | Where-Object { $_.date -ge $cutoff })
            $result["todoist_auto_tasks"] = @{
                shurangama_total = ($recentSummary | Measure-Object -Property shurangama_count -Sum).Sum
                log_audit_total = ($recentSummary | Measure-Object -Property log_audit_count -Sum).Sum
                git_push_total = ($recentSummary | Measure-Object -Property git_push_count -Sum).Sum
            }
        }

        $result | ConvertTo-Json -Depth 5
        return
    }

    # Table format
    $dateLabel = if ($Agent -ne "all") { "近 $Days 天，Agent: $Agent" } else { "近 $Days 天" }
    Write-Header "排程執行成果摘要（$dateLabel）"

    if ($runs.Count -eq 0) {
        Write-Host "  無執行記錄" -ForegroundColor Gray
        return
    }

    $total = $runs.Count
    $successCount = @($runs | Where-Object { $_.status -eq "success" }).Count
    $failedCount = @($runs | Where-Object { $_.status -eq "failed" }).Count
    $avgDuration = [math]::Round(($runs | Measure-Object -Property duration_seconds -Average).Average, 0)
    $successRate = [math]::Round(($successCount / $total) * 100, 1)

    Write-Section "總覽"
    Write-Host "  執行次數: $total" -ForegroundColor White
    $rateColor = if ($successRate -ge 90) { "Green" } elseif ($successRate -ge 70) { "Yellow" } else { "Red" }
    Write-Host "  成功率:   $successRate%" -ForegroundColor $rateColor
    Write-Host "  平均耗時: ${avgDuration} 秒" -ForegroundColor White
    Write-Host ""

    # 按 Agent 分組
    Write-Section "按 Agent 分類"
    Write-Host "  Agent               | 執行 | 成功 | 失敗 | 成功率 | 平均耗時" -ForegroundColor Gray
    Write-Host "  --------------------|------|------|------|--------|--------" -ForegroundColor Gray

    $grouped = $runs | Group-Object -Property agent
    foreach ($g in $grouped) {
        $gTotal = $g.Count
        $gSuccess = @($g.Group | Where-Object { $_.status -eq "success" }).Count
        $gFailed = $gTotal - $gSuccess
        $gRate = [math]::Round(($gSuccess / $gTotal) * 100, 1)
        $gAvg = [math]::Round(($g.Group | Measure-Object -Property duration_seconds -Average).Average, 0)

        $name = $g.Name.PadRight(20)
        $gRateColor = if ($gRate -ge 90) { "Green" } elseif ($gRate -ge 70) { "Yellow" } else { "Red" }
        Write-Host "  $name| $("$gTotal".PadRight(5))| $("$gSuccess".PadRight(5))| $("$gFailed".PadRight(5))| " -NoNewline -ForegroundColor White
        Write-Host "$("$gRate%".PadRight(7))" -NoNewline -ForegroundColor $gRateColor
        Write-Host "| ${gAvg}s" -ForegroundColor White
    }

    # Todoist 自動任務統計
    $history = Get-History
    if ($history -and $history.daily_summary) {
        $cutoff = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
        $recentSummary = @($history.daily_summary | Where-Object { $_.date -ge $cutoff })
        if ($recentSummary.Count -gt 0) {
            Write-Host ""
            Write-Section "Todoist 自動任務統計（近 $Days 天）"
            $sTotal = ($recentSummary | Measure-Object -Property shurangama_count -Sum).Sum
            $lTotal = ($recentSummary | Measure-Object -Property log_audit_count -Sum).Sum
            $gTotal = ($recentSummary | Measure-Object -Property git_push_count -Sum).Sum
            Write-Host "  楞嚴經研究: $sTotal 次" -ForegroundColor White
            Write-Host "  系統 Log 審查: $lTotal 次" -ForegroundColor White
            Write-Host "  Git Push: $gTotal 次" -ForegroundColor White
        }
    }

    Write-Host ""
}

# ============================================
# Mode: detail
# ============================================
function Show-Detail {
    $filterDate = if ($Date) { $Date } else { (Get-Date).ToString("yyyy-MM-dd") }
    $runs = Get-Runs -FilterDays 0 -FilterAgent $Agent -FilterDate $filterDate

    if ($Format -eq "json") {
        @{ date = $filterDate; runs = $runs } | ConvertTo-Json -Depth 5
        return
    }

    Write-Header "執行詳情: $filterDate"

    if ($runs.Count -eq 0) {
        Write-Host "  該日無執行記錄" -ForegroundColor Gray
        return
    }

    Write-Section "時間線"
    $sorted = $runs | Sort-Object -Property timestamp
    foreach ($r in $sorted) {
        $time = try { [datetime]::Parse($r.timestamp).ToString("HH:mm") } catch { "??:??" }
        $agentName = $r.agent.PadRight(22)
        $statusColor = Format-StatusColor $r.status
        $dur = "$($r.duration_seconds)s".PadRight(6)

        $extra = ""
        if ($r.sections) {
            $sectionParts = @()
            $r.sections.PSObject.Properties | ForEach-Object {
                $sColor = switch ($_.Value) { "success" { "ok" }; "cached" { "cache" }; "failed" { "FAIL" }; default { $_.Value } }
                $sectionParts += "$($_.Name)=$sColor"
            }
            $extra = ($sectionParts -join " ")
        }

        Write-Host "  $time " -NoNewline -ForegroundColor White
        Write-Host "$agentName" -NoNewline -ForegroundColor White
        Write-Host "$($r.status.PadRight(8))" -NoNewline -ForegroundColor $statusColor
        Write-Host "$dur" -NoNewline -ForegroundColor White
        if ($extra) { Write-Host " $extra" -ForegroundColor Gray } else { Write-Host "" }
    }

    # 日統計
    $total = $runs.Count
    $successCount = @($runs | Where-Object { $_.status -eq "success" }).Count
    $failedCount = $total - $successCount
    Write-Host ""
    Write-Section "日統計"
    Write-Host "  執行: $total 次 | 成功: $successCount | 失敗: $failedCount" -ForegroundColor White

    # 自動任務
    $history = Get-History
    if ($history -and $history.auto_tasks) {
        $dayTasks = @($history.auto_tasks | Where-Object { $_.date -eq $filterDate })
        if ($dayTasks.Count -gt 0) {
            $sCount = @($dayTasks | Where-Object { $_.type -eq "shurangama" }).Count
            $lCount = @($dayTasks | Where-Object { $_.type -eq "log_audit" }).Count
            $gCount = @($dayTasks | Where-Object { $_.type -eq "git_push" }).Count
            Write-Host "  楞嚴經研究: $sCount 次 | Log 審查: $lCount 次 | Git Push: $gCount 次" -ForegroundColor White

            $shurangamaTasks = @($dayTasks | Where-Object { $_.type -eq "shurangama" -and $_.topic })
            if ($shurangamaTasks.Count -gt 0) {
                $topics = ($shurangamaTasks | ForEach-Object { $_.topic }) -join ", "
                Write-Host "  楞嚴經主題: $topics" -ForegroundColor White
            }
        }
    }

    Write-Host ""
}

# ============================================
# Mode: errors
# ============================================
function Show-Errors {
    if ($Format -eq "json") {
        $runs = Get-Runs -FilterDays $Days -FilterAgent $Agent
        $failedRuns = @($runs | Where-Object { $_.status -eq "failed" })

        # 日誌掃描
        $logStats = Scan-Logs

        $result = @{
            period = "近 $Days 天"
            failed_runs = $failedRuns.Count
            log_stats = $logStats
        }
        $result | ConvertTo-Json -Depth 5
        return
    }

    Write-Header "錯誤與警告彙總（近 $Days 天）"

    # 失敗的 runs
    $runs = Get-Runs -FilterDays $Days -FilterAgent $Agent
    $failedRuns = @($runs | Where-Object { $_.status -eq "failed" })

    Write-Section "失敗執行記錄"
    if ($failedRuns.Count -eq 0) {
        Write-Host "  無失敗記錄" -ForegroundColor Green
    }
    else {
        Write-Host "  失敗次數: $($failedRuns.Count)" -ForegroundColor Red
        Write-Host ""
        Write-Host "  時間                  | Agent              | 耗時   | 錯誤" -ForegroundColor Gray
        Write-Host "  ----------------------|--------------------|--------|------" -ForegroundColor Gray
        foreach ($r in $failedRuns | Select-Object -Last 10) {
            $agentName = $r.agent.PadRight(19)
            $dur = "$($r.duration_seconds)s".PadRight(6)
            $errMsg = if ($r.error) { $r.error } else { "-" }
            Write-Host "  $($r.timestamp) | $agentName| $dur | " -NoNewline -ForegroundColor White
            Write-Host "$errMsg" -ForegroundColor Red
        }
    }

    # 日誌掃描
    Write-Host ""
    $logStats = Scan-Logs

    Write-Section "日誌問題統計"
    $totalIssues = $logStats.errors + $logStats.warns + $logStats.timeouts
    if ($totalIssues -eq 0) {
        Write-Host "  無問題發現" -ForegroundColor Green
    }
    else {
        if ($logStats.errors -gt 0) { Write-Host "  ERROR:   $($logStats.errors) 次" -ForegroundColor Red }
        if ($logStats.warns -gt 0)  { Write-Host "  WARN:    $($logStats.warns) 次" -ForegroundColor Yellow }
        if ($logStats.retries -gt 0) { Write-Host "  RETRY:   $($logStats.retries) 次" -ForegroundColor Yellow }
        if ($logStats.timeouts -gt 0) { Write-Host "  TIMEOUT: $($logStats.timeouts) 次" -ForegroundColor Red }
    }

    if ($logStats.recent_errors.Count -gt 0) {
        Write-Host ""
        Write-Section "最近錯誤"
        foreach ($err in $logStats.recent_errors) {
            Write-Host "  $($err.file): $($err.message)" -ForegroundColor Red
        }
    }

    # 區塊降級統計
    $sectionIssues = @{}
    foreach ($r in $runs) {
        if ($r.sections) {
            $r.sections.PSObject.Properties | ForEach-Object {
                if ($_.Value -ne "success") {
                    $key = "$($_.Name):$($_.Value)"
                    if (-not $sectionIssues.ContainsKey($key)) { $sectionIssues[$key] = 0 }
                    $sectionIssues[$key]++
                }
            }
        }
    }

    if ($sectionIssues.Count -gt 0) {
        Write-Host ""
        Write-Section "區塊降級統計"
        foreach ($key in $sectionIssues.Keys | Sort-Object) {
            $parts = $key -split ":"
            Write-Host "  $($parts[0]): $($parts[1]) x $($sectionIssues[$key])" -ForegroundColor Yellow
        }
    }

    Write-Host ""
}

function Scan-Logs {
    $stats = @{ errors = 0; warns = 0; retries = 0; timeouts = 0; recent_errors = @() }

    if (-not (Test-Path $LogDir)) { return $stats }

    $cutoff = (Get-Date).AddDays(-$Days)
    $logFiles = Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cutoff } |
        Sort-Object LastWriteTime -Descending

    foreach ($logFile in $logFiles | Select-Object -First 20) {
        $content = Get-Content -Path $logFile.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if (-not $content) { continue }

        $stats.errors += [regex]::Matches($content, '\[ERROR\]').Count
        $stats.warns += [regex]::Matches($content, '\[WARN\]').Count
        $stats.retries += [regex]::Matches($content, 'RETRY').Count
        $stats.timeouts += [regex]::Matches($content, 'TIMEOUT').Count

        if ($stats.recent_errors.Count -lt 5) {
            $errorLines = $content -split "`n" | Where-Object { $_ -match '\[ERROR\]' } | Select-Object -First 2
            foreach ($errLine in $errorLines) {
                if ($stats.recent_errors.Count -lt 5) {
                    $msg = $errLine.Trim()
                    if ($msg.Length -gt 80) { $msg = $msg.Substring(0, 80) + "..." }
                    $stats.recent_errors += @{ file = $logFile.Name; message = $msg }
                }
            }
        }
    }

    return $stats
}

# ============================================
# Mode: todoist
# ============================================
function Show-Todoist {
    $history = Get-History

    if ($Format -eq "json") {
        if (-not $history) {
            @{ error = "todoist-history.json not found" } | ConvertTo-Json
            return
        }
        $cutoff = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
        $result = @{
            period = "近 $Days 天"
            auto_tasks = @($history.auto_tasks | Where-Object { $_.date -ge $cutoff })
            daily_summary = @($history.daily_summary | Where-Object { $_.date -ge $cutoff })
        }
        $result | ConvertTo-Json -Depth 5
        return
    }

    Write-Header "Todoist Agent 執行歷史（近 $Days 天）"

    if (-not $history) {
        Write-Host "  尚無歷史記錄（state/todoist-history.json 不存在）" -ForegroundColor Gray
        Write-Host "  歷史記錄將在下次 Todoist Agent 執行自動任務後建立" -ForegroundColor Gray
        Write-Host ""
        return
    }

    $cutoff = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")

    # 執行統計（從 scheduler-state.json）
    $todoistRuns = Get-Runs -FilterDays $Days -FilterAgent "todoist"
    if ($todoistRuns.Count -gt 0) {
        Write-Section "執行統計"
        $total = $todoistRuns.Count
        $successCount = @($todoistRuns | Where-Object { $_.status -eq "success" }).Count
        $rate = [math]::Round(($successCount / $total) * 100, 1)
        Write-Host "  執行次數: $total | 成功: $successCount | 成功率: $rate%" -ForegroundColor White
        Write-Host ""
    }

    # 自動任務歷史
    $recentTasks = @($history.auto_tasks | Where-Object { $_.date -ge $cutoff })
    if ($recentTasks.Count -gt 0) {
        Write-Section "自動任務明細"
        $byType = $recentTasks | Group-Object -Property type
        foreach ($g in $byType) {
            $successCount = @($g.Group | Where-Object { $_.status -eq "success" }).Count
            $typeName = switch ($g.Name) {
                "shurangama" { "楞嚴經研究" }
                "log_audit"  { "系統 Log 審查" }
                "git_push"   { "Git Push" }
                default      { $g.Name }
            }
            Write-Host "  $typeName`: $($g.Count) 次（成功 $successCount）" -ForegroundColor White
        }

        # 楞嚴經主題列表
        $shurangamaTasks = @($recentTasks | Where-Object { $_.type -eq "shurangama" -and $_.topic })
        if ($shurangamaTasks.Count -gt 0) {
            Write-Host ""
            Write-Host "  研究主題:" -ForegroundColor White
            $uniqueTopics = $shurangamaTasks | ForEach-Object { $_.topic } | Select-Object -Unique
            foreach ($topic in $uniqueTopics) {
                $count = @($shurangamaTasks | Where-Object { $_.topic -eq $topic }).Count
                Write-Host "    - $topic ($count 次)" -ForegroundColor White
            }
        }
        Write-Host ""
    }

    # 每日摘要表
    $recentSummary = @($history.daily_summary | Where-Object { $_.date -ge $cutoff } | Sort-Object -Property date -Descending)
    if ($recentSummary.Count -gt 0) {
        Write-Section "每日摘要"
        Write-Host "  日期       | 楞嚴經 | Log審查 | Git Push | 完成任務 | 執行次數" -ForegroundColor Gray
        Write-Host "  -----------|--------|---------|----------|----------|--------" -ForegroundColor Gray
        foreach ($s in $recentSummary) {
            $sC = "$($s.shurangama_count)/3".PadRight(7)
            $lC = "$($s.log_audit_count)/1".PadRight(8)
            $gC = "$($s.git_push_count)/2".PadRight(9)
            $tC = "$($s.todoist_completed)".PadRight(9)
            $eC = "$($s.total_executions)"
            Write-Host "  $($s.date) | $sC| $lC| $gC| $tC| $eC" -ForegroundColor White
        }
        Write-Host ""
    }
}

# ============================================
# Mode: trend
# ============================================
function Show-Trend {
    $runs = Get-Runs -FilterDays $Days -FilterAgent $Agent

    if ($Format -eq "json") {
        $daily = @{}
        foreach ($r in $runs) {
            $d = try { [datetime]::Parse($r.timestamp).ToString("yyyy-MM-dd") } catch { continue }
            if (-not $daily.ContainsKey($d)) { $daily[$d] = @{ total = 0; success = 0; durations = @() } }
            $daily[$d].total++
            if ($r.status -eq "success") { $daily[$d].success++ }
            $daily[$d].durations += $r.duration_seconds
        }

        $trendData = @()
        foreach ($key in $daily.Keys | Sort-Object) {
            $s = $daily[$key]
            $trendData += @{
                date = $key
                total = $s.total
                success = $s.success
                success_rate = if ($s.total -gt 0) { [math]::Round(($s.success / $s.total) * 100, 1) } else { 0 }
                avg_duration = if ($s.durations.Count -gt 0) { [math]::Round(($s.durations | Measure-Object -Average).Average, 0) } else { 0 }
            }
        }

        @{ period = "近 $Days 天"; trend = $trendData } | ConvertTo-Json -Depth 5
        return
    }

    $agentLabel = if ($Agent -ne "all") { "，Agent: $Agent" } else { "" }
    Write-Header "趨勢分析（近 $Days 天$agentLabel）"

    if ($runs.Count -eq 0) {
        Write-Host "  無執行記錄" -ForegroundColor Gray
        return
    }

    # 按日分組
    $daily = @{}
    foreach ($r in $runs) {
        $d = try { [datetime]::Parse($r.timestamp).ToString("yyyy-MM-dd") } catch { continue }
        if (-not $daily.ContainsKey($d)) { $daily[$d] = @{ total = 0; success = 0; durations = @() } }
        $daily[$d].total++
        if ($r.status -eq "success") { $daily[$d].success++ }
        $daily[$d].durations += $r.duration_seconds
    }

    # 成功率趨勢
    Write-Section "成功率趨勢"
    $sortedDays = $daily.Keys | Sort-Object
    foreach ($d in $sortedDays) {
        $s = $daily[$d]
        $rate = if ($s.total -gt 0) { [math]::Round(($s.success / $s.total) * 100, 0) } else { 0 }
        $barLen = [math]::Floor($rate / 5)
        $bar = [string]::new([char]0x2588, $barLen)
        $empty = [string]::new([char]0x2591, (20 - $barLen))
        $dateShort = $d.Substring(5)
        $rateColor = if ($rate -ge 90) { "Green" } elseif ($rate -ge 70) { "Yellow" } else { "Red" }
        Write-Host "  $dateShort " -NoNewline -ForegroundColor White
        Write-Host "$bar$empty" -NoNewline -ForegroundColor $rateColor
        Write-Host " ${rate}% ($($s.total) 次)" -ForegroundColor White
    }

    # 平均耗時趨勢
    Write-Host ""
    Write-Section "平均耗時趨勢"
    $maxDur = 1
    foreach ($d in $sortedDays) {
        $avg = if ($daily[$d].durations.Count -gt 0) { [math]::Round(($daily[$d].durations | Measure-Object -Average).Average, 0) } else { 0 }
        if ($avg -gt $maxDur) { $maxDur = $avg }
    }

    foreach ($d in $sortedDays) {
        $s = $daily[$d]
        $avg = if ($s.durations.Count -gt 0) { [math]::Round(($s.durations | Measure-Object -Average).Average, 0) } else { 0 }
        $barLen = [math]::Floor(($avg / $maxDur) * 20)
        if ($barLen -lt 1 -and $avg -gt 0) { $barLen = 1 }
        $bar = [string]::new([char]0x2588, $barLen)
        $empty = [string]::new([char]0x2591, (20 - $barLen))
        $dateShort = $d.Substring(5)
        Write-Host "  $dateShort " -NoNewline -ForegroundColor White
        Write-Host "$bar$empty" -NoNewline -ForegroundColor Cyan
        Write-Host " ${avg}s" -ForegroundColor White
    }

    # 異常偵測
    $allDurations = $runs | ForEach-Object { $_.duration_seconds }
    $avgAll = if ($allDurations.Count -gt 0) { [math]::Round(($allDurations | Measure-Object -Average).Average, 0) } else { 0 }
    $threshold = $avgAll * 2

    $anomalies = @($runs | Where-Object { $_.duration_seconds -gt $threshold })
    if ($anomalies.Count -gt 0 -and $avgAll -gt 0) {
        Write-Host ""
        Write-Section "異常偵測（耗時超過平均 2 倍: ${threshold}s）"
        foreach ($a in $anomalies | Select-Object -Last 5) {
            $pct = [math]::Round((($a.duration_seconds - $avgAll) / $avgAll) * 100, 0)
            Write-Host "  (!) $($a.timestamp) $($a.agent) 耗時 $($a.duration_seconds)s (+${pct}%)" -ForegroundColor Yellow
        }
    }

    Write-Host ""
}

# ============================================
# Mode: health-score
# ============================================
function Show-HealthScore {
    $runs = Get-Runs -FilterDays $Days -FilterAgent $Agent

    # === 計算各維度分數 ===

    # 1. 成功率 (weight: 30)
    $total = $runs.Count
    if ($total -gt 0) {
        $successCount = @($runs | Where-Object { $_.status -eq "success" }).Count
        $successRate = $successCount / $total
        $successScore = [math]::Min(30, [math]::Round($successRate * 30, 0))
    }
    else {
        $successRate = 0
        $successScore = 0
    }

    # 2. 錯誤率 (weight: 20) — 從 session-summary.jsonl
    $summaryFile = "$AgentDir\logs\structured\session-summary.jsonl"
    $totalErrors = 0
    $totalBlocked = 0
    $sessionCount = 0
    $totalApiCalls = 0
    $totalCacheReads = 0
    if (Test-Path $summaryFile) {
        $cutoff = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-ddTHH:mm:ss")
        $sessions = @(Get-Content -Path $summaryFile -Encoding UTF8 | ForEach-Object {
            try { $_ | ConvertFrom-Json } catch { $null }
        } | Where-Object { $_ -and $_.ts -ge $cutoff })

        $sessionCount = $sessions.Count
        $totalErrors = ($sessions | Measure-Object -Property errors -Sum -ErrorAction SilentlyContinue).Sum
        $totalBlocked = ($sessions | Measure-Object -Property blocked -Sum -ErrorAction SilentlyContinue).Sum
        $totalApiCalls = ($sessions | Measure-Object -Property api_calls -Sum -ErrorAction SilentlyContinue).Sum
        $totalCacheReads = ($sessions | Measure-Object -Property cache_reads -Sum -ErrorAction SilentlyContinue).Sum
    }

    $errorScore = switch ($true) {
        ($totalErrors -eq 0) { 20; break }
        ($totalErrors -le 2) { 15; break }
        ($totalErrors -le 5) { 10; break }
        default              { 0 }
    }

    # 3. 攔截事件 (weight: 15)
    $blockedScore = switch ($true) {
        ($totalBlocked -eq 0) { 15; break }
        ($totalBlocked -le 2) { 10; break }
        default               { 0 }
    }

    # 4. 快取命中率 (weight: 15)
    $totalCacheOps = $totalApiCalls + $totalCacheReads
    $cacheHitRate = if ($totalCacheOps -gt 0) { $totalCacheReads / $totalCacheOps } else { 1.0 }
    $cacheScore = [math]::Min(15, [math]::Round($cacheHitRate * 15, 0))

    # 5. 耗時穩定度 (weight: 10)
    $durations = @($runs | ForEach-Object { $_.duration_seconds } | Where-Object { $_ -gt 0 })
    if ($durations.Count -ge 3) {
        $avg = ($durations | Measure-Object -Average).Average
        $variance = ($durations | ForEach-Object { [math]::Pow($_ - $avg, 2) } | Measure-Object -Average).Average
        $stddev = [math]::Sqrt($variance)
        $cv = if ($avg -gt 0) { $stddev / $avg } else { 0 }
        $durationScore = switch ($true) {
            ($cv -lt 0.3) { 10; break }
            ($cv -lt 0.5) { 7; break }
            default       { 3 }
        }
    }
    else {
        $cv = 0
        $durationScore = 5  # 資料不足給中間分
    }

    # 6. 連續天數 (weight: 10)
    $memFile = "$AgentDir\context\digest-memory.json"
    $streak = 0
    if (Test-Path $memFile) {
        $mem = Get-Content -Path $memFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($mem) { $streak = [int]($mem.run_count) }
    }
    $streakScore = switch ($true) {
        ($streak -ge 14) { 10; break }
        ($streak -ge 7)  { 8; break }
        ($streak -ge 3)  { 5; break }
        default          { 3 }
    }

    # === 總分 ===
    $totalScore = $successScore + $errorScore + $blockedScore + $cacheScore + $durationScore + $streakScore

    # === 分數等級 ===
    $grade = switch ($true) {
        ($totalScore -ge 90) { "優秀"; break }
        ($totalScore -ge 75) { "良好"; break }
        ($totalScore -ge 60) { "尚可"; break }
        ($totalScore -ge 40) { "不佳"; break }
        default              { "嚴重" }
    }
    $gradeColor = switch ($true) {
        ($totalScore -ge 75) { "Green"; break }
        ($totalScore -ge 60) { "Yellow"; break }
        default              { "Red" }
    }

    # === JSON 輸出 ===
    if ($Format -eq "json") {
        @{
            period = "近 $Days 天"
            total_score = $totalScore
            grade = $grade
            dimensions = @{
                success_rate = @{ score = $successScore; max = 30; value = [math]::Round($successRate * 100, 1) }
                error_rate = @{ score = $errorScore; max = 20; count = $totalErrors }
                blocked_events = @{ score = $blockedScore; max = 15; count = $totalBlocked }
                cache_hit_rate = @{ score = $cacheScore; max = 15; value = [math]::Round($cacheHitRate * 100, 1) }
                duration_stability = @{ score = $durationScore; max = 10 }
                streak_continuity = @{ score = $streakScore; max = 10; days = $streak }
            }
        } | ConvertTo-Json -Depth 5
        return
    }

    # === Table 輸出 ===
    Write-Header "系統健康評分（近 $Days 天）"

    # 總分視覺化
    $barLen = [math]::Floor($totalScore / 5)
    $bar = [string]::new([char]0x2588, $barLen)
    $empty = [string]::new([char]0x2591, (20 - $barLen))
    Write-Host "  總分: " -NoNewline -ForegroundColor White
    Write-Host "$bar$empty" -NoNewline -ForegroundColor $gradeColor
    Write-Host " $totalScore/100 ($grade)" -ForegroundColor $gradeColor

    Write-Host ""
    Write-Section "各維度明細"
    Write-Host "  維度             | 得分  | 滿分  | 數值" -ForegroundColor Gray
    Write-Host "  -----------------|-------|-------|------" -ForegroundColor Gray

    $dims = @(
        @{ name = "排程成功率"; score = $successScore; max = 30; val = "$([math]::Round($successRate * 100, 1))%" }
        @{ name = "工具錯誤率"; score = $errorScore; max = 20; val = "$totalErrors 次" }
        @{ name = "違規攔截數"; score = $blockedScore; max = 15; val = "$totalBlocked 次" }
        @{ name = "快取命中率"; score = $cacheScore; max = 15; val = "$([math]::Round($cacheHitRate * 100, 1))%" }
        @{ name = "耗時穩定度"; score = $durationScore; max = 10; val = if ($durations.Count -ge 3) { "CV=$([math]::Round($cv * 100, 0))%" } else { "資料不足" } }
        @{ name = "連續執行數"; score = $streakScore; max = 10; val = "$streak 天" }
    )

    foreach ($d in $dims) {
        $nameStr = $d.name.PadRight(12)
        $scoreStr = "$($d.score)".PadLeft(5)
        $maxStr = "$($d.max)".PadLeft(5)
        $dimColor = if ($d.score -ge $d.max * 0.8) { "Green" } elseif ($d.score -ge $d.max * 0.5) { "Yellow" } else { "Red" }
        Write-Host "  $nameStr   | " -NoNewline -ForegroundColor White
        Write-Host "$scoreStr" -NoNewline -ForegroundColor $dimColor
        Write-Host " | $maxStr | $($d.val)" -ForegroundColor White
    }

    # === 日對日比較 ===
    Write-Host ""
    Write-Section "日對日比較"

    $todayStr = (Get-Date).ToString("yyyy-MM-dd")
    $yesterdayStr = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")

    $todayRuns = @($runs | Where-Object { try { $_.timestamp -like "$todayStr*" } catch { $false } })
    $yesterdayRuns = @($runs | Where-Object { try { $_.timestamp -like "$yesterdayStr*" } catch { $false } })

    $todayTotal = $todayRuns.Count
    $yesterdayTotal = $yesterdayRuns.Count
    $todaySuccess = @($todayRuns | Where-Object { $_.status -eq "success" }).Count
    $yesterdaySuccess = @($yesterdayRuns | Where-Object { $_.status -eq "success" }).Count
    $todayRate = if ($todayTotal -gt 0) { [math]::Round(($todaySuccess / $todayTotal) * 100, 1) } else { 0 }
    $yesterdayRate = if ($yesterdayTotal -gt 0) { [math]::Round(($yesterdaySuccess / $yesterdayTotal) * 100, 1) } else { 0 }

    $todayAvgDur = if ($todayRuns.Count -gt 0) { [math]::Round(($todayRuns | Measure-Object -Property duration_seconds -Average).Average, 0) } else { 0 }
    $yesterdayAvgDur = if ($yesterdayRuns.Count -gt 0) { [math]::Round(($yesterdayRuns | Measure-Object -Property duration_seconds -Average).Average, 0) } else { 0 }

    function Format-Delta {
        param([double]$Today, [double]$Yesterday, [string]$Unit, [bool]$LowerIsBetter = $false)
        $delta = $Today - $Yesterday
        if ($Yesterday -eq 0 -and $Today -eq 0) { return "(持平)" }
        $sign = if ($delta -gt 0) { "+" } else { "" }

        # 判斷趨勢：數值上升對指標是好是壞
        $isImprovement = ($delta -gt 0 -and -not $LowerIsBetter) -or ($delta -lt 0 -and $LowerIsBetter)
        if ($delta -eq 0) {
            $arrow = "(持平)"
        }
        elseif ($isImprovement) {
            $arrow = "(++)"
        }
        else {
            $arrow = "(--)"
        }

        return "${sign}${delta}${Unit} $arrow"
    }

    Write-Host "  執行次數:  $yesterdayTotal -> $todayTotal  $(Format-Delta $todayTotal $yesterdayTotal '')" -ForegroundColor White
    Write-Host "  成功率:    $yesterdayRate% -> $todayRate%  $(Format-Delta $todayRate $yesterdayRate '%')" -ForegroundColor White
    Write-Host "  平均耗時:  ${yesterdayAvgDur}s -> ${todayAvgDur}s  $(Format-Delta $todayAvgDur $yesterdayAvgDur 's' $true)" -ForegroundColor White

    # === 洞察建議 ===
    Write-Host ""
    Write-Section "洞察建議"
    $hasInsight = $false

    if ($successRate -lt 0.9 -and $total -gt 3) {
        Write-Host "  [!] 成功率低於 90%，建議檢查近期失敗原因" -ForegroundColor Yellow
        $hasInsight = $true
    }
    if ($totalBlocked -gt 0) {
        Write-Host "  [!] 偵測到 $totalBlocked 次違規攔截，請檢查 Agent 行為" -ForegroundColor Yellow
        $hasInsight = $true
    }
    if ($totalErrors -ge 5) {
        Write-Host "  [!] 錯誤次數偏高 ($totalErrors 次)，建議檢查 API 穩定性" -ForegroundColor Yellow
        $hasInsight = $true
    }
    if ($cacheHitRate -lt 0.3 -and $totalCacheOps -gt 5) {
        Write-Host "  [!] 快取命中率偏低 ($([math]::Round($cacheHitRate * 100, 1))%)，建議檢查 TTL 設定" -ForegroundColor Yellow
        $hasInsight = $true
    }
    if ($streak -ge 30) {
        Write-Host "  [OK] 連續報到超過 30 天，系統運作穩定" -ForegroundColor Green
        $hasInsight = $true
    }
    if (-not $hasInsight) {
        Write-Host "  [OK] 系統運行正常，無特殊建議" -ForegroundColor Green
    }

    Write-Host ""
}

# ============================================
# Mode: trace
# ============================================
function Show-Trace {
    if (-not $TraceId) {
        Write-Host "錯誤: -TraceId 參數為必填（使用 -Mode trace 時）" -ForegroundColor Red
        return
    }

    Write-Header "分散式追蹤（Trace ID: $TraceId）"

    $structuredLogDir = "$AgentDir\logs\structured"
    if (-not (Test-Path $structuredLogDir)) {
        Write-Host "  結構化日誌目錄不存在: $structuredLogDir" -ForegroundColor Gray
        return
    }

    # 讀取所有 JSONL 檔案（近 7 天）
    $cutoff = (Get-Date).AddDays(-$Days)
    $logFiles = Get-ChildItem -Path $structuredLogDir -Filter "*.jsonl" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cutoff } |
        Sort-Object Name

    if ($logFiles.Count -eq 0) {
        Write-Host "  無結構化日誌檔案" -ForegroundColor Gray
        return
    }

    # 解析 JSONL 並過濾 trace_id
    $entries = @()
    foreach ($logFile in $logFiles) {
        $content = Get-Content -Path $logFile.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        foreach ($line in $content) {
            try {
                $entry = $line | ConvertFrom-Json
                if ($entry.trace_id -eq $TraceId) {
                    $entries += $entry
                }
            } catch {
                # 跳過無效 JSON
                continue
            }
        }
    }

    if ($entries.Count -eq 0) {
        Write-Host "  找不到匹配的 trace_id: $TraceId" -ForegroundColor Yellow
        Write-Host "  建議: 檢查最近一次執行的日誌，確認 trace_id 是否正確" -ForegroundColor Gray
        return
    }

    # JSON 輸出
    if ($Format -eq "json") {
        @{
            trace_id = $TraceId
            entries = $entries | Sort-Object -Property ts
        } | ConvertTo-Json -Depth 5
        return
    }

    # Table 輸出
    Write-Section "執行流程（共 $($entries.Count) 個工具呼叫）"
    $sorted = $entries | Sort-Object -Property ts

    # 分析 Phase
    $phase1Count = @($sorted | Where-Object { $_.tags -contains "phase1" }).Count
    $phase2Count = @($sorted | Where-Object { $_.tags -contains "phase2" }).Count
    $teamMode = @($sorted | Where-Object { $_.tags -contains "team-mode" }).Count -gt 0

    if ($teamMode) {
        Write-Host "  模式: 團隊並行模式" -ForegroundColor Cyan
        Write-Host "  Phase 1 工具呼叫: $phase1Count" -ForegroundColor White
        Write-Host "  Phase 2 工具呼叫: $phase2Count" -ForegroundColor White
        Write-Host ""
    }

    Write-Host "  時間       | Tool  | 摘要                                  | 標籤" -ForegroundColor Gray
    Write-Host "  -----------|-------|---------------------------------------|------" -ForegroundColor Gray

    foreach ($e in $sorted) {
        $time = try { ([datetime]::Parse($e.ts)).ToString("HH:mm:ss") } catch { "??:??:??" }
        $tool = $e.tool.PadRight(6)
        $summary = $e.summary
        if ($summary.Length -gt 37) { $summary = $summary.Substring(0, 37) }
        $summary = $summary.PadRight(37)

        # 標籤處理（只顯示關鍵標籤）
        $keyTags = @($e.tags | Where-Object { $_ -match "^(phase1|phase2|api-call|cache-read|cache-write|sub-agent|error|blocked|team-mode)$" })
        $tagsStr = if ($keyTags.Count -gt 0) { $keyTags -join "," } else { "-" }

        $color = "White"
        if ($e.has_error) { $color = "Red" }
        elseif ($e.tags -contains "blocked") { $color = "Yellow" }
        elseif ($e.tags -contains "api-call") { $color = "Cyan" }

        Write-Host "  $time | " -NoNewline -ForegroundColor White
        Write-Host "$tool" -NoNewline -ForegroundColor White
        Write-Host "| " -NoNewline -ForegroundColor White
        Write-Host "$summary" -NoNewline -ForegroundColor $color
        Write-Host "| $tagsStr" -ForegroundColor Gray
    }

    # 統計摘要
    Write-Host ""
    Write-Section "統計摘要"
    $apiCalls = @($sorted | Where-Object { $_.tags -contains "api-call" }).Count
    $cacheReads = @($sorted | Where-Object { $_.tags -contains "cache-read" }).Count
    $errors = @($sorted | Where-Object { $_.has_error }).Count
    $blocked = @($sorted | Where-Object { $_.tags -contains "blocked" }).Count

    Write-Host "  API 呼叫: $apiCalls 次" -ForegroundColor White
    Write-Host "  快取讀取: $cacheReads 次" -ForegroundColor White
    if ($errors -gt 0) { Write-Host "  錯誤: $errors 次" -ForegroundColor Red }
    if ($blocked -gt 0) { Write-Host "  攔截: $blocked 次" -ForegroundColor Yellow }

    # 時間軸（首次呼叫 → 最後一次呼叫）
    $firstTs = try { [datetime]::Parse($sorted[0].ts) } catch { $null }
    $lastTs = try { [datetime]::Parse($sorted[-1].ts) } catch { $null }
    if ($firstTs -and $lastTs) {
        $duration = [math]::Round(($lastTs - $firstTs).TotalSeconds, 1)
        Write-Host "  總耗時: ${duration}s（從首次呼叫到最後一次）" -ForegroundColor White
    }

    Write-Host ""
}

# ============================================
# VZ2: 自動任務 7 天完成矩陣
# ============================================
function Show-TaskBoard {
    param([int]$BoardDays = 7)

    Write-Header "自動任務 ${BoardDays} 天完成矩陣"

    $historyFile = "$AgentDir\state\todoist-history.json"
    $freqLimitsFile = "$AgentDir\config\frequency-limits.yaml"

    if (-not (Test-Path $historyFile)) {
        Write-Host "  （無歷史紀錄：$historyFile）" -ForegroundColor Gray
        return
    }

    # 讀取任務定義（名稱 + counter_field）
    $taskDefs = @()
    if (Test-Path $freqLimitsFile) {
        $freqContent = Get-Content -Path $freqLimitsFile -Raw -Encoding UTF8
        $taskMatches = [regex]::Matches($freqContent, '(?m)^\s{2}(\w+):\s*\n(?:(?!\s{2}\w+:)[\s\S])*?\s{4}name:\s*(.+?)\s*\n')
        foreach ($m in $taskMatches) {
            $taskDefs += @{ key = $m.Groups[1].Value; name = $m.Groups[2].Value.Trim() }
        }
    }

    # 讀取 todoist-history.json 的 daily_summary 或 auto_tasks
    $historyRaw = Get-Content -Path $historyFile -Raw -Encoding UTF8
    $history = $historyRaw | ConvertFrom-Json

    # 建立近 N 天日期列表
    $today = Get-Date
    $dates = @()
    for ($i = $BoardDays - 1; $i -ge 0; $i--) {
        $dates += ($today.AddDays(-$i)).ToString("MM/dd")
    }
    $dateKeys = @()
    for ($i = $BoardDays - 1; $i -ge 0; $i--) {
        $dateKeys += ($today.AddDays(-$i)).ToString("yyyy-MM-dd")
    }

    # 從 auto_tasks 聚合每日每任務執行次數
    $matrix = @{}
    if ($history.auto_tasks) {
        foreach ($entry in $history.auto_tasks) {
            $d = try { ([datetime]::Parse($entry.date)).ToString("yyyy-MM-dd") } catch { "" }
            $type = $entry.type
            if ($d -and $type) {
                $matKey = "${d}|${type}"
                if (-not $matrix.ContainsKey($matKey)) { $matrix[$matKey] = 0 }
                $matrix[$matKey]++
            }
        }
    }

    # 標題列（日期）
    $headerPad = "  {0,-12}" -f "任務名稱"
    $dateHeader = ($dates | ForEach-Object { $_.PadLeft(6) }) -join " "
    Write-Host ("$headerPad $dateHeader") -ForegroundColor DarkCyan
    Write-Host ("  $('─' * (12 + 7 * $BoardDays + 1))") -ForegroundColor DarkGray

    # 任務列
    $fallbackTasks = if ($taskDefs.Count -gt 0) { $taskDefs } else {
        # Fallback：從 history 中提取唯一任務類型
        $uniqueTypes = $history.auto_tasks | Select-Object -ExpandProperty type -Unique | Sort-Object
        $uniqueTypes | ForEach-Object { @{ key = $_; name = $_ } }
    }

    $hungerAlert = @()
    foreach ($t in $fallbackTasks) {
        $taskKey = $t.key
        $taskName = if ($t.name.Length -gt 8) { $t.name.Substring(0,8) } else { $t.name }
        $row = "  {0,-12}" -f $taskName

        $zeroCount = 0
        foreach ($dk in $dateKeys) {
            $cnt = if ($matrix.ContainsKey("${dk}|${taskKey}")) { $matrix["${dk}|${taskKey}"] } else { 0 }
            $cell = switch ($cnt) {
                0 { "░" }
                1 { "█" }
                2 { "██" }
                3 { "███" }
                default { "████" }
            }
            $row += " " + $cell.PadLeft(6)
            if ($cnt -eq 0) { $zeroCount++ }
        }

        $color = if ($zeroCount -ge ($BoardDays - 1)) { "Gray" } elseif ($zeroCount -ge 3) { "Yellow" } else { "White" }
        Write-Host $row -ForegroundColor $color

        # 飢餓任務偵測（連續 3 天以上 0 次）
        $consecutiveZero = 0
        $maxConsec = 0
        foreach ($dk in $dateKeys) {
            if (($matrix["${dk}|${taskKey}"] -or 0) -eq 0) { $consecutiveZero++ } else { $consecutiveZero = 0 }
            if ($consecutiveZero -gt $maxConsec) { $maxConsec = $consecutiveZero }
        }
        if ($maxConsec -ge 3) { $hungerAlert += $t.name }
    }

    Write-Host ("  $('─' * (12 + 7 * $BoardDays + 1))") -ForegroundColor DarkGray
    Write-Host "  圖例：░=0次  █=1  ██=2  ███=3  ████=4+" -ForegroundColor DarkGray

    if ($hungerAlert.Count -gt 0) {
        Write-Host ""
        Write-Host "  ⚠ 連續 3 天以上未執行（可能饑餓）：" -ForegroundColor Yellow
        foreach ($ta in $hungerAlert) {
            Write-Host "    - $ta" -ForegroundColor Yellow
        }
    }
    Write-Host ""
}

# ============================================
# Show-Timeline: Phase 執行時間線
# ============================================
function Show-Timeline {
    Write-Host ""
    Write-Host "[Phase 執行時間線]" -ForegroundColor Cyan
    Write-Host ("  " + "─" * 60) -ForegroundColor DarkGray

    # 讀取 scheduler-state.json
    $stateFile = "$AgentDir\state\scheduler-state.json"
    if (-not (Test-Path $stateFile)) {
        Write-Host "  找不到 state/scheduler-state.json" -ForegroundColor Yellow
        return
    }

    try {
        $stateData = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Host "  無法解析 scheduler-state.json: $_" -ForegroundColor Red
        return
    }

    # 優先取 runs（daily/todoist），其次取 executions（audit）
    $allRecords = @()
    if ($stateData.runs) {
        $allRecords += $stateData.runs | Where-Object { $_.phase_breakdown -ne $null }
    }
    if ($stateData.executions) {
        $allRecords += $stateData.executions | Where-Object { $_.phase_breakdown -ne $null }
    }

    # 依時間排序，取最近 $Days 天且最多 5 筆
    $cutoff = (Get-Date).AddDays(-$Days)
    $recent = $allRecords | Where-Object {
        $ts = if ($_.start_time) { $_.start_time } else { $_.timestamp }
        try { [datetime]$ts -ge $cutoff } catch { $false }
    } | Sort-Object {
        $ts = if ($_.start_time) { $_.start_time } else { $_.timestamp }
        try { [datetime]$ts } catch { [datetime]::MinValue }
    } -Descending | Select-Object -First 5

    if ($recent.Count -eq 0) {
        Write-Host "  近 ${Days} 天內無 phase_breakdown 資料（需執行新版腳本後才會產生）" -ForegroundColor Yellow
        Write-Host ""
        return
    }

    foreach ($run in $recent) {
        $ts = if ($run.start_time) { $run.start_time } else { $run.timestamp }
        $dateStr = try { ([datetime]$ts).ToString("MM-dd HH:mm") } catch { "unknown" }
        $agentStr = if ($run.agent) { $run.agent } else { "unknown" }
        $pb = $run.phase_breakdown

        $statusColor = switch ($run.status) {
            "success" { "Green" }
            "failed"  { "Red" }
            "skipped" { "Gray" }
            default   { "White" }
        }
        Write-Host ("  [{0}] {1} ({2})" -f $dateStr, $agentStr, $run.status) -ForegroundColor $statusColor

        # Phase 1
        if ($null -ne $pb.phase1_seconds) {
            $p1 = [int]$pb.phase1_seconds
            $maxRef = 300  # 基準 300s（daily-digest Phase 1 timeout）
            $barLen = if ($maxRef -gt 0) { [int](($p1 / $maxRef) * 20) } else { 0 }
            $barLen = [Math]::Min([Math]::Max($barLen, 0), 20)
            $bar = ("█" * $barLen) + ("░" * (20 - $barLen))
            $status = if ($p1 -le $maxRef) { "✓" } else { "⚠慢" }
            $color = if ($p1 -le $maxRef) { "Green" } else { "Yellow" }
            Write-Host ("    Phase 1 [{0}] {1,4}s {2}" -f $bar, $p1, $status) -ForegroundColor $color
        }

        # Phase 2
        if ($null -ne $pb.phase2_seconds) {
            $p2 = [int]$pb.phase2_seconds
            # Todoist Phase 2 基準 720s（最長 tech_research），audit Phase 2 基準 1200s
            # daily-digest Phase 2 基準 420s
            $maxRef = switch ($agentStr) {
                "todoist-team"       { 720 }
                "system-audit-team"  { 1200 }
                default              { 420 }
            }
            $barLen = if ($maxRef -gt 0) { [int](($p2 / $maxRef) * 20) } else { 0 }
            $barLen = [Math]::Min([Math]::Max($barLen, 0), 20)
            $bar = ("█" * $barLen) + ("░" * (20 - $barLen))
            $status = if ($p2 -le $maxRef) { "✓" } else { "⚠慢" }
            $color = if ($p2 -le $maxRef) { "Green" } else { "Yellow" }
            Write-Host ("    Phase 2 [{0}] {1,4}s {2}" -f $bar, $p2, $status) -ForegroundColor $color
        }

        # Phase 3（Todoist 才有）
        if ($null -ne $pb.phase3_seconds) {
            $p3 = [int]$pb.phase3_seconds
            $maxRef = 180  # 基準 180s（Phase 3 timeout = 180s）
            $barLen = if ($maxRef -gt 0) { [int](($p3 / $maxRef) * 20) } else { 0 }
            $barLen = [Math]::Min([Math]::Max($barLen, 0), 20)
            $bar = ("█" * $barLen) + ("░" * (20 - $barLen))
            $status = if ($p3 -le $maxRef) { "✓" } else { "⚠慢" }
            $color = if ($p3 -le $maxRef) { "Green" } else { "Yellow" }
            Write-Host ("    Phase 3 [{0}] {1,4}s {2}" -f $bar, $p3, $status) -ForegroundColor $color
        }

        # 附加資訊（plan_type / phase1_agents）
        if ($pb.plan_type) {
            Write-Host ("    plan_type: {0}" -f $pb.plan_type) -ForegroundColor DarkGray
        }
        if ($pb.phase1_agents) {
            $agents = $pb.phase1_agents -join ", "
            Write-Host ("    agents: {0}" -f $agents) -ForegroundColor DarkGray
        }

        Write-Host ""
    }

    Write-Host ("  " + "─" * 60) -ForegroundColor DarkGray
    Write-Host "  圖例：基準 Phase1=300s, Phase2=420s(daily)/720s(todoist)/1200s(audit), Phase3=180s" -ForegroundColor DarkGray
    Write-Host "  ✓ = 在基準內  ⚠慢 = 超過基準  顯示最近 5 筆（含 phase_breakdown 的記錄）" -ForegroundColor DarkGray
    Write-Host ""
}

# ============================================
# Main dispatch
# ============================================
switch ($Mode) {
    "summary"      { Show-Summary }
    "detail"       { Show-Detail }
    "errors"       { Show-Errors }
    "todoist"      { Show-Todoist }
    "trend"        { Show-Trend }
    "health-score" { Show-HealthScore }
    "trace"        { Show-Trace }
    "task-board"   { Show-TaskBoard -BoardDays $Days }
    "timeline"     { Show-Timeline }
}
