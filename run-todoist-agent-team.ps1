# ============================================
# Todoist Agent Team - Parallel Orchestrator (PowerShell 7)
# ============================================
# Usage:
#   Manual: pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1
#   Task Scheduler: same command
# ============================================
# Architecture:
#   Phase 1: 1 query agent (todoist query + filter + route + plan)
#   Phase 2: N parallel agents (task execution or auto-tasks)
#   Phase 3: 1 assembly agent (close + update + notify)
# ============================================

# PowerShell 7 defaults to UTF-8, explicit set for safety
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Set paths
$AgentDir = $PSScriptRoot
$LogDir = "$AgentDir\logs"
$StateFile = "$AgentDir\state\scheduler-state.json"
$ResultsDir = "$AgentDir\results"

# Config (Phase 2 timeout is dynamic, calculated after Phase 1)
$Phase1TimeoutSeconds = 420   # Phase 1 可能需要寫 plan.json + N 個 task prompt 檔案（300s 偶爾不足）
$MaxPhase1Retries = 1     # Phase 1 query: max 2 attempts (30s interval)
$Phase3TimeoutSeconds = 180
$MaxPhase3Retries = 1

# Dynamic timeout budgets per task type
$TimeoutBudget = @{
    "research" = 600   # WebSearch/WebFetch tasks: 10 min
    "code"     = 900   # Edit/Glob/Grep tasks: 15 min
    "skill"    = 300   # Simple skill tasks: 5 min
    "general"  = 300   # General tasks: 5 min
    "auto"     = 600   # Auto-tasks (shurangama/log-audit): 10 min
    "gitpush"  = 360   # Git push + KB sync + npm generate: 6 min
    "buffer"   = 120   # CLI startup + safety buffer
}

# Per-key timeout override（秒）— 優先級高於群組預設
$AutoTaskTimeoutOverride = @{
    "creative_game"          = 900   # sync-games.ps1 npm build 最長 ~15 min
    "creative_game_optimize" = 900
    "log_audit"              = 720   # 讀 10+ log + 分析修正 + KB 匯入
    "qa_optimize"            = 720   # WebSearch CVE + Grep 掃描 + 程式碼修改
    "ai_deep_research"       = 720   # 4 階段 WebFetch
    "tech_research"          = 2600  # 讀 history + WebSearch×3 + WebFetch×4 + KB 匯入
}

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$LogDir\structured" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\context" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\cache" | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

# Generate log filename
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\todoist-team_$Timestamp.log"

# Write-Log function (UTF-8 without BOM)
function Write-Log {
    param([string]$Message)
    Write-Host $Message
    [System.IO.File]::AppendAllText($LogFile, "$Message`r`n", [System.Text.Encoding]::UTF8)
}

