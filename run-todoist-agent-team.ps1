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

# Config (Phase 2 timeout 由 config/timeouts.yaml 載入，見 ADR-015；Phase1/Phase3 下方載入後可覆寫)
$Phase1TimeoutSeconds = 420   # fallback：Phase 1 寫 plan.json + task prompt（300s 偶爾不足）
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
# 注意：新增自動任務時必須同步更新此處（與 config/timeouts.yaml phase2_timeout_by_task 保持一致）
$AutoTaskTimeoutOverride = @{
    # === 研究類（WebSearch/WebFetch + KB 匯入）===
    "ai_github_research"     = 900   # GitHub WebSearch×3 + WebFetch + KB 匯入（原缺失回落 600s 導致超時）
    "ai_workflow_github"     = 720   # GitHub workflow 研究 + KB 匯入
    "ai_deep_research"       = 720   # 4 階段 WebFetch
    "unsloth_research"       = 720   # WebSearch + WebFetch + KB 匯入
    "tech_research"          = 2600  # 讀 history + WebSearch×3 + WebFetch×4 + KB 匯入
    # === 佛學研究類（WebFetch 多章 + KB 匯入）===
    "shurangama"             = 900   # 楞嚴經 WebFetch 多章 + KB 匯入
    "jiaoguangzong"          = 900   # 教觀綱宗多章 + KB 匯入
    "fahua"                  = 900   # 法華多章 + KB 匯入
    "jingtu"                 = 900   # 淨土多章 + KB 匯入
    # === 系統類（重 context，含 sub-agent）===
    "skill_audit"            = 720   # sub-agent 掃描 26 SKILL.md + KB 搜尋
    "system_insight"         = 720   # sub-agent 分析 logs/state + 更新 system-insight.json
    "log_audit"              = 720   # sub-agent 讀 10+ log + 分析修正 + KB 匯入
    "qa_optimize"            = 720   # WebSearch CVE + Grep 掃描 + 程式碼修改
    "self_heal"              = 720   # 多步驟修復 + ntfy
    "arch_evolution"         = 900   # 讀 improvement-backlog + context/*.json + 架構決策
    "chatroom_optimize"      = 480   # sub-agent log 分析 + routing.yaml 調整
    # === 創意類 ===
    "creative_game"          = 900   # sync-games.ps1 npm build 最長 ~15 min
    "creative_game_optimize" = 900
    # === 長時媒體類（TTS + 上傳）===
    "podcast_create"         = 2400  # 腳本生成 + TTS(40段) + concat + R2 上傳
    "podcast_jiaoguangzong"  = 2400  # 教觀綱宗 Podcast：30-40 輪 TTS + concat + R2 上傳
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

# 從 selected_tasks 項目取出正規化 key（與 Phase 2 一致，避免 result path / failed 記錄用錯 key）
function Get-NormalizedAutoTaskKey {
    param([object]$Item)
    $raw = if ($null -ne $Item -and $Item.PSObject.Properties['key']) {
        $Item.key
    } elseif ($Item -is [string] -and $Item -match '^@{key=([^;]+)') {
        $Matches[1].Trim()
    } else {
        $Item
    }
    $normalized = $raw -replace '-', '_'
    $keyAliases = @{
        "logaudit" = "log_audit"; "gitpush" = "git_push"; "techresearch" = "tech_research"
        "aideepresearch" = "ai_deep_research"; "unsloth" = "unsloth_research"; "aigithub" = "ai_github_research"
        "aismartcity" = "ai_smart_city"; "aisysdev" = "ai_sysdev"; "skillaudit" = "skill_audit"
        "qaoptimize" = "qa_optimize"; "systeminsight" = "system_insight"; "selfheal" = "self_heal"
        "githubscout" = "github_scout"; "ai_github" = "ai_github_research"; "ai_deep" = "ai_deep_research"
        "ai_smart" = "ai_smart_city"; "creative_game" = "creative_game_optimize"; "podcastcreate" = "podcast_create"
        "podcast" = "podcast_create"
    }
    if ($keyAliases.ContainsKey($normalized)) { $keyAliases[$normalized] } else { $normalized }
}

# 自動任務失敗追蹤（state/failed-auto-tasks.json）
function Update-FailedAutoTasks {
    param(
        [string]$TaskKey,
        [string]$Reason = "result_file_missing",  # "result_file_missing" | "timeout" | "job_failed"
        [bool]$Succeeded = $false
    )
    $failedFile = "$AgentDir\state\failed-auto-tasks.json"
    $nowIso = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")

    # 讀取或初始化
    $data = if (Test-Path $failedFile) {
        try {
            $parsed = Get-Content $failedFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
            if ($null -eq $parsed.entries) {
                $parsed | Add-Member -NotePropertyName 'entries' -NotePropertyValue @() -Force
            }
            $parsed
        } catch {
            [PSCustomObject]@{ version = 1; entries = @(); updated_at = $nowIso }
        }
    } else {
        [PSCustomObject]@{ version = 1; entries = @(); updated_at = $nowIso }
    }

    $entries = [System.Collections.ArrayList]@($data.entries)
    # 正規化既有條目的 task_key（可能為 @{key=...} 字串），以便比對與後續寫回純 key
    foreach ($e in $entries) {
        if ($e.task_key -match '^@{key=([^;]+)') {
            $e.task_key = (Get-NormalizedAutoTaskKey -Item $Matches[1].Trim())
        }
    }
    $existing = $entries | Where-Object { $_.task_key -eq $TaskKey }

    if ($Succeeded) {
        if ($existing -and [int]$existing.consecutive_count -gt 0) {
            $existing.consecutive_count = 0
            $existing | Add-Member -NotePropertyName 'last_success_at' -NotePropertyValue $nowIso -Force
            Write-Log "[FailedTasks] $TaskKey succeeded — consecutive_count reset to 0"
        }
    } else {
        if ($existing) {
            $existing.consecutive_count = [int]$existing.consecutive_count + 1
            $existing.last_failed_at = $nowIso
            $existing.reason = $Reason
        } else {
            $newEntry = [PSCustomObject]@{
                task_key          = $TaskKey
                first_failed_at   = $nowIso
                last_failed_at    = $nowIso
                reason            = $Reason
                consecutive_count = 1
                reset_count       = 0
            }
            $entries.Add($newEntry) | Out-Null
        }
        $curCount = if ($existing) { [int]$existing.consecutive_count } else { 1 }
        Write-Log "[FailedTasks] $TaskKey failure recorded (reason=$Reason, consecutive=$curCount)" "WARN"
    }

    # 清除連續失敗為 0 且超過 7 天的條目
    $cutoff = (Get-Date).AddDays(-7)
    $filtered = $entries | Where-Object {
        [int]$_.consecutive_count -gt 0 -or
        (try { [datetime]$_.last_failed_at -ge $cutoff } catch { $true })
    }

    $data.entries = @($filtered)
    $data | Add-Member -NotePropertyName 'updated_at' -NotePropertyValue $nowIso -Force
    $data | ConvertTo-Json -Depth 5 | Set-Content $failedFile -Encoding UTF8 -Force
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

    # P2-A: 殭屍狀態清理（running 超過 stale_timeout_hours → timeout）
    $staleHours = 2  # 與 config/timeouts.yaml fsm.stale_timeout_hours 同步
    $staleCutoff = (Get-Date).AddHours(-$staleHours).ToString("yyyy-MM-ddTHH:mm:ss")
    foreach ($existingRun in @($fsm.runs.PSObject.Properties)) {
        foreach ($existingPhase in @($existingRun.Value.phases.PSObject.Properties)) {
            if ($existingPhase.Value.state -eq "running" -and $existingPhase.Value.updated -lt $staleCutoff) {
                $existingPhase.Value | Add-Member -NotePropertyName "state" -NotePropertyValue "timeout" -Force
                $existingPhase.Value | Add-Member -NotePropertyName "detail" -NotePropertyValue "auto-timeout: running > ${staleHours}h" -Force
            }
        }
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

    # 清理：已完成/失敗/timeout 超過 24 小時的 runs（不清除仍 running 的 runs）
    $cutoff24h = (Get-Date).AddHours(-24).ToString("yyyy-MM-ddTHH:mm:ss")
    $doneOldKeys = @($fsm.runs.PSObject.Properties | Where-Object {
        $run = $_.Value
        $phases = @($run.phases.PSObject.Properties.Value)
        $isOld = $run.started -lt $cutoff24h
        $allDone = $phases.Count -gt 0 -and ($phases | Where-Object { $_.state -eq "running" }).Count -eq 0
        $isOld -and $allDone
    } | Select-Object -ExpandProperty Name)
    foreach ($k in $doneOldKeys) {
        $fsm.runs.PSObject.Properties.Remove($k)
    }

    # max_entries 限制（超過 20 則移除最舊的已完成 run）
    $maxEntries = 20  # 與 config/timeouts.yaml fsm.max_entries 同步
    $runCount = ($fsm.runs.PSObject.Properties | Measure-Object).Count
    if ($runCount -gt $maxEntries) {
        $toRemoveCount = $runCount - $maxEntries
        $doneRunsToRemove = @($fsm.runs.PSObject.Properties | Where-Object {
            $phases = @($_.Value.phases.PSObject.Properties.Value)
            $phases.Count -gt 0 -and ($phases | Where-Object { $_.state -eq "running" }).Count -eq 0
        } | Sort-Object { $_.Value.started } | Select-Object -First $toRemoveCount -ExpandProperty Name)
        foreach ($k in $doneRunsToRemove) {
            $fsm.runs.PSObject.Properties.Remove($k)
        }
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

function Write-Span {
    param(
        [string]$TraceId,
        [string]$SpanType,
        [string]$Phase,
        [string]$Agent = "",
        [datetime]$StartTime,
        [datetime]$EndTime,
        [string]$Status
    )
    $spansFile = "$ResultsDir\spans-$TraceId.json"
    $spans = @()
    if (Test-Path $spansFile) {
        try { $spans = @(Get-Content $spansFile -Raw | ConvertFrom-Json) } catch { $spans = @() }
    }
    $span = [PSCustomObject]@{
        span_id    = [guid]::NewGuid().ToString("N").Substring(0, 8)
        trace_id   = $TraceId
        span_type  = $SpanType
        phase      = $Phase
        agent      = $Agent
        start_time = $StartTime.ToString("yyyy-MM-ddTHH:mm:ss")
        end_time   = $EndTime.ToString("yyyy-MM-ddTHH:mm:ss")
        duration_s = [int]($EndTime - $StartTime).TotalSeconds
        status     = $Status
    }
    $spans += $span
    try {
        $spans | ConvertTo-Json -Depth 3 | Set-Content $spansFile -Encoding UTF8
    } catch { Write-Log "[Span] Write failed: $_" }
}

# ============================================
# Multi-Backend Model Selection Functions
# ============================================

function ConvertFrom-YamlViapy {
    param([string]$YamlPath)
    try {
        $json = uv run --project $AgentDir python -c @"
import json, sys
try:
    import yaml
    with open(r'$YamlPath', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    print(json.dumps(data, ensure_ascii=False))
except Exception as e:
    sys.exit(1)
"@
        return $json | ConvertFrom-Json
    } catch {
        return $null
    }
}

# ADR-015：從 config/timeouts.yaml 載入 timeout（覆蓋預設，失敗時保留上方 hardcoded）
$timeoutsPath = Join-Path $AgentDir "config\timeouts.yaml"
if (Test-Path $timeoutsPath) {
    try {
        $ty = ConvertFrom-YamlViapy -YamlPath $timeoutsPath
        if ($ty -and $ty.todoist_team) {
            $tt = $ty.todoist_team
            if ($tt.phase1_timeout) { $Phase1TimeoutSeconds = [int]$tt.phase1_timeout }
            if ($tt.phase3_timeout) { $Phase3TimeoutSeconds = [int]$tt.phase3_timeout }
            if ($tt.phase2_timeout_by_task) {
                $byTask = $tt.phase2_timeout_by_task
                $AutoTaskTimeoutOverride = @{}
                $byTask.PSObject.Properties | ForEach-Object { $AutoTaskTimeoutOverride[$_.Name] = [int]$_.Value }
            }
        }
    } catch {
        # 保留腳本上方定義的預設值
    }
}

function Get-TaskBackend {
    param([string]$TaskKey)
    $default = @{ type = "claude_code"; cli_flag = ""; model = ""; reason = "default" }
    try {
        # 讀 frequency-limits.yaml（含合併後的模型選擇規則）
        $selPath = "$AgentDir\config\frequency-limits.yaml"
        if (-not (Test-Path $selPath)) { return $default }
        $sel = ConvertFrom-YamlViapy -YamlPath $selPath
        if (-not $sel) { return $default }

        # 決定後端名稱
        $backendName = "claude_sonnet"
        foreach ($bName in @("claude_sonnet45","claude_haiku","codex_exec","codex_standard","openrouter_standard","openrouter_research")) {
            $rules = $sel.task_rules.$bName
            if ($rules -and ($rules -contains $TaskKey)) {
                $backendName = $bName
                break
            }
        }

        $bCfg = $sel.backends.$backendName

        # codex_exec / codex_standard：偵測安裝（訂閱制不需 API Key）
        if ($backendName -in @("codex_exec","codex_standard")) {
            if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
                Write-Log "[ModelSelect] WARN: codex not installed, fallback -> openrouter_research ($TaskKey)"
                $backendName = "openrouter_research"
                $bCfg = $sel.backends.openrouter_research
            }
        }

        # openrouter_*：偵測 API Key
        if ($backendName -like "openrouter*" -and -not $env:OPENROUTER_API_KEY) {
            Write-Log "[ModelSelect] WARN: OPENROUTER_API_KEY not set, fallback -> claude_haiku ($TaskKey)"
            $backendName = "claude_haiku"
            $bCfg = $sel.backends.claude_haiku
        }

        # 讀 token_level（供呼叫方查詢）
        $tokenLevel = "normal"
        $tokenPath = "$AgentDir\state\token-usage.json"
        if (Test-Path $tokenPath) {
            try {
                $tu = Get-Content $tokenPath -Raw | ConvertFrom-Json
                $_tdKey = (Get-Date).ToString("yyyy-MM-dd")
                $est = [long]($tu.daily.$_tdKey.estimated_tokens ?? $tu.estimated_tokens ?? 0)
                $thresholds = $sel.token_thresholds
                if ($est -ge [long]$thresholds.emergency) { $tokenLevel = "emergency" }
                elseif ($est -ge [long]$thresholds.critical) { $tokenLevel = "critical" }
                elseif ($est -ge [long]$thresholds.warn) { $tokenLevel = "warn" }
            } catch {}
        }

        $liveWs = $false
        if ($backendName -in @("codex_exec","codex_standard")) {
            $lwTasks = $sel.codex.live_websearch_tasks
            $liveWs = ($lwTasks -and ($lwTasks -contains $TaskKey))
        }

        Write-Log "[ModelSelect] $TaskKey -> $backendName (token_level=$tokenLevel)"
        return @{
            type         = $bCfg.type ?? "claude_code"
            backend      = $backendName
            cli_flag     = $bCfg.cli_flag ?? ""
            model        = $bCfg.model ?? ""
            model_flag   = $bCfg.model_flag ?? ""   # Codex -m <model> 旗標
            live_ws      = $liveWs
            token_level  = $tokenLevel
            sel_config   = $sel
            reason       = "frequency-limits.yaml rule"
        }
    } catch {
        Write-Log "[ModelSelect] ERROR in Get-TaskBackend: $_ -> fallback default"
        return $default
    }
}

function Start-CodexJob {
    param(
        [string]$TaskKey,
        [string]$PromptContent,
        [bool]$LiveWebSearch = $false,
        [string]$TraceId = "",
        [string]$AgentName = "",
        [string]$ModelFlag = ""   # 例如 "-m gpt-5.4" 或 "" (使用 Codex 預設)
    )
    $codexCmd = "codex exec --full-auto"
    if ($ModelFlag) { $codexCmd += " $ModelFlag" }
    # codex exec 在 pipe prompt 時會把 --search 當成 [PROMPT] 導致參數錯誤；即時 WebSearch 改由 ~/.codex/config.toml 的 features.web_search_request 或執行時 --enable web_search_request 啟用
    # if ($LiveWebSearch) { $codexCmd += " --search" }
    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($prompt, $cmd, $traceId, $agentName, $dir)
        $env:CLAUDE_TEAM_MODE   = "1"
        $env:DIGEST_TRACE_ID    = $traceId
        $env:AGENT_PHASE        = "2"
        $env:AGENT_NAME         = $agentName
        Set-Location $dir
        $fullPrompt = "請以正體中文輸出。`n`n$prompt"
        $result = $fullPrompt | & cmd /c "$cmd" 2>&1
        $result
    } -ArgumentList $PromptContent, $codexCmd, $TraceId, $AgentName, $AgentDir
    return $job
}

function Start-OpenRouterJob {
    param(
        [string]$TaskKey,
        [string]$PromptContent,
        [string]$TraceId = "",
        [string]$AgentName = ""
    )
    $runnerPath = "$AgentDir\tools\agentic-openrouter-runner.js"
    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($prompt, $runner, $traceId, $agentName, $orKey, $dir)
        $env:OPENROUTER_API_KEY = $orKey
        $env:CLAUDE_TEAM_MODE   = "1"
        $env:DIGEST_TRACE_ID    = $traceId
        $env:AGENT_PHASE        = "2"
        $env:AGENT_NAME         = $agentName
        Set-Location $dir
        $result = $prompt | node $runner 2>&1
        $result
    } -ArgumentList $PromptContent, $runnerPath, $TraceId, $AgentName, $env:OPENROUTER_API_KEY, $AgentDir
    return $job
}

# ============================================
# Start execution
# ============================================
$startTime = Get-Date

# ─── 載入環境變數（系統環境變數優先，其次從 .env 讀取）───
$envFile = "$AgentDir\.env"
$todoistTokenSource = "none"

# TODOIST_API_TOKEN（排程執行時依賴 run-with-env.ps1 或此處從 .env 載入）
if (-not $env:TODOIST_API_TOKEN) {
    if (Test-Path $envFile) {
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        $envRaw = [System.IO.File]::ReadAllText($envFile, $utf8NoBom)
        $envLine = ($envRaw -split "`r?`n" | Where-Object { $_ -match '^TODOIST_API_TOKEN=' } | Select-Object -First 1)
        if ($envLine) {
            $todoistToken = ($envLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
            if ($todoistToken.Length -gt 0 -and $todoistToken[0] -eq [char]0xFEFF) { $todoistToken = $todoistToken.TrimStart([char]0xFEFF) }
            [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $todoistToken, "Process")
            $todoistTokenSource = ".env"
            Write-Host "[Token] TODOIST_API_TOKEN loaded from .env"
        }
        else {
            Write-Host "[WARN] TODOIST_API_TOKEN not found in .env"
            $todoistToken = ""
        }
    }
    else {
        Write-Host "[WARN] .env not found at $envFile , TODOIST_API_TOKEN may be missing"
        $todoistToken = ""
    }
}
else {
    $todoistToken = $env:TODOIST_API_TOKEN
    $todoistTokenSource = "environment"
    Write-Host "[Token] TODOIST_API_TOKEN loaded from environment"
}
Write-Log "[Token] TODOIST_API_TOKEN source=$todoistTokenSource (loaded)"

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

# Codex CLI 訂閱制：不需要 API Key，由使用者帳號授權
# （已移除 CODEX_API_KEY 檢查）

# OPENROUTER_API_KEY（OpenRouter 維護/研究任務後端）
if (-not $env:OPENROUTER_API_KEY) {
    if (Test-Path $envFile) {
        $orLine = Get-Content $envFile | Where-Object { $_ -match '^OPENROUTER_API_KEY=' }
        if ($orLine) {
            $orKey = ($orLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", $orKey, "Process")
            Write-Host "[Token] OPENROUTER_API_KEY loaded from .env"
        } else {
            Write-Host "[WARN] OPENROUTER_API_KEY not set -> openrouter tasks will fallback to claude_haiku"
        }
    }
}

# ─── 生產環境安全策略 ───
# 若未設定則預設 strict（排程器執行環境），手動執行可覆蓋
$validPresets = @("strict", "normal", "permissive")
if (-not (Test-Path Env:HOOK_SECURITY_PRESET)) {
    $env:HOOK_SECURITY_PRESET = "strict"
} elseif ($env:HOOK_SECURITY_PRESET -notin $validPresets) {
    Write-Log "[Security] WARN: Invalid HOOK_SECURITY_PRESET='$($env:HOOK_SECURITY_PRESET)', falling back to 'strict'"
    $env:HOOK_SECURITY_PRESET = "strict"
}
Write-Log "[Security] HOOK_SECURITY_PRESET = $($env:HOOK_SECURITY_PRESET)"

# Generate trace ID for distributed tracing
$traceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
Write-Log "=== Todoist Agent Team start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Log "Trace ID: $traceId"
Write-Log "Mode: parallel (Phase 1 x1 + Phase 2 xN + Phase 3 x1)"
Write-Log "[PID] $PID"

# ─── Instance Lock（防止與上一班排程重疊，避免 results/ 衝突與日誌截斷）───
$TodoistTeamLockFile = "$AgentDir\state\run-todoist-agent-team.lock"
if (Test-Path $TodoistTeamLockFile) {
    $lockContent = Get-Content $TodoistTeamLockFile -Raw -ErrorAction SilentlyContinue
    $lockPid = ($lockContent -split "`n")[0].Trim()
    $existingProcess = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
        Write-Log "[SKIP] Another instance is running (PID $lockPid). Exiting to avoid overlap."
        exit 0
    }
    Write-Log "[WARN] Stale lock found (PID $lockPid not running). Removing."
    Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue
}
$PID | Set-Content $TodoistTeamLockFile -Encoding UTF8
try {
    Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue
    } | Out-Null
} catch {
    Write-Log "[WARN] Could not register exit handler for lock cleanup: $_"
}

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
# Phase 1a: ToolOrchestra 前置簡易分類（P3-C）
# 用 Groq Llama 8B 快速判斷今日任務複雜度
# 若任務簡單（pure formatting / status update），可略過 Claude 深度分析
# ============================================
$invokeRouter = "$AgentDir\tools\invoke-llm.ps1"
if (Test-Path $invokeRouter) {
    try {
        $todayTasksHint = "Todoist 任務規劃請求，日期=$((Get-Date -Format 'yyyy-MM-dd'))"
        $routerResult = & $invokeRouter -TaskType "todoist_query_simple" -InputText $todayTasksHint -DryRun 2>$null
        if ($routerResult -and $routerResult.provider -eq "groq") {
            Write-Log "[P3-C] ToolOrchestra: todoist_query_simple → Groq route confirmed (dry-run)"
        }
    } catch {
        Write-Log "[P3-C] ToolOrchestra 前置分類略過：$($_.Exception.Message)"
    }
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

# ── Step 6: Phase 1 Token Budget 控制 ──
# 讀取今日 token 用量，決定 Phase 1 模型旗標與 max-tokens
$phase1ModelFlag = ""
$phase1MaxTokens = 80000   # 預設：防止單次超限
$_tokenPath = "$AgentDir\state\token-usage.json"
$_selPath   = "$AgentDir\config\frequency-limits.yaml"
if ((Test-Path $_tokenPath) -and (Test-Path $_selPath)) {
    try {
        $tu  = Get-Content $_tokenPath -Raw | ConvertFrom-Json
        $sel = ConvertFrom-YamlViapy -YamlPath $_selPath
        $_tdKey = (Get-Date).ToString("yyyy-MM-dd")
        $est = [long]($tu.daily.$_tdKey.estimated_tokens ?? $tu.estimated_tokens ?? 0)
        if ($sel -and $sel.token_thresholds) {
            if ($est -ge [long]$sel.token_thresholds.emergency) {
                $phase1ModelFlag  = "--model claude-haiku-4-5"
                $phase1MaxTokens  = [int]$sel.phase_overrides.emergency.phase1_max_tokens
                Write-Log "[Phase1] token_level=emergency -> haiku + max-tokens=$phase1MaxTokens"
            } elseif ($est -ge [long]$sel.token_thresholds.critical) {
                $phase1ModelFlag  = "--model claude-haiku-4-5"
                $phase1MaxTokens  = [int]$sel.phase_overrides.critical.phase1_max_tokens
                Write-Log "[Phase1] token_level=critical -> haiku + max-tokens=$phase1MaxTokens"
            } elseif ($est -ge [long]$sel.token_thresholds.warn) {
                Write-Log "[Phase1] token_level=warn -> default model + max-tokens=$phase1MaxTokens"
            } else {
                Write-Log "[Phase1] token_level=normal -> default model + max-tokens=$phase1MaxTokens"
            }
        }
    } catch {
        Write-Log "[Phase1] WARN: token budget check failed: $_"
    }
}

while ($phase1Attempt -le $MaxPhase1Retries) {
    if ($phase1Attempt -gt 0) {
        $p1Backoff = 30 + (Get-Random -Minimum 0 -Maximum 10)
        Write-Log "[Phase1] Retry attempt $($phase1Attempt + 1) in ${p1Backoff}s..."
        Start-Sleep -Seconds $p1Backoff
    }

    Write-Log "[Phase1] Running query agent (attempt $($phase1Attempt + 1))..."

    try {
        $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
            param($prompt, $logDir, $timestamp, $traceId, $apiToken, $modelFlag)

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
            $claudeArgs = @("-p", "--allowedTools", "Read,Bash,Write")
            if ($modelFlag) { $claudeArgs += ($modelFlag -split '\s+') }
            $output = $prompt | claude @claudeArgs 2>$stderrFile

            # 執行成功且 stderr 為空 → 刪除
            if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                $stderrSize = (Get-Item $stderrFile).Length
                if ($stderrSize -eq 0) {
                    Remove-Item $stderrFile -Force
                }
            }

            return $output
        } -ArgumentList $queryContent, $LogDir, $Timestamp, $traceId, $todoistToken, $phase1ModelFlag

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

        Write-Log "[Phase1] Waiting for main query job (timeout ${Phase1TimeoutSeconds}s)..."
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
# Level 3-A: Phase 1 span
Write-Span -TraceId $traceId -SpanType "phase" -Phase "phase1" `
    -StartTime $phase1Start -EndTime $phase1End `
    -Status $(if ($phase1Success) { "ok" } else { "failed" })

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
    # 多任務並行時加緩衝，避免最後寫檔的 agent 被逾時強停導致「Phase 2 結果缺失」
    if ($plan.tasks.Count -gt 1) {
        $multiTaskBuffer = [Math]::Min(120, [int]($maxTaskTimeout * 0.15))
        $Phase2TimeoutSeconds += $multiTaskBuffer
        Write-Log "[Dynamic] +${multiTaskBuffer}s buffer for $($plan.tasks.Count) parallel tasks"
    }
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
                "podcastcreate"      = "podcast_create"
                "podcast"            = "podcast_create"
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

            # ── Multi-backend routing (Step 5) ──
            $backend = Get-TaskBackend -TaskKey $taskKey
            Write-Log "[ModelSelect] $taskKey -> backend=$($backend.backend) type=$($backend.type) token_level=$($backend.token_level)"

            if ($backend.type -eq "codex") {
                $job = Start-CodexJob -TaskKey $taskKey -PromptContent $promptContent `
                    -LiveWebSearch $backend.live_ws -TraceId $traceId -AgentName $agentName `
                    -ModelFlag $backend.model_flag
            } elseif ($backend.type -eq "openrouter_runner") {
                $job = Start-OpenRouterJob -TaskKey $taskKey -PromptContent $promptContent `
                    -TraceId $traceId -AgentName $agentName
            } else {
                # claude_code: 原有 Start-Job，注入可選的 cli_flag（如 --model claude-haiku-4-5）
                $cliFlag = $backend.cli_flag
                $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                    param($prompt, $agentName, $logDir, $timestamp, $traceId, $apiToken, $cliFlag)

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
                    # 動態組合 claude 參數（支援 --model 旗標注入）
                    $claudeArgs = @("-p", "--allowedTools", "Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch")
                    if ($cliFlag) { $claudeArgs += ($cliFlag -split '\s+') }
                    $output = $prompt | claude @claudeArgs 2>$stderrFile

                    if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                        $stderrSize = (Get-Item $stderrFile).Length
                        if ($stderrSize -eq 0) { Remove-Item $stderrFile -Force }
                    }
                    return $output
                } -ArgumentList $promptContent, $agentName, $LogDir, $Timestamp, $traceId, $todoistToken, $cliFlag
            }

            $job | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $agentName -Force
            $job | Add-Member -NotePropertyName "BackendName" -NotePropertyValue $backend.backend -Force
            $phase2Jobs += $job
            Write-Log "[Phase2] Started: $agentName ($taskName) backend=$($backend.backend) (Job $($job.Id))"
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
        # 計算 per-job 耗時（使用 PS Job 的 PSBeginTime/PSEndTime）
        $jobElapsed = if ($job.PSBeginTime -and $job.PSEndTime) {
            [int]($job.PSEndTime - $job.PSBeginTime).TotalSeconds
        } else { $null }
        Write-Log "[Phase2] $agentName completed$(if ($jobElapsed) { " (${jobElapsed}s)" })"

        # Codex / OpenRouter 後端：若 Agent 未產出有效結果檔，寫入結構化失敗檔（避免整段 stdout 寫入導致「結果檔損壞」）
        $needFallback = $job.BackendName -in @("codex_exec", "codex_standard", "openrouter_research", "openrouter_standard")
        if ($needFallback -and $output) {
            $tkKey = $agentName -replace '^auto-', ''
            $rFile = "$AgentDir\results\todoist-auto-$tkKey.json"
            $fullOutput = ($output -join "`n")
            $doFallback = $false
            if (-not (Test-Path $rFile)) {
                $doFallback = $true
            } elseif ((Get-Item $rFile).Length -lt 500) {
                $doFallback = $true
            } else {
                # 已有檔案且足夠大：檢查是否為有效結構（含 type/agent + status），避免覆蓋
                try {
                    $existing = Get-Content $rFile -Raw -Encoding UTF8 | ConvertFrom-Json
                    if (-not $existing.type -and -not $existing.agent) { $doFallback = $true }
                    elseif (-not $existing.status) { $doFallback = $true }
                } catch { $doFallback = $true }
            }
            if ($doFallback) {
                # 僅寫入結構化失敗 + 短預覽（上限 2000 字），避免 10 萬字 stdout 導致 Phase 3 判定「結果檔損壞」
                $previewLen = [Math]::Min(2000, [Math]::Max(0, $fullOutput.Length))
                $stdoutPreview = if ($previewLen -gt 0) { $fullOutput.Substring(0, $previewLen) } else { "" }
                if ($fullOutput.Length -gt 2000) { $stdoutPreview += "`n... [truncated, total $($fullOutput.Length) chars]" }
                $fallback = @{
                    agent   = "todoist-auto-$tkKey"
                    type    = $tkKey
                    status  = "failed"
                    reason  = "result_file_missing_or_invalid"
                    summary = "後端未產出有效結果檔，stdout 已截斷預覽"
                    backend_stdout_preview = $stdoutPreview
                    backend = $job.BackendName
                }
                if ($jobElapsed) { $fallback.elapsed_seconds = $jobElapsed }
                $fallback | ConvertTo-Json -Depth 4 |
                    Set-Content -Path $rFile -Encoding UTF8 -Force
                Write-Log "[Phase2] ${agentName} result file補寫 (structured failure, stdout_preview=${previewLen} chars, total=$($fullOutput.Length), ${jobElapsed}s)"
            } else {
                # 已有有效結構：若 status=in_progress 代表任務中途 context 耗盡 → 升級為 partial_success
                try {
                    $existing = Get-Content $rFile -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($existing.status -eq "in_progress") {
                        $existing.status  = "partial_success"
                        $existing.summary = if ($existing.summary -and $existing.summary -ne "研究進行中") { $existing.summary } else { "研究已完成但最終步驟未執行（context 耗盡）" }
                        $existing | ConvertTo-Json -Depth 4 |
                            Set-Content -Path $rFile -Encoding UTF8 -Force
                        Write-Log "[Phase2] ${agentName} result file: in_progress → partial_success (context 耗盡，研究內容已產出)"
                    }
                } catch { <# 讀取失敗則保留原檔案不動 #> }
            }
        }
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
# Level 3-A: per-agent spans + Phase 2 span
foreach ($agentKey in $sections.Keys) {
    if ($sections[$agentKey] -ne "pending") {
        Write-Span -TraceId $traceId -SpanType "agent" -Phase "phase2" -Agent $agentKey `
            -StartTime $phase2Start -EndTime (Get-Date) `
            -Status ($sections[$agentKey] -ne $null ? $sections[$agentKey] : "unknown")
    }
}
Write-Span -TraceId $traceId -SpanType "phase" -Phase "phase2" `
    -StartTime $phase2Start -EndTime (Get-Date) `
    -Status $(if ($phase2FailCount -eq 0) { "ok" } else { "failed" })

# ── Pre-Phase-3：檢查 plan_type=tasks 的結果檔是否齊全 ──
if ($plan.plan_type -eq "tasks" -and $null -ne $plan.tasks -and $plan.tasks.Count -gt 0) {
    $missingResults = @()
    for ($rank = 1; $rank -le $plan.tasks.Count; $rank++) {
        $resultPath = "$ResultsDir\todoist-result-$rank.json"
        if (-not (Test-Path $resultPath)) {
            $taskContent = $plan.tasks[$rank - 1].content
            $shortContent = if ($taskContent.Length -gt 40) { $taskContent.Substring(0, 40) + "…" } else { $taskContent }
            $missingResults += "task-$rank (todoist-result-$rank.json)"
            $sectionKey = "task-$rank"
            $jobState = $sections[$sectionKey]
            Write-Log "[Phase2] Missing result file: todoist-result-$rank.json — job state=$jobState — content: $shortContent" "WARN"
        }
    }
    if ($missingResults.Count -gt 0) {
        Write-Log "[Phase2] Missing result files: $($missingResults -join ', ') — Phase 3 will mark these tasks as failed (結果缺失)" "WARN"
    }
}

# ── Pre-Phase-3：Auto-task 失敗追蹤（plan_type=auto）──
# 比對 selected_tasks 與實際產出的結果檔，記錄到 state/failed-auto-tasks.json
# 使用正規化 key 作為 result 檔名與 task_key，避免 selected_tasks 為物件時被轉成 @{key=...} 導致永遠 result_file_missing
if ($plan.plan_type -eq "auto" -and
    $null -ne $plan.auto_tasks -and
    $null -ne $plan.auto_tasks.selected_tasks) {
    foreach ($item in $plan.auto_tasks.selected_tasks) {
        $normalizedKey = Get-NormalizedAutoTaskKey -Item $item
        $rawKey = if ($null -ne $item -and $item.PSObject.Properties['key']) { $item.key } else { $normalizedKey }
        $resultPath = "$ResultsDir\todoist-auto-$normalizedKey.json"
        if (Test-Path $resultPath) {
            Update-FailedAutoTasks -TaskKey $normalizedKey -Succeeded $true
        } else {
            $agentSectionKey = "auto-$rawKey"
            $jobFailReason = if ($sections[$agentSectionKey] -eq "timeout") { "timeout" } else { "result_file_missing" }
            Update-FailedAutoTasks -TaskKey $normalizedKey -Reason $jobFailReason -Succeeded $false
        }
    }
}

# ── Step 9A: Backend 分布日誌 + 研究品質評分 ──
$backendDist = @{}
foreach ($j in $phase2Jobs) {
    $bn = $j.BackendName ?? "claude_code"
    $backendDist[$bn] = ($backendDist[$bn] ?? 0) + 1
}
$distStr = ($backendDist.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "
Write-Log "[ModelSelect] backend 分布: $distStr"

# 研究品質評分（針對研究類任務）
$researchTasks = @("shurangama","jingtu","jiaoguangzong","fahua","ai_sysdev","ai_workflow_github","ai_github_research","ai_deep_research","tech_research")
$qualityScores = @()
$scoreScript = "$AgentDir\tools\score-research-quality.py"
if (Test-Path $scoreScript) {
    foreach ($rTask in $researchTasks) {
        $rFile = "$AgentDir\results\todoist-auto-$rTask.json"
        if (Test-Path $rFile) {
            try {
                $scoreOut = uv run --project $AgentDir python $scoreScript $rFile 2>$null
                $scoreJson = $scoreOut | Where-Object { $_.TrimStart().StartsWith('{') } | Select-Object -Last 1
                if ($scoreJson) {
                    $scoreData = $scoreJson | ConvertFrom-Json
                    $qualityScores += @{ task = $rTask; score = $scoreData.score }
                }
            } catch { Write-Log "[QualityScore] WARN: scoring failed for $rTask : $_" }
        }
    }
    if ($qualityScores.Count -gt 0) {
        $avgScore = [int](($qualityScores | ForEach-Object { $_.score } | Measure-Object -Average).Average)
        $scoreStr = ($qualityScores | ForEach-Object { "$($_.task)=$($_.score)" }) -join ", "
        Write-Log "[QualityScore] $scoreStr avg=$avgScore"
    }
}

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

# ── P5-A：Phase 3 前 done_cert 驗證 ─────────────────────────────────────────
$doneCertScript = "$AgentDir\tools\agent_pool\done_cert.py"
if (Test-Path $doneCertScript) {
    Write-Log "[Phase3-Pre] Verifying done_certs before assembly..."
    try {
        $certResult = uv run --project $AgentDir python $doneCertScript --verify-all 2>&1
        $certJson = $certResult | Where-Object { $_ -match '^\{' } | Select-Object -Last 1
        if ($certJson) {
            $cert = $certJson | ConvertFrom-Json
            $passed = $cert.passed
            $total  = $cert.total
            $failed = $cert.failed
            Write-Log "[Phase3-Pre] done_cert: $passed/$total passed, $failed failed"
            if ($failed -gt 0) {
                $ratio = if ($total -gt 0) { [math]::Round($passed / $total, 2) } else { 1.0 }
                if ($ratio -lt 0.6) {
                    Write-Log "[Phase3-Pre] WARNING: success_ratio=$ratio < 0.6 (min_success_ratio), some results may be missing"
                }
                $certResult | ForEach-Object { Write-Log "  [cert] $_" }
            }
        }
    } catch {
        Write-Log "[Phase3-Pre] done_cert check skipped: $($_.Exception.Message)"
    }
}
# ─────────────────────────────────────────────────────────────────────────────

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
        # Step 6: Phase 3 token budget（使用與 Phase 1 相同的 token_level）
        $phase3Args = @("-p", "--allowedTools", "Read,Bash,Write")
        if ($phase1ModelFlag) { $phase3Args += ($phase1ModelFlag -split '\s+') }
        $output = $assembleContent | claude @phase3Args 2>$stderrFile

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

# Level 3-A: Phase 3 + Overall span
$runEnd = Get-Date
Write-Span -TraceId $traceId -SpanType "phase" -Phase "phase3" `
    -StartTime $phase3StartOuter -EndTime $runEnd `
    -Status $(if ($phase3Success) { "ok" } else { "failed" })
Write-Span -TraceId $traceId -SpanType "phase" -Phase "overall" `
    -StartTime $startTime -EndTime $runEnd `
    -Status $(if ($phase3Success) { "ok" } else { "failed" })

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

# Clean up spans files older than 7 days
Get-ChildItem "$ResultsDir\spans-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force

# Clean up stale loop-state files older than 48 hours
$loopStateFiles = Get-ChildItem "$AgentDir\state\loop-state-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-48) }
if ($loopStateFiles) {
    $loopStateFiles | Remove-Item -Force
    Write-Log "[Cleanup] Removed $($loopStateFiles.Count) stale loop-state files (>48h)"
}

# Clean up stale stop-alert files older than 7 days
$stopAlertFiles = Get-ChildItem "$AgentDir\state\stop-alert-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
if ($stopAlertFiles) {
    $stopAlertFiles | Remove-Item -Force
    Write-Log "[Cleanup] Removed $($stopAlertFiles.Count) stale stop-alert files (>7d)"
}

# Clean up stale results files older than 7 days (exclude spans, handled above)
$staleResults = Get-ChildItem "$ResultsDir\*" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notlike "spans-*" -and $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
if ($staleResults) {
    $staleResults | Remove-Item -Force
    Write-Log "[Cleanup] Removed $($staleResults.Count) stale result files (>7d)"
}