# Remove stderr file if empty or contains only benign warnings
# Known benign patterns: .claude.json corrupted (Claude CLI concurrency issue), Pre-flight check warnings
function Remove-StderrIfBenign {
    param([string]$StderrFile)
    if (-not (Test-Path $StderrFile)) { return }
    $size = (Get-Item $StderrFile).Length
    if ($size -eq 0) {
        Remove-Item $StderrFile -Force -ErrorAction SilentlyContinue
        return
    }
    $content = Get-Content $StderrFile -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) { return }
    # Remove known benign patterns, then check if anything meaningful remains
    $filtered = $content -replace '(?m)^.*\.claude\.json is corrupted.*$', '' `
                         -replace '(?m)^.*corrupted file has been backed up.*$', '' `
                         -replace '(?m)^.*corrupted file has already been backed up.*$', '' `
                         -replace '(?m)^.*backup file exists at.*$', '' `
                         -replace '(?m)^.*manually restore it by running.*$', '' `
                         -replace '(?m)^.*Pre-flight check is taking longer.*$', ''
    if ([string]::IsNullOrWhiteSpace($filtered)) {
        Remove-Item $StderrFile -Force -ErrorAction SilentlyContinue
    }
}

# Update scheduler state
function Update-State {
    param(
        [string]$Status,
        [int]$Duration,
        [string]$ErrorMsg,
        [hashtable]$Sections,
        [PSCustomObject]$PhaseBreakdown
    )

    $run = @{
        timestamp        = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")
        start_time       = $script:startTime.ToString("yyyy-MM-ddTHH:mm:ss")
        agent            = "todoist-team"
        status           = $Status
        duration_seconds = $Duration
        error            = $ErrorMsg
        sections         = $Sections
        log_file         = (Split-Path -Leaf $LogFile)
        phase_breakdown  = $PhaseBreakdown
    }

    if (Test-Path $StateFile) {
        try {
            $stateJson = Get-Content -Path $StateFile -Raw -Encoding UTF8
            $state = $stateJson | ConvertFrom-Json
        } catch {
            Write-Log "[WARN] scheduler-state.json corrupted, backing up and rebuilding..."
            Copy-Item $StateFile "$StateFile.corrupted.$(Get-Date -Format 'yyyyMMdd_HHmmss')" -ErrorAction SilentlyContinue
            $state = @{ runs = @() }
        }
    }
    else {
        $state = @{ runs = @() }
    }

    $runs = [System.Collections.ArrayList]@($state.runs)
    $runs.Add($run) | Out-Null

    while ($runs.Count -gt 200) {
        $runs.RemoveAt(0)
    }

    $state.runs = $runs.ToArray()
    $json = $state | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($StateFile, $json, [System.Text.Encoding]::UTF8)
}

# Update failure stats
function Update-FailureStats {
    param(
        [string]$FailureType,  # "timeout" | "api_error" | "circuit_open" | "phase_failure" | "parse_error"
        [string]$Phase = "unknown",
        [string]$AgentType = "todoist"
    )

    $statsFile = "$AgentDir\state\failure-stats.json"

    # 讀取現有統計
    if (Test-Path $statsFile) {
        try {
            $stats = Get-Content $statsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            $stats = [PSCustomObject]@{ updated = ""; daily = [PSCustomObject]@{}; total = [PSCustomObject]@{} }
        }
    } else {
        $stats = [PSCustomObject]@{ updated = ""; daily = [PSCustomObject]@{}; total = [PSCustomObject]@{} }
    }

    $today = (Get-Date).ToString("yyyy-MM-dd")

    # 確保今日條目存在
    if (-not $stats.daily.$today) {
        $stats.daily | Add-Member -NotePropertyName $today -NotePropertyValue ([PSCustomObject]@{
            timeout = 0; api_error = 0; circuit_open = 0; phase_failure = 0; parse_error = 0
        }) -Force
    }

    # 更新今日統計
    $currentVal = $stats.daily.$today.$FailureType
    if ($null -eq $currentVal) { $currentVal = 0 }
    $stats.daily.$today | Add-Member -NotePropertyName $FailureType -NotePropertyValue ($currentVal + 1) -Force

    # 更新總計
    $totalVal = $stats.total.$FailureType
    if ($null -eq $totalVal) { $totalVal = 0 }
    $stats.total | Add-Member -NotePropertyName $FailureType -NotePropertyValue ($totalVal + 1) -Force

    # 只保留 30 天
    $cutoff = (Get-Date).AddDays(-30).ToString("yyyy-MM-dd")
    $oldKeys = @($stats.daily.PSObject.Properties.Name | Where-Object { $_ -lt $cutoff })
    foreach ($k in $oldKeys) {
        $stats.daily.PSObject.Properties.Remove($k)
    }

    $stats | Add-Member -NotePropertyName "updated" -NotePropertyValue (Get-Date -Format "yyyy-MM-ddTHH:mm:ss") -Force

    # 原子寫入（write-to-temp + rename）
    $tmpFile = "$statsFile.tmp"
    $stats | ConvertTo-Json -Depth 5 | Set-Content $tmpFile -Encoding UTF8
    Move-Item $tmpFile $statsFile -Force
}

# PS 層失敗通知（Phase 3 未執行時的安全網）
function Send-FailureAlert {
    param(
        [string]$Phase,    # 失敗的階段，如 "Phase1"
        [string]$Reason    # 失敗原因
    )
    try {
        $tmpFile = [System.IO.Path]::GetTempFileName() + ".json"
        $payload = @{
            topic    = "wangsc2025"
            title    = "Todoist Team 失敗 - $Phase"
            message  = "$Reason`nLog: $(Split-Path -Leaf $LogFile)`n時間: $(Get-Date -Format 'HH:mm')"
            priority = 4
            tags     = @("warning", "robot")
        } | ConvertTo-Json -Compress
        [System.IO.File]::WriteAllText($tmpFile, $payload, [System.Text.Encoding]::UTF8)
        curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$tmpFile" https://ntfy.sh 2>$null
        Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
    }
    catch { <# 通知失敗不中斷主流程 #> }
}

# FSM 狀態管理
function Set-FsmState {
    param(
        [string]$RunId,
        [string]$Phase,
        [string]$State,
        [string]$AgentType = "todoist",
        [string]$Detail = ""
    )

    $fsmFile = "$AgentDir\state\run-fsm.json"
    $transitionFile = "$AgentDir\logs\structured\fsm-transitions.jsonl"
    $now = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"

    if (Test-Path $fsmFile) {
        try {
            $fsm = Get-Content $fsmFile -Raw | ConvertFrom-Json
        } catch {
            $fsm = [PSCustomObject]@{ runs = [PSCustomObject]@{}; updated = "" }
        }
    } else {
        $fsm = [PSCustomObject]@{ runs = [PSCustomObject]@{}; updated = "" }
    }

    $runKey = "${AgentType}_${RunId}"
    if (-not $fsm.runs.$runKey) {
        $fsm.runs | Add-Member -NotePropertyName $runKey -NotePropertyValue ([PSCustomObject]@{
            run_id     = $RunId
            agent_type = $AgentType
            started    = $now
            phases     = [PSCustomObject]@{}
        }) -Force
    }

    $fsm.runs.$runKey.phases | Add-Member -NotePropertyName $Phase -NotePropertyValue ([PSCustomObject]@{
        state   = $State
        updated = $now
        detail  = $Detail
    }) -Force

    $fsm | Add-Member -NotePropertyName "updated" -NotePropertyValue $now -Force

    $cutoff = (Get-Date).AddHours(-24).ToString("yyyy-MM-ddTHH:mm:ss")
    $oldKeys = @($fsm.runs.PSObject.Properties | Where-Object {
        $_.Value.started -lt $cutoff
    } | Select-Object -ExpandProperty Name)
    foreach ($k in $oldKeys) {
        $fsm.runs.PSObject.Properties.Remove($k)
    }

    $tmpFile = "$fsmFile.tmp"
    $fsm | ConvertTo-Json -Depth 6 | Set-Content $tmpFile -Encoding UTF8
    Move-Item $tmpFile $fsmFile -Force

    $transition = [PSCustomObject]@{
        ts         = $now
        run_id     = $RunId
        agent_type = $AgentType
        phase      = $Phase
        state      = $State
        detail     = $Detail
    }
    $transitionJson = $transition | ConvertTo-Json -Compress

    $transitionDir = Split-Path $transitionFile -Parent
    if (-not (Test-Path $transitionDir)) {
        New-Item -ItemType Directory -Path $transitionDir -Force | Out-Null
    }

    Add-Content -Path $transitionFile -Value $transitionJson -Encoding UTF8
}

# ============================================
# Start execution
# ============================================
$startTime = Get-Date

# ─── 載入環境變數（系統環境變數優先，其次從 .env 讀取）───
$envFile = "$AgentDir\.env"

# TODOIST_API_TOKEN
if (-not $env:TODOIST_API_TOKEN) {
    if (Test-Path $envFile) {
        $envLine = Get-Content $envFile | Where-Object { $_ -match '^TODOIST_API_TOKEN=' }
        if ($envLine) {
            $todoistToken = ($envLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $todoistToken, "Process")
            Write-Host "[Token] TODOIST_API_TOKEN loaded from .env"
        }
        else {
            Write-Host "[WARN] TODOIST_API_TOKEN not found in .env"
            $todoistToken = ""
        }
    }
    else {
        Write-Host "[WARN] .env not found, TODOIST_API_TOKEN may be missing"
        $todoistToken = ""
    }
}
else {
    $todoistToken = $env:TODOIST_API_TOKEN
    Write-Host "[Token] TODOIST_API_TOKEN loaded from environment"
}

# BOT_API_SECRET（chatroom 認證，從 .env 讀取作為備援）
if (-not $env:BOT_API_SECRET) {
    if (Test-Path $envFile) {
        $botSecretLine = Get-Content $envFile | Where-Object { $_ -match '^BOT_API_SECRET=' }
        if ($botSecretLine) {
            $botSecret = ($botSecretLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable("BOT_API_SECRET", $botSecret, "Process")
            Write-Host "[Token] BOT_API_SECRET loaded from .env"
        }
        # 無 BOT_API_SECRET 時靜默略過（chatroom 為可選整合）
    }
}

# ─── 生產環境安全策略 ───
# 若未設定則預設 strict（排程器執行環境），手動執行可覆蓋
if (-not (Test-Path Env:HOOK_SECURITY_PRESET)) {
    $env:HOOK_SECURITY_PRESET = "strict"
}
Write-Log "[Security] HOOK_SECURITY_PRESET = $($env:HOOK_SECURITY_PRESET)"

# Generate trace ID for distributed tracing
$traceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
Write-Log "=== Todoist Agent Team start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Log "Trace ID: $traceId"
Write-Log "Mode: parallel (Phase 1 x1 + Phase 2 xN + Phase 3 x1)"

# Check if claude is installed
$claudePath = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudePath) {
    Write-Log "[ERROR] claude not found, install: npm install -g @anthropic-ai/claude-code"
    Update-State -Status "failed" -Duration 0 -ErrorMsg "claude not found" -Sections @{}
    exit 1
}

# ============================================
# Phase 0: Circuit Breaker 預檢查
# ============================================
Write-Log ""
Write-Log "=== Phase 0: Circuit Breaker precheck ==="

# 載入預檢查工具
$utilsPath = "$AgentDir\circuit-breaker-utils.ps1"
if (Test-Path $utilsPath) {
    . $utilsPath
    Write-Log "[預檢查] 已載入 circuit-breaker-utils.ps1"

    # 檢查 Todoist API 狀態
    $todoistState = Test-CircuitBreaker "todoist"

    if ($todoistState -eq "open") {
        Write-Log "[預檢查] ✗ Todoist API 為 OPEN 狀態，Circuit Breaker 啟動"
        Write-Log "[預檢查] Todoist 為核心 API，跳過本次執行"
        Update-FailureStats "circuit_open" "phase0" "todoist"
        $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
        Update-State -Status "skipped" -Duration $totalDuration -ErrorMsg "todoist circuit breaker open" -Sections @{ todoist = "circuit_open" }
        exit 0
    }
    elseif ($todoistState -eq "half_open") {
        Write-Log "[預檢查] ⚠ Todoist API 為 HALF_OPEN 狀態，將正常執行（試探模式）"
    }
    else {
        Write-Log "[預檢查] ✓ Todoist API 為 CLOSED 狀態，正常執行"
    }
}
else {
    Write-Log "[WARN] circuit-breaker-utils.ps1 不存在，跳過預檢查"
}

# ============================================
# Phase 1: Query + Filter + Route + Plan
# ============================================
Write-Log ""
Write-Log "=== Phase 1: Query & Plan start ==="
$phase1Start = Get-Date
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "running" -AgentType "todoist"

$queryPrompt = "$AgentDir\prompts\team\todoist-query.md"
if (-not (Test-Path $queryPrompt)) {
    Write-Log "[ERROR] Query prompt not found: $queryPrompt"
    Update-State -Status "failed" -Duration 0 -ErrorMsg "query prompt not found" -Sections @{}
    exit 1
}

$queryContent = Get-Content -Path $queryPrompt -Raw -Encoding UTF8
$phase1Success = $false
$phase1Attempt = 0

while ($phase1Attempt -le $MaxPhase1Retries) {
    if ($phase1Attempt -gt 0) {
        $p1Backoff = 30 + (Get-Random -Minimum 0 -Maximum 10)
        Write-Log "[Phase1] Retry attempt $($phase1Attempt + 1) in ${p1Backoff}s..."
        Start-Sleep -Seconds $p1Backoff
    }

    Write-Log "[Phase1] Running query agent (attempt $($phase1Attempt + 1))..."

    try {
        $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
            param($prompt, $logDir, $timestamp, $traceId, $apiToken)

            # 明確設定 Process 級別環境變數（會傳遞到子 process）
            [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
            [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
            [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase1", "Process")
            [System.Environment]::SetEnvironmentVariable("AGENT_NAME", "todoist-query", "Process")
            if ($apiToken) {
                [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
            }

            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $OutputEncoding = [System.Text.Encoding]::UTF8

            $stderrFile = "$logDir\query-stderr-$timestamp.log"
            $output = $prompt | claude -p --allowedTools "Read,Bash,Write" 2>$stderrFile

            # 執行成功且 stderr 為空 → 刪除
            if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                $stderrSize = (Get-Item $stderrFile).Length
                if ($stderrSize -eq 0) {
                    Remove-Item $stderrFile -Force
                }
            }

            return $output
        } -ArgumentList $queryContent, $LogDir, $Timestamp, $traceId, $todoistToken

        # G28: chatroom-query Phase 1 並行 Job（軟依賴，失敗不影響主流程）
        $chatroomQueryPrompt = "$AgentDir\prompts\team\chatroom-query.md"
        $chatroom_job = $null
        if (Test-Path $chatroomQueryPrompt) {
            $chatroomContent = Get-Content -Path $chatroomQueryPrompt -Raw -Encoding UTF8
            $botApiSecret = $env:BOT_API_SECRET  # 讀取 bot API secret（若未設定則空字串）
            $chatroom_job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                param($prompt, $logDir, $timestamp, $traceId, $botSecret)
                [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase1", "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_NAME", "chatroom-query", "Process")
                if ($botSecret) {
                    [System.Environment]::SetEnvironmentVariable("BOT_API_SECRET", $botSecret, "Process")
                }
                [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                $OutputEncoding = [System.Text.Encoding]::UTF8
                $stderrFile = "$logDir\chatroom-query-stderr-$timestamp.log"
                $output = $prompt | claude -p --allowedTools "Read,Bash,Write" 2>$stderrFile
                if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                    $stderrSize = (Get-Item $stderrFile).Length
                    if ($stderrSize -eq 0) { Remove-Item $stderrFile -Force }
                }
                return $output
            } -ArgumentList $chatroomContent, $LogDir, $Timestamp, $traceId, $botApiSecret
            Write-Log "[Phase1] G28 chatroom-query job started (Job $($chatroom_job.Id))"
        }
        else {
            Write-Log "[Phase1] G28 chatroom-query prompt not found, skipping"
        }

        $completed = $job | Wait-Job -Timeout $Phase1TimeoutSeconds

        if ($null -eq $completed) {
            $partialOutput = Receive-Job $job -ErrorAction SilentlyContinue
            if ($partialOutput) { foreach ($line in $partialOutput) { Write-Log "  [query] $line" } }
            Stop-Job $job
            Write-Log "[Phase1] TIMEOUT after ${Phase1TimeoutSeconds}s"
            Update-FailureStats "timeout" "phase1" "todoist"
        }
        else {
            $output = Receive-Job $job
            # Log last 10 lines
            $outputLines = @($output)
            $startIdx = [Math]::Max(0, $outputLines.Count - 10)
            for ($i = $startIdx; $i -lt $outputLines.Count; $i++) {
                Write-Log "  [query] $($outputLines[$i])"
            }
            if ($job.State -eq 'Completed') { $phase1Success = $true }
        }
        Remove-Job $job -Force

        # G28: 收集 chatroom-query job 結果（軟依賴，失敗靜默忽略）
        if ($null -ne $chatroom_job) {
            $chatroomCompleted = $chatroom_job | Wait-Job -Timeout 120
            if ($null -eq $chatroomCompleted) {
                Stop-Job $chatroom_job -ErrorAction SilentlyContinue
                Write-Log "[Phase1] G28 chatroom-query TIMEOUT (120s), skipping"
            }
            else {
                $chatroomOutput = Receive-Job $chatroom_job -ErrorAction SilentlyContinue
                if ($chatroom_job.State -eq 'Completed') {
                    Write-Log "[Phase1] G28 chatroom-query completed"
                }
                else {
                    Write-Log "[Phase1] G28 chatroom-query failed (state: $($chatroom_job.State)), continuing"
                }
            }
            Remove-Job $chatroom_job -Force -ErrorAction SilentlyContinue
            # 確認結果檔案狀態
            if (Test-Path "$ResultsDir\chatroom-plan.json") {
                Write-Log "[Phase1] G28 chatroom-plan.json produced"
            }
            else {
                Write-Log "[Phase1] G28 chatroom-plan.json not produced (bot.js may be offline)"
            }
        }
    }
    catch {
        Write-Log "[Phase1] Error: $_"
    }

    if ($phase1Success) { break }
    $phase1Attempt++
}

# ─── Phase 1 Fallback: 若計畫檔在執行視窗內已寫入，即使 Job 超時也視為成功 ───
# 根因：Claude CLI 寫完 todoist-plan.json 後可能繼續做收尾（日誌/狀態），
# 導致 PS Job 超時而計畫檔實際上已完整產出。
if (-not $phase1Success -and (Test-Path "$ResultsDir\todoist-plan.json")) {
    $planAge = [int]((Get-Date) - (Get-Item "$ResultsDir\todoist-plan.json").LastWriteTime).TotalSeconds
    $maxValidAge = ($MaxPhase1Retries + 1) * $Phase1TimeoutSeconds + 60  # 執行視窗（2×420）+ 60s 緩衝 = 900s
    if ($planAge -lt $maxValidAge) {
        $phase1Success = $true
        Write-Log "[Phase1] Fallback: 計畫檔在超時前已寫入（age=${planAge}s），繼續執行"
    }
    else {
        Write-Log "[Phase1] 計畫檔過舊（age=${planAge}s, threshold=${maxValidAge}s），跳過"
    }
}

$phase1End = Get-Date
$phase1Seconds = [int]($phase1End - $phase1Start).TotalSeconds
$phase1Duration = [int]($phase1End - $startTime).TotalSeconds
Write-Log "=== Phase 1 complete (${phase1Duration}s from start, ${phase1Seconds}s phase-only) ==="
if ($phase1Success) {
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "completed" -AgentType "todoist" -Detail "plan_type=$($plan.plan_type)"
} else {
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "failed" -AgentType "todoist" -Detail "query/plan failed"
}

# ─── Circuit Breaker 自動更新（基於 Phase 1 結果）───
if (Get-Command Update-CircuitBreaker -ErrorAction SilentlyContinue) {
    $cbSuccess = $phase1Success -and (Test-Path "$ResultsDir\todoist-plan.json")
    Update-CircuitBreaker -ApiName "todoist" -Success $cbSuccess
    Write-Log "[Circuit Breaker] Todoist 更新: $(if ($cbSuccess) { 'success ✓' } else { 'failure ✗' })"
}

# Check Phase 1 result
$planFile = "$ResultsDir\todoist-plan.json"
if (-not $phase1Success -or -not (Test-Path $planFile)) {
    Write-Log "[ERROR] Phase 1 failed or plan file not found"
    Update-FailureStats "phase_failure" "phase1" "todoist"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "phase 1 failed" -Sections @{ query = "failed" }
    Send-FailureAlert -Phase "Phase1" -Reason "查詢/規劃逾時（$($MaxPhase1Retries + 1) 次嘗試均失敗）"
    exit 1
}

# Parse plan
try {
    $planJson = Get-Content -Path $planFile -Raw -Encoding UTF8
    $plan = $planJson | ConvertFrom-Json
    Write-Log "[Phase1] plan_type=$($plan.plan_type) | tasks=$($plan.tasks.Count)"
}
catch {
    Write-Log "[ERROR] Failed to parse plan: $_"
    Update-FailureStats "parse_error" "phase1" "todoist"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "plan parse error" -Sections @{ query = "failed" }
    exit 1
}

# ============================================
# Dynamic Phase 2 Timeout Calculation
# ============================================
$Phase2TimeoutSeconds = $TimeoutBudget["buffer"]  # Start with buffer

if ($plan.plan_type -eq "tasks") {
    # Determine max timeout from task types (parallel = max, not sum)
    $maxTaskTimeout = 0
    foreach ($task in $plan.tasks) {
        $tools = $task.allowed_tools
        if ($tools -match "Edit|Glob|Grep") {
            $taskTimeout = $TimeoutBudget["code"]
        }
        elseif ($tools -match "WebSearch|WebFetch") {
            $taskTimeout = $TimeoutBudget["research"]
        }
        else {
            $taskTimeout = $TimeoutBudget["skill"]
        }
        if ($taskTimeout -gt $maxTaskTimeout) { $maxTaskTimeout = $taskTimeout }
    }
    $Phase2TimeoutSeconds += $maxTaskTimeout
}
elseif ($plan.plan_type -eq "auto") {
    # Auto-tasks: parallel = take max timeout across all selected tasks (not sum)
    $selectedTasks = $plan.auto_tasks.selected_tasks
    if ($null -ne $selectedTasks -and $selectedTasks.Count -gt 0) {
        $maxAutoTimeout = 0
        foreach ($autoTask in $selectedTasks) {
            $thisTimeout = if ($autoTask.key -eq "git_push") {
                $TimeoutBudget["gitpush"]                        # 360s（特殊）
            } elseif ($AutoTaskTimeoutOverride.ContainsKey($autoTask.key)) {
                $AutoTaskTimeoutOverride[$autoTask.key]          # per-key override
            } else {
                $TimeoutBudget["auto"]                           # 預設 600s
            }
            if ($thisTimeout -gt $maxAutoTimeout) { $maxAutoTimeout = $thisTimeout }
        }
        $Phase2TimeoutSeconds += $maxAutoTimeout
    }
}
# plan_type == "idle" → stays at buffer only (no Phase 2 work)

Write-Log "[Dynamic] Phase2 timeout = ${Phase2TimeoutSeconds}s (plan_type=$($plan.plan_type))"

# ============================================
# Phase 2: Parallel Execution
# ============================================
Write-Log ""
Write-Log "=== Phase 2: Parallel execution start ==="
$phase2Start = Get-Date
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "running" -AgentType "todoist"

$phase2Jobs = @()
$sections = @{ query = "success" }

if ($plan.plan_type -eq "tasks") {
    # Scenario A: Execute Todoist tasks in parallel
    foreach ($task in $plan.tasks) {
        $promptFile = $task.prompt_file
        if (-not (Test-Path "$AgentDir\$promptFile")) {
            Write-Log "[Phase2] Task prompt not found: $promptFile"
            continue
        }
        $taskPrompt = Get-Content -Path "$AgentDir\$promptFile" -Raw -Encoding UTF8
        $taskTools = $task.allowed_tools

        $taskName = "task-$($task.rank)"

        $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
            param($prompt, $tools, $taskName, $logDir, $timestamp, $traceId, $apiToken)

            # 明確設定 Process 級別環境變數（會傳遞到子 process）
            [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
            [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
            [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2", "Process")
            [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $taskName, "Process")
            if ($apiToken) {
                [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
            }

            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $OutputEncoding = [System.Text.Encoding]::UTF8

            $stderrFile = "$logDir\$taskName-stderr-$timestamp.log"
            $output = $prompt | claude -p --allowedTools $tools 2>$stderrFile

            # 執行成功且 stderr 為空 → 刪除
            if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                $stderrSize = (Get-Item $stderrFile).Length
                if ($stderrSize -eq 0) {
                    Remove-Item $stderrFile -Force
                }
            }

            return $output
        } -ArgumentList $taskPrompt, $taskTools, $taskName, $LogDir, $Timestamp, $traceId, $todoistToken

        $job | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $taskName
        $phase2Jobs += $job
        Write-Log "[Phase2] Started: $taskName (Job $($job.Id)) - $($task.content)"
    }
}
elseif ($plan.plan_type -eq "auto") {
    # Scenario B: Execute auto-tasks selected by Phase 1 (up to 4 in parallel)
    $selectedTasks = $plan.auto_tasks.selected_tasks

    if ($null -eq $selectedTasks -or $selectedTasks.Count -eq 0) {
        Write-Log "[Phase2] No auto-tasks selected (all exhausted or error)"
    }
    else {
        Write-Log "[Phase2] Starting $($selectedTasks.Count) auto-task agents in parallel..."

        # Dedicated team prompts：動態掃描實際檔案，防止重命名後路徑失效
        # 命名規則：prompts/team/todoist-auto-{plan_key}.md（底線，與 frequency-limits.yaml key 一致）
        $dedicatedPrompts = @{}
        Get-ChildItem "$AgentDir\prompts\team\todoist-auto-*.md" -ErrorAction SilentlyContinue | ForEach-Object {
            $key = $_.BaseName -replace "^todoist-auto-", ""
            $dedicatedPrompts[$key] = $_.FullName
        }
        Write-Log "[Phase2] Discovered $($dedicatedPrompts.Count) dedicated prompts: $($dedicatedPrompts.Keys -join ', ')"

        foreach ($autoTask in $selectedTasks) {
            $taskKey = $autoTask.key
            $taskName = $autoTask.name

            # Key 正規化：LLM 產出的 key 格式不穩定（連字號/縮寫/遺漏 _research 後綴）
            # Step 1: 統一連字號→底線（最常見不一致：tech-research、ai-deep-research）
            $normalizedKey = $taskKey -replace '-', '_'
            # Step 2: 別名表（縮寫/遺漏後綴 → 標準 key，與 frequency-limits.yaml YAML key 一致）
            $keyAliases = @{
                # 無分隔符縮寫（LLM 可能省略分隔符）
                "logaudit"           = "log_audit"
                "gitpush"            = "git_push"
                "techresearch"       = "tech_research"
                "aideepresearch"     = "ai_deep_research"
                "unsloth"            = "unsloth_research"   # 省略 _research
                "aigithub"           = "ai_github_research"
                "aismartcity"        = "ai_smart_city"
                "aisysdev"           = "ai_sysdev"
                "skillaudit"         = "skill_audit"
                "qaoptimize"         = "qa_optimize"
                "systeminsight"      = "system_insight"
                "selfheal"           = "self_heal"
                "githubscout"        = "github_scout"
                # 短形式別名（LLM 省略 _research 後綴）
                "ai_github"          = "ai_github_research"
                "ai_deep"            = "ai_deep_research"
                "ai_smart"           = "ai_smart_city"
                "creative_game"      = "creative_game_optimize"
            }
            if ($keyAliases.ContainsKey($normalizedKey)) {
                $normalizedKey = $keyAliases[$normalizedKey]
            }
            if (-not $dedicatedPrompts.ContainsKey($normalizedKey) -and $dedicatedPrompts.ContainsKey($taskKey)) {
                $normalizedKey = $taskKey
            }
            if ($normalizedKey -ne $taskKey) {
                Write-Log "[Phase2] Key normalized: $taskKey -> $normalizedKey"
            }

            if ($dedicatedPrompts.ContainsKey($normalizedKey) -and (Test-Path $dedicatedPrompts[$normalizedKey])) {
                $promptToUse = $dedicatedPrompts[$normalizedKey]
                Write-Log "[Phase2] Using dedicated prompt for $normalizedKey"
            }
            else {
                Write-Log "[Phase2] No dedicated prompt found for $taskKey (normalized: $normalizedKey), skipping"
                $sections["auto-$taskKey"] = "skipped"
                continue
            }

            $promptContent = Get-Content -Path $promptToUse -Raw -Encoding UTF8

            # G10: 若 todoist-plan.json 中有 prompt_content，前置到 prompt 開頭
            # JSON null → PS $null；字串 "null" 亦排除（防 LLM 將 null 輸出為字串）
            $promptContent_override = $autoTask.prompt_content
            if ($promptContent_override -and $promptContent_override -ne "null") {
                $promptContent = "$promptContent_override`n`n$promptContent"
                Write-Log "[Phase2] G10 prompt_content injected for $normalizedKey"
            }

            $agentName = "auto-$taskKey"

            $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                param($prompt, $agentName, $logDir, $timestamp, $traceId, $apiToken)

                # 明確設定 Process 級別環境變數（會傳遞到子 process）
                [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2-auto", "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
                if ($apiToken) {
                    [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
                }

                [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                $OutputEncoding = [System.Text.Encoding]::UTF8

                $stderrFile = "$logDir\$agentName-stderr-$timestamp.log"
                $output = $prompt | claude -p --allowedTools "Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch" 2>$stderrFile

                # 執行成功且 stderr 為空 → 刪除
                if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                    $stderrSize = (Get-Item $stderrFile).Length
                    if ($stderrSize -eq 0) {
                        Remove-Item $stderrFile -Force
                    }
                }

                return $output
            } -ArgumentList $promptContent, $agentName, $LogDir, $Timestamp, $traceId, $todoistToken

            $job | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $agentName
            $phase2Jobs += $job
            Write-Log "[Phase2] Started: $agentName ($taskName) (Job $($job.Id))"
        }
    }
}
else {
    # Scenario C: idle
    Write-Log "[Phase2] Idle - all auto-tasks at daily limit"
}

# Wait for Phase 2 jobs
if ($phase2Jobs.Count -gt 0) {
    Write-Log "[Phase2] Waiting for $($phase2Jobs.Count) agents (timeout: ${Phase2TimeoutSeconds}s)..."
    $phase2Jobs | Wait-Job -Timeout $Phase2TimeoutSeconds | Out-Null
}

# Collect Phase 2 results
foreach ($job in $phase2Jobs) {
    $agentName = $job.AgentName
    $output = Receive-Job -Job $job -ErrorAction SilentlyContinue

    if ($job.State -eq "Completed") {
        if ($output) {
            $outputLines = @($output)
            $startIdx = [Math]::Max(0, $outputLines.Count - 5)
            for ($i = $startIdx; $i -lt $outputLines.Count; $i++) {
                Write-Log "  [$agentName] $($outputLines[$i])"
            }
        }
        $sections[$agentName] = "success"
        Write-Log "[Phase2] $agentName completed"
    }
    elseif ($job.State -eq "Running") {
        Write-Log "[Phase2] $agentName TIMEOUT - stopping"
        Stop-Job -Job $job
        $sections[$agentName] = "timeout"
        Update-FailureStats "timeout" "phase2" "todoist"
    }
    else {
        Write-Log "[Phase2] $agentName failed (state: $($job.State))"
        if ($output) { foreach ($line in @($output)) { Write-Log "  [$agentName] $line" } }
        $sections[$agentName] = "failed"
        Update-FailureStats "phase_failure" "phase2" "todoist"
    }
}

$phase2Jobs | Remove-Job -Force -ErrorAction SilentlyContinue

# Clean up stderr files (empty or containing only benign warnings)
Get-ChildItem "$LogDir\*-stderr-$Timestamp.log" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-StderrIfBenign $_.FullName
}

$phase2Seconds = [int]((Get-Date) - $phase2Start).TotalSeconds
$phase2Duration = [int]((Get-Date) - $startTime).TotalSeconds - $phase1Duration
Write-Log ""
Write-Log "=== Phase 2 complete (${phase2Duration}s from start, ${phase2Seconds}s phase-only) ==="
$phase2FailCount = @($phase2Jobs | Where-Object { $_.AgentName } | ForEach-Object {
    $n = $_.AgentName; $sections[$n]
} | Where-Object { $_ -eq "failed" -or $_ -eq "timeout" }).Count
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "completed" -AgentType "todoist" -Detail "$($phase2Jobs.Count) agents done, $phase2FailCount failed"

# ============================================
# Phase 3: Assembly (close + update + notify)
# ============================================
Write-Log ""
Write-Log "=== Phase 3: Assembly start ==="
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "running" -AgentType "todoist"

$assemblePrompt = "$AgentDir\prompts\team\todoist-assemble.md"
if (-not (Test-Path $assemblePrompt)) {
    Write-Log "[ERROR] Assembly prompt not found: $assemblePrompt"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "assembly prompt not found" -Sections $sections
    exit 1
}

$assembleContent = Get-Content -Path $assemblePrompt -Raw -Encoding UTF8
$phase3Success = $false
$phase3Seconds = 0
$attempt = 0
$phase3StartOuter = Get-Date

while ($attempt -le $MaxPhase3Retries) {
    if ($attempt -gt 0) {
        $backoff = [math]::Min(60 * [math]::Pow(2, $attempt), 300)
        $jitter = Get-Random -Minimum 0 -Maximum 15
        $waitSec = [int]($backoff + $jitter)
        Write-Log "[Phase3] Retry attempt $($attempt + 1) in ${waitSec}s (backoff=${backoff}+jitter=${jitter})..."
        Start-Sleep -Seconds $waitSec
    }

    Write-Log "[Phase3] Running assembly agent (attempt $($attempt + 1))..."
    $phase3Start = Get-Date

    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        # Set trace ID and phase marker for Phase 3
        $env:DIGEST_TRACE_ID = $traceId
        $env:AGENT_PHASE = "phase3"
        $env:AGENT_NAME = "todoist-assemble"

        $stderrFile = "$LogDir\assemble-stderr-$Timestamp.log"
        $output = $assembleContent | claude -p --allowedTools "Read,Bash,Write" 2>$stderrFile

        # 清理 stderr（空檔或僅含已知無害警告）
        Remove-StderrIfBenign $stderrFile

        $output | ForEach-Object {
            Write-Log "  [assemble] $_"
        }

        if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
            $phase3Success = $true
            $phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
            Write-Log "[Phase3] Assembly completed (${phase3Seconds}s)"
            Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "completed" -AgentType "todoist"
            break
        }
        else {
            Write-Log "[Phase3] Assembly exited with code: $LASTEXITCODE"
            Update-FailureStats "phase_failure" "phase3" "todoist"
            Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "failed" -AgentType "todoist" -Detail "exit code $LASTEXITCODE"
        }
    }
    catch {
        Write-Log "[Phase3] Assembly failed: $_"
        Update-FailureStats "phase_failure" "phase3" "todoist"
        Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "failed" -AgentType "todoist" -Detail "$_"
    }

    $attempt++
}

# 若 phase3 未成功完成（失敗/未賦值），用外層計時估算
if ($phase3Seconds -eq 0) {
    $phase3Seconds = [int]((Get-Date) - $phase3StartOuter).TotalSeconds
}

# ============================================
# Final status
# ============================================
$totalDuration = [int]((Get-Date) - $startTime).TotalSeconds

# 組合 phase_breakdown
$phaseBreakdown = [PSCustomObject]@{
    phase1_seconds = $phase1Seconds
    phase2_seconds = $phase2Seconds
    phase3_seconds = $phase3Seconds
    plan_type      = $plan.plan_type
}

if ($phase3Success) {
    Write-Log ""
    Write-Log "=== Todoist Agent Team done (success): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Write-Log "Total: ${totalDuration}s (Phase1: ${phase1Seconds}s + Phase2: ${phase2Seconds}s + Phase3: ${phase3Seconds}s)"
    Update-State -Status "success" -Duration $totalDuration -ErrorMsg $null -Sections $sections -PhaseBreakdown $phaseBreakdown
}
else {
    Write-Log ""
    Write-Log "=== Todoist Agent Team done (failed): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    Write-Log "Total: ${totalDuration}s"
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "assembly failed after $($MaxPhase3Retries + 1) attempts" -Sections $sections -PhaseBreakdown $phaseBreakdown
}

# Clean up logs older than 7 days
Get-ChildItem -Path $LogDir -Filter "todoist-team_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force
