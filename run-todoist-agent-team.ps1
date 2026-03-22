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

# ADR-20260312-015: 優先從 config/timeouts.yaml 讀取 per-task timeout（動態載入）
$TimeoutFromConfig = @{}
try {
    $timeoutYamlRaw = uv run --project $AgentDir python -c @"
import yaml, json
with open('config/timeouts.yaml', 'r', encoding='utf-8') as f:
    c = yaml.safe_load(f)
print(json.dumps(c.get('todoist_team', {}).get('phase2_timeout_by_task', {})))
"@
    if ($timeoutYamlRaw) {
        $timeoutJson = ConvertFrom-Json $timeoutYamlRaw
        $timeoutJson.PSObject.Properties | ForEach-Object { $TimeoutFromConfig[$_.Name] = $_.Value }
    }
} catch {
    Write-Host "  [WARN] 無法從 config/timeouts.yaml 讀取 task timeout，使用 hardcoded fallback" -ForegroundColor Yellow
}

# Per-key timeout override（秒）— 優先級高於群組預設
# 注意：key 必須與 config/frequency-limits.yaml 一致（底線命名）
# ADR-20260312-015: 以下為 fallback 值，config/timeouts.yaml 有對應 key 時會被覆蓋
$AutoTaskTimeoutOverride = @{
    # === 研究類（WebSearch/WebFetch + KB 匯入）===
    "ai_github_research"     = 900   # GitHub WebSearch×3 + WebFetch + KB 匯入（原缺失回落 600s 導致超時）
    "ai_workflow_github"     = 720   # GitHub workflow 研究 + KB 匯入
    "ai_deep_research"       = 720   # 4 階段 WebFetch
    "unsloth_research"       = 720   # WebSearch + WebFetch + KB 匯入
    "tech_research"          = 2600  # 讀 history + WebSearch×3 + WebFetch×4 + KB 匯入
    # === 佛學研究類（WebFetch 多章 + KB 匯入）===
    "shurangama"             = 1200  # 楞嚴經重型主題（如五十陰魔）偶發超過 900s
    "jiaoguangzong"          = 1200  # 教觀綱宗會通型主題偶發超過 900s
    "fahua"                  = 900   # 法華多章 + KB 匯入
    "jingtu"                 = 900   # 淨土多章 + KB 匯入
    # === 系統類（重 context，含 sub-agent）===
    "skill_audit"            = 720   # sub-agent 掃描 26 SKILL.md + KB 搜尋
    "system_insight"         = 720   # sub-agent 分析 logs/state + 更新 system-insight.json
    "log_audit"              = 720   # sub-agent 讀 10+ log + 分析修正 + KB 匯入
    "qa_optimize"            = 720   # WebSearch CVE + Grep 掃描 + 程式碼修改
    "self_heal"              = 1200  # 多步驟修復 + ntfy（延長：720s 曾超時，2026-03-12）
    "arch_evolution"         = 900   # 讀 improvement-backlog + context/*.json + 架構決策
    "chatroom_optimize"      = 480   # sub-agent log 分析 + routing.yaml 調整
    # === 創意類 ===
    "creative_game"          = 900   # sync-games.ps1 npm build 最長 ~15 min
    "creative_game_optimize" = 900
    # === 長時媒體類（TTS + 上傳）===
    "podcast_create"         = 2400  # 腳本生成 + TTS(40段) + concat + R2 上傳
    "podcast_jiaoguangzong"  = 2400  # 教觀綱宗 Podcast：30-40 輪 TTS + concat + R2 上傳
    # === 補齊 fallback（config/timeouts.yaml 有值時會被覆蓋）===
    "ai_smart_city"          = 600
    "ai_sysdev"              = 600
    "git_push"               = 600
    "skill_forge"            = 900
    "github_scout"           = 600
    "future_plan_optimize"   = 900   # 未來計畫待辦優化：KB + MD 寫回
    "kb_insight_evaluation"  = 1200  # 洞察報告擇 3 項研究 + 執行方案 + improvement-backlog
    "workflow_forge"         = 900   # Workflow 鑄造廠：流程標準化 + 輸出 Schema + 一致性
    "insight_briefing"       = 900   # 深度研究洞察簡報：多 Skill 串接 + 簡報產出 + KB + ntfy
}

# 合併：config/timeouts.yaml 優先，hardcoded 為 fallback
$TimeoutFromConfig.Keys | ForEach-Object {
    $AutoTaskTimeoutOverride[$_] = $TimeoutFromConfig[$_]
}
if ($TimeoutFromConfig.Count -gt 0) {
    Write-Host "  [INFO] Task timeout 從 config/timeouts.yaml 載入 $($TimeoutFromConfig.Count) 個 key" -ForegroundColor Cyan
}

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$LogDir\structured" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\context" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\cache" | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

# ─── Loop-State 自動清理（保留 3 天，防止檔案膨脹）───
$loopStatePattern = Join-Path $AgentDir "state\loop-state-*.json"
$loopStateFiles = Get-ChildItem $loopStatePattern -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-3) }
if ($loopStateFiles.Count -gt 0) {
    $loopStateFiles | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "[CLEANUP] Removed $($loopStateFiles.Count) stale loop-state files (>3 days old)"
}

# ADR-036: context-compression hint 清理（30 分鐘 TTL）
Get-ChildItem "$AgentDir\state\context-compression-hint-*.txt" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddMinutes(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

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

    # 同步 failure_taxonomy（確保 total 與 taxonomy 一致）
    $taxonomyDefs = @{
        timeout        = @{ blast_radius = "single_task"; description = "Agent 或 API 呼叫超時" }
        phase_failure  = @{ blast_radius = "phase"; description = "Phase 執行失敗（LLM 錯誤、結果檔缺失）" }
        api_error      = @{ blast_radius = "dependent_tasks"; description = "外部 API 不可用（KB、Todoist、ntfy）" }
        circuit_open   = @{ blast_radius = "all_tasks"; description = "斷路器開啟導致任務跳過" }
        parse_error    = @{ blast_radius = "single_task"; description = "結果 JSON 格式錯誤或 schema 不符" }
        quota_exceeded = @{ blast_radius = "all_tasks"; description = "Token 或 API 配額耗盡" }
        unknown        = @{ blast_radius = "unknown"; description = "未分類失敗" }
    }
    if (-not $stats.failure_taxonomy) {
        $stats | Add-Member -NotePropertyName "failure_taxonomy" -NotePropertyValue ([PSCustomObject]@{}) -Force
    }
    foreach ($ft in $taxonomyDefs.Keys) {
        $cnt = $stats.total.$ft
        if ($null -eq $cnt) { $cnt = 0 }
        $lastOcc = $null
        # 從 daily 找最後出現日期
        $dailyDates = @($stats.daily.PSObject.Properties.Name | Sort-Object -Descending)
        foreach ($d in $dailyDates) {
            $dVal = $stats.daily.$d.$ft
            if ($null -ne $dVal -and $dVal -gt 0) { $lastOcc = $d; break }
        }
        $def = $taxonomyDefs[$ft]
        $stats.failure_taxonomy | Add-Member -NotePropertyName $ft -NotePropertyValue ([PSCustomObject]@{
            count           = $cnt
            blast_radius    = $def.blast_radius
            last_occurrence = $lastOcc
            description     = $def.description
        }) -Force
    }

    # 只保留 30 天
    $cutoff = (Get-Date).AddDays(-30).ToString("yyyy-MM-dd")
    $oldKeys = @($stats.daily.PSObject.Properties.Name | Where-Object { $_ -lt $cutoff })
    foreach ($k in $oldKeys) {
        $stats.daily.PSObject.Properties.Remove($k)
    }

    $stats | Add-Member -NotePropertyName "schema_version" -NotePropertyValue 2 -Force
    $stats | Add-Member -NotePropertyName "updated" -NotePropertyValue (Get-Date -Format "yyyy-MM-ddTHH:mm:ss") -Force

    # 原子寫入（write-to-temp + rename）
    $tmpFile = "$statsFile.tmp"
    $stats | ConvertTo-Json -Depth 5 | Set-Content $tmpFile -Encoding UTF8
    Move-Item $tmpFile $statsFile -Force
}

function Repair-CompletedAutoTaskResultFile {
    param(
        [string]$TaskKey,
        [string]$AgentName,
        [string]$BackendName,
        [object[]]$Output,
        [string]$StdErrFile,
        [Nullable[int]]$JobElapsed
    )

    $resultFile = "$AgentDir\results\todoist-auto-$TaskKey.json"
    $fullOutput = if ($Output) { (@($Output) -join "`n").Trim() } else { "" }
    $stderrOutput = ""
    if ($StdErrFile -and (Test-Path $StdErrFile)) {
        try { $stderrOutput = (Get-Content -Path $StdErrFile -Raw -Encoding UTF8).Trim() } catch { $stderrOutput = "" }
    }

    $previewSource = if ($fullOutput) { $fullOutput } elseif ($stderrOutput) { $stderrOutput } else { "" }
    $previewLimit = 2000
    $preview = ""
    if ($previewSource) {
        $previewLen = [Math]::Min($previewLimit, $previewSource.Length)
        $preview = $previewSource.Substring(0, $previewLen)
        if ($previewSource.Length -gt $previewLimit) {
            $preview += "`n... [truncated, total $($previewSource.Length) chars]"
        }
    }

    $existing = $null
    $existingValid = $false
    if (Test-Path $resultFile) {
        try {
            $existing = Get-Content -Path $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $existingValid = (($existing.type -or $existing.agent -or $existing.task_key) -and $existing.status)
        } catch {
            $existing = $null
            $existingValid = $false
        }
    }

    if ($existingValid -and $existing.status -eq "in_progress") {
        $existing.status = "partial_success"
        if (-not $existing.summary -or $existing.summary -eq "研究進行中") {
            $existing.summary = "主要研究已完成，但最終結果檔未完整收尾，已由排程自動補記"
        }
        if ($JobElapsed) {
            $existing | Add-Member -NotePropertyName "duration_seconds" -NotePropertyValue $JobElapsed -Force
        }
        if ($preview) {
            $existing | Add-Member -NotePropertyName "backend_stdout_preview" -NotePropertyValue $preview -Force
        }
        $existing | ConvertTo-Json -Depth 6 |
            Set-Content -Path $resultFile -Encoding UTF8 -Force
        Write-Log "[Phase2] ${agentName} result file: in_progress -> partial_success (backend=$BackendName)"
        return
    }

    if ($existingValid) { return }

    $fallback = @{
        agent   = "todoist-auto-$TaskKey"
        type    = $TaskKey
        status  = if ($preview) { "partial_success" } else { "failed" }
        reason  = "result_file_missing_or_invalid"
        summary = if ($preview) {
            "Agent 已完成主要輸出，但未產出有效結果檔，已保留預覽"
        } else {
            "後端未產出有效結果檔，且無可用輸出"
        }
        backend = $BackendName
    }
    if ($JobElapsed) { $fallback.elapsed_seconds = $JobElapsed }
    if ($preview) { $fallback.backend_stdout_preview = $preview }

    $fallback | ConvertTo-Json -Depth 4 |
        Set-Content -Path $resultFile -Encoding UTF8 -Force
    Write-Log "[Phase2] ${agentName} result file補寫 (backend=$BackendName, status=$($fallback.status), preview=$($preview.Length) chars)"
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

        # 決定後端名稱（預設 cursor_cli；未列入 task_rules 的任務以此執行）
        $backendName = "cursor_cli"
        foreach ($bName in @("claude_opus46","claude_sonnet45","claude_haiku","codex_exec","codex_standard","openrouter_standard","openrouter_research","cursor_cli")) {
            $rules = $sel.task_rules.$bName
            if ($rules -and ($rules -contains $TaskKey)) {
                $backendName = $bName
                break
            }
        }

        $bCfg = $sel.backends.$backendName

        # codex_exec / codex_standard：偵測安裝（訂閱制不需 API Key）
        # 備援規則：非 cursor_cli 模型 → cursor_cli；cursor_cli → claude
        if ($backendName -in @("codex_exec","codex_standard")) {
            if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
                Write-Log "[ModelSelect] WARN: codex not installed, fallback -> cursor_cli ($TaskKey)"
                $backendName = "cursor_cli"
                $bCfg = $sel.backends.cursor_cli
            }
        }

        # openrouter_*：偵測 API Key
        # 備援規則：非 cursor_cli 模型 → cursor_cli；cursor_cli → claude
        if ($backendName -like "openrouter*" -and -not $env:OPENROUTER_API_KEY) {
            Write-Log "[ModelSelect] WARN: OPENROUTER_API_KEY not set, fallback -> cursor_cli ($TaskKey)"
            $backendName = "cursor_cli"
            $bCfg = $sel.backends.cursor_cli
        }

        # cursor_cli：偵測 agent 指令可用性
        if ($backendName -eq "cursor_cli") {
            if (-not (Get-Command agent -ErrorAction SilentlyContinue)) {
                Write-Log "[ModelSelect] WARN: 'agent' CLI not found, cursor_cli fallback -> claude_sonnet ($TaskKey)"
                $backendName = "claude_sonnet"
                $bCfg = $sel.backends.claude_sonnet
            } else {
                $taskFile = Join-Path $AgentDir "temp\cursor-cli-task-$TaskKey.md"
                if (-not (Test-Path $taskFile)) {
                    Write-Log "[ModelSelect] WARN: cursor_cli task file missing ($taskFile), fallback -> claude_sonnet ($TaskKey)"
                    $backendName = "claude_sonnet"
                    $bCfg = $sel.backends.claude_sonnet
                }
            }
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

        # 安全性：cli_flag 白名單驗證（防止 config 注入任意 CLI 旗標）
        $rawCliFlag = $bCfg.cli_flag ?? ""
        $allowedCliFlags = @(
            "",
            "--model claude-haiku-4-5",
            "--model claude-sonnet-4-5",
            "--model claude-opus-4-6"
        )
        if ($rawCliFlag -and ($rawCliFlag -notin $allowedCliFlags)) {
            Write-Log "[ModelSelect] WARNING: cli_flag '$rawCliFlag' not in whitelist, rejected -> empty"
            $rawCliFlag = ""
        }

        Write-Log "[ModelSelect] $TaskKey -> $backendName (token_level=$tokenLevel)"
        return @{
            type         = $bCfg.type ?? "claude_code"
            backend      = $backendName
            cli_flag     = $rawCliFlag
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
    $safeAgentName = if ($AgentName) { $AgentName } else { "codex-$TaskKey" }
    $stdoutFile = Join-Path $LogDir "$safeAgentName-stdout-$Timestamp.log"
    $stderrFile = Join-Path $LogDir "$safeAgentName-stderr-$Timestamp.log"
    $promptFile = Join-Path $LogDir "$safeAgentName-prompt-$Timestamp.txt"
    $runnerFile = Join-Path $LogDir "$safeAgentName-runner-$Timestamp.cmd"
    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($prompt, $cmd, $traceId, $agentName, $dir, $promptFile, $stdoutFile, $stderrFile, $runnerFile)
        $env:CLAUDE_TEAM_MODE   = "1"
        $env:DIGEST_TRACE_ID    = $traceId
        $env:AGENT_PHASE        = "phase2-auto"
        $env:AGENT_NAME         = $agentName
        Set-Location $dir
        $fullPrompt = "請以正體中文輸出。`n`n$prompt"
        Set-Content -Path $promptFile -Value $fullPrompt -Encoding UTF8
        @(
            "@echo off"
            "cd /d ""$dir"""
            "$cmd < ""$promptFile"" > ""$stdoutFile"" 2> ""$stderrFile"""
            "exit /b %errorlevel%"
        ) | Set-Content -Path $runnerFile -Encoding ASCII

        try {
            $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", $runnerFile) `
                -WorkingDirectory $dir -Wait -NoNewWindow -PassThru
            $stdout = if (Test-Path $stdoutFile) { Get-Content -Path $stdoutFile -Encoding UTF8 } else { @() }
            $stderr = if (Test-Path $stderrFile) { Get-Content -Path $stderrFile -Encoding UTF8 } else { @() }

            if ($proc.ExitCode -ne 0 -and $stdout.Count -eq 0 -and $stderr.Count -gt 0) {
                return @("[codex-exit:$($proc.ExitCode)]") + $stderr
            }
            if ($stdout.Count -gt 0) { return $stdout }
            if ($stderr.Count -gt 0) { return @("[codex-stderr]") + $stderr }
            return @()
        } finally {
            foreach ($tmp in @($promptFile, $runnerFile)) {
                if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
            }
        }
    } -ArgumentList $PromptContent, $codexCmd, $TraceId, $AgentName, $AgentDir, $promptFile, $stdoutFile, $stderrFile, $runnerFile
    $job | Add-Member -NotePropertyName "StdOutFile" -NotePropertyValue $stdoutFile -Force
    $job | Add-Member -NotePropertyName "StdErrFile" -NotePropertyValue $stderrFile -Force
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

function Start-CursorCliJob {
    param(
        [string]$TaskKey,
        [string]$TaskFile,
        [string]$AgentDir,
        [int]$TimeoutSeconds = 600,
        [string]$TraceId = ""
    )
    $safeKey    = $TaskKey
    $resultFile = Join-Path $AgentDir "results\todoist-auto-$safeKey.json"
    $stderrFile = Join-Path $AgentDir "logs\cursor-cli-$safeKey-stderr.log"

    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($taskFile, $resultFile, $stderrFile, $traceId, $taskKey, $dir)
        $env:CLAUDE_TEAM_MODE = "1"
        $env:DIGEST_TRACE_ID  = $traceId
        $env:AGENT_PHASE      = "phase2-auto"
        $env:AGENT_NAME       = "cursor-cli-$taskKey"
        Set-Location $dir

        $startTime = Get-Date
        $content   = Get-Content $taskFile -Raw -Encoding UTF8

        # Ensure logs dir exists
        $logsDir = Split-Path $stderrFile -Parent
        if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }

        $output = & agent -p $content 2>$stderrFile
        $exitCode = $LASTEXITCODE
        $elapsed  = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)

        # 取最後 10 行作為摘要
        $outputLines = $output | Where-Object { $_ }
        $summaryLines = ($outputLines | Select-Object -Last 10) -join "`n"

        # Ensure results dir exists
        $resultsDir = Split-Path $resultFile -Parent
        if (-not (Test-Path $resultsDir)) { New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null }

        # 若 Agent 已寫入有效結果檔（含 type/agent/status），僅合併後設資料，不覆蓋 note_id/kb_imported/topic
        $existing = $null
        if (Test-Path $resultFile) {
            try {
                $raw = Get-Content $resultFile -Raw -Encoding UTF8
                if ($raw -and $raw.Length -ge 100) {
                    $existing = $raw | ConvertFrom-Json
                    if ($existing.agent -and $existing.status -and ($existing.PSObject.Properties.Name -contains "type")) {
                        $existing.backend      = "cursor_cli"
                        $existing.elapsed      = $elapsed
                        $existing.exit_code    = $exitCode
                        $existing.trace_id     = $traceId
                        $existing.generated_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
                        if (-not $existing.summary -and $summaryLines) { $existing.summary = $summaryLines }
                        if ($exitCode -ne 0 -and $existing.status -eq "completed") { $existing.status = "failed" }
                        $existing | ConvertTo-Json -Depth 5 | Set-Content $resultFile -Encoding UTF8
                        return $output
                    }
                }
            } catch { }
        }

        $result = @{
            agent        = "todoist-auto-$taskKey"
            backend      = "cursor_cli"
            status       = if ($exitCode -eq 0) { "completed" } else { "failed" }
            summary      = $summaryLines
            elapsed      = $elapsed
            exit_code    = $exitCode
            trace_id     = $traceId
            generated_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        }
        $result | ConvertTo-Json -Depth 3 | Set-Content $resultFile -Encoding UTF8
        return $output
    } -ArgumentList $TaskFile, $resultFile, $stderrFile, $TraceId, $TaskKey, $AgentDir

    $job | Add-Member -NotePropertyName "ResultFile" -NotePropertyValue $resultFile -Force
    $job | Add-Member -NotePropertyName "StdErrFile"  -NotePropertyValue $stderrFile  -Force
    return $job
}

# 移除 Markdown frontmatter（--- ... ---），避免 claude -p 將 prompt 誤判為貼上的文件
function Strip-Frontmatter {
    param([string]$Content)
    $lines = $Content -split "`n"
    if ($lines.Count -gt 0 -and $lines[0].Trim() -eq '---') {
        for ($i = 1; $i -lt $lines.Count; $i++) {
            if ($lines[$i].Trim() -eq '---') {
                return ($lines[($i+1)..($lines.Count-1)] -join "`n").TrimStart("`n`r")
            }
        }
    }
    return $Content
}

# ============================================
# Start execution
# ============================================
$startTime = Get-Date

# ─── 載入環境變數（Todoist token 僅從 .env 讀取）───
$envFile = "$AgentDir\.env"
$todoistTokenSource = "none"

# TODOIST_API_TOKEN（固定只從 .env 載入，避免被使用者/系統環境變數污染）
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
# PID 存活檢查邏輯：
#   死進程 → 強制清除孤立鎖，繼續執行
#   活進程 → 等待 5 分鐘後再查；仍活 → ntfy 通知「前一任務執行中」後退出；已死 → 清除鎖繼續執行
$TodoistTeamLockFile = "$AgentDir\state\run-todoist-agent-team.lock"
if (Test-Path $TodoistTeamLockFile) {
    $lockContent = Get-Content $TodoistTeamLockFile -Raw -ErrorAction SilentlyContinue
    $lockPid = ($lockContent -split "`n")[0].Trim()
    $existingProcess = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
        Write-Log "[LOCK] PID $lockPid 仍在運行，等待 5 分鐘後再確認..."
        Start-Sleep -Seconds 300
        # 5 分鐘後再次檢查
        $existingProcess2 = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
        if ($existingProcess2) {
            Write-Log "[SKIP] 前一任務（PID $lockPid）5 分鐘後仍在執行中，退出避免重疊。"
            # ntfy 通知前一任務仍執行中
            $ntfyLockJson = "$AgentDir\temp\ntfy-lock-overlap-$(Get-Date -Format 'HHmmss').json"
            @{
                topic = "wangsc2025"
                title = "⚠️ Todoist 任務排程重疊"
                message = "前一次 todoist-team 排程（PID $lockPid）仍在執行，本次（PID $PID）已跳過。若持續發生請確認任務是否卡死。"
                priority = 3
                tags = @("warning")
            } | ConvertTo-Json | Set-Content $ntfyLockJson -Encoding UTF8
            try {
                curl -s -X POST https://ntfy.sh -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyLockJson" | Out-Null
            } catch {}
            Remove-Item $ntfyLockJson -Force -ErrorAction SilentlyContinue
            exit 0
        }
        # 5 分鐘後已死進程：若鎖仍存在則強制清除
        Write-Log "[LOCK] PID $lockPid 於等待期間結束，強制清除孤立鎖後繼續執行。"
        Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue
    } else {
        Write-Log "[WARN] Stale lock found (PID $lockPid not running). Removing."
        Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue
    }
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
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
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
# Phase 0b: ADR-024 高失敗時段前置健康檢查（time_slot_profiles）
# ============================================
$script:ADR024_SkipPhase2 = $false
$script:ADR024_SkipKBTasks = $false
if (Test-Path $timeoutsPath) {
    try {
        $ty = ConvertFrom-YamlViapy -YamlPath $timeoutsPath
        $tsp = $ty.time_slot_profiles
        if ($tsp -and $tsp.high_failure_slots) {
            $currentHour = (Get-Date).Hour
            $slot = $tsp.high_failure_slots | Where-Object { [int]$_.hour -eq $currentHour } | Select-Object -First 1
            if ($slot -and $slot.pre_execution_health_check -eq $true) {
                Write-Log "[Phase0b] ADR-024: 高失敗時段 ${currentHour}:00，執行前置健康檢查（KB + Todoist）"
                $hc = $tsp.health_check
                $kbOk = $false
                $todoistOk = $false
                if ($hc.kb_endpoint) {
                    try {
                        $kbSec = [int]($hc.kb_timeout_sec ?? 5)
                        Invoke-RestMethod -Uri $hc.kb_endpoint -Method Get -TimeoutSec $kbSec -ErrorAction Stop | Out-Null
                        $kbOk = $true
                        Write-Log "[Phase0b] KB ping OK"
                        # 持久化 KB 存活狀態，供 Phase 2 agent 直接讀取（免重複 curl）
                        @{
                            checked_at   = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
                            kb_alive     = $true
                            endpoint     = $hc.kb_endpoint
                            ttl_minutes  = 30
                        } | ConvertTo-Json | Set-Content (Join-Path $AgentDir "cache\kb_live_status.json") -Encoding UTF8
                    } catch {
                        Write-Log "[Phase0b] KB ping 失敗: $($_.Exception.Message)"
                        @{
                            checked_at  = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
                            kb_alive    = $false
                            endpoint    = $hc.kb_endpoint
                            ttl_minutes = 30
                            error       = $_.Exception.Message
                        } | ConvertTo-Json | Set-Content (Join-Path $AgentDir "cache\kb_live_status.json") -Encoding UTF8
                    }
                } else {
                    $kbOk = $true
                }
                if ($hc.todoist_endpoint -and $todoistToken) {
                    try {
                        $todoistSec = [int]($hc.todoist_timeout_sec ?? 8)
                        $headers = @{ Authorization = "Bearer $todoistToken" }
                        Invoke-RestMethod -Uri $hc.todoist_endpoint -Method Get -Headers $headers -TimeoutSec $todoistSec -ErrorAction Stop | Out-Null
                        $todoistOk = $true
                        Write-Log "[Phase0b] Todoist API ping OK"
                    } catch {
                        Write-Log "[Phase0b] Todoist API ping 失敗: $($_.Exception.Message)"
                    }
                } else {
                    if (-not $todoistToken) { Write-Log "[Phase0b] 略過 Todoist ping（無 token）" }
                    $todoistOk = $true
                }
                $onKb = $hc.on_kb_failure ?? "skip_kb_tasks"
                $onTodoist = $hc.on_todoist_failure ?? "skip_phase2"
                $onBoth = $hc.on_both_failure ?? "abort_and_notify"
                if (-not $kbOk -and -not $todoistOk) {
                    if ($onBoth -eq "abort_and_notify") {
                        Write-Log "[Phase0b] ADR-024: KB 與 Todoist 均不可用，中止並發送告警"
                        Update-FailureStats "adr024_health_check" "phase0" "todoist"
                        $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
                        Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "ADR-024 pre-execution health check: KB and Todoist unavailable" -Sections @{ health_check = "both_failed" }
                        $ntfyTopic = "wangsc2025"
                        $bodyFile = Join-Path $AgentDir "ntfy_adr024_alert.json"
                        @{ topic = $ntfyTopic; title = "Todoist Agent 健康檢查失敗"; message = "ADR-024: 高失敗時段前置檢查 KB 與 Todoist 均不可用，本次執行已中止"; tags = @("warning") } | ConvertTo-Json | Set-Content $bodyFile -Encoding UTF8
                        try {
                            curl -s -X POST "https://ntfy.sh" -H "Content-Type: application/json; charset=utf-8" -d "@$bodyFile" | Out-Null
                        } catch { Write-Log "[Phase0b] ntfy 告警發送失敗: $_" }
                        if (Test-Path $bodyFile) { Remove-Item $bodyFile -Force }
                        if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
                        exit 1
                    }
                }
                if (-not $todoistOk -and $onTodoist -eq "skip_phase2") {
                    $script:ADR024_SkipPhase2 = $true
                    Write-Log "[Phase0b] ADR-024: Todoist 不可用，本次跳過 Phase 2，直接 Phase 3 組裝"
                }
                if (-not $kbOk -and $onKb -eq "skip_kb_tasks") {
                    $script:ADR024_SkipKBTasks = $true
                    Write-Log "[Phase0b] ADR-024: KB 不可用，本次跳過需 KB 的自動任務"
                }
            }
        }
    } catch {
        Write-Log "[Phase0b] ADR-024 time_slot_profiles 讀取或執行失敗（略過）: $_"
    }
}

# ============================================
# Phase 0c: ADR-027 自動任務公平輪轉 Fairness-Hint 預計算
# 讀取 context/auto-tasks-today.json 偵測飢餓任務，
# 寫入 state/auto-task-fairness-hint.json 供 Phase 1 參考。
# 同時保護 next_execution_order 不越界（超過 max 則重置為 1）。
# ============================================
$autoTasksTrackingFile = "$AgentDir\context\auto-tasks-today.json"
$fairnessHintFile = "$AgentDir\state\auto-task-fairness-hint.json"
try {
    $fairnessJson = uv run --project $AgentDir python -X utf8 -c @"
import json, os, yaml, datetime

tracking_path = r'$($autoTasksTrackingFile -replace '\\','\\')'
freq_path     = r'$($AgentDir -replace '\\','\\')\\config\\frequency-limits.yaml'
hint_path     = r'$($fairnessHintFile -replace '\\','\\')'

with open(freq_path, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

tasks = cfg.get('tasks') or {}
today = datetime.datetime.now().strftime('%Y-%m-%d')

# 讀取或初始化 tracking 檔案
tracking = {}
if os.path.exists(tracking_path):
    try:
        with open(tracking_path, 'r', encoding='utf-8') as f:
            tracking = json.load(f)
    except Exception:
        tracking = {}

# 若 date 不一致 → 視同全部 0
if tracking.get('date') != today:
    tracking = {'date': today}

# 計算每個任務的今日執行次數
counts = {}
for key in tasks:
    counts[key] = tracking.get(f'{key}_count', 0)

# 偵測飢餓任務（今日執行次數 = 0，且今日為允許執行日）
today_weekday = datetime.datetime.now().weekday()  # Mon=0...Sun=6
def is_allowed_today(task):
    allowed = task.get('allowed_days')
    if not allowed:
        return True
    return today_weekday in allowed

zero_tasks = [k for k, v in counts.items() if v == 0 and tasks[k].get('daily_limit', 0) > 0 and is_allowed_today(tasks[k])]

# 偵測 next_execution_order 越界（大於所有 execution_order 的最大值 + 1）
max_order = max((t.get('execution_order', 0) for t in tasks.values()), default=1)
current_order = tracking.get('next_execution_order', 1)
if current_order > max_order:
    tracking['next_execution_order'] = 1
    with open(tracking_path, 'w', encoding='utf-8') as f:
        json.dump(tracking, f, ensure_ascii=False)
    pointer_reset = True
else:
    pointer_reset = False

# 計算 fairness score（標準差 / 平均值；越接近 0 越公平）
non_zero = [v for v in counts.values() if v > 0]
if len(non_zero) >= 2:
    mean_v = sum(non_zero) / len(non_zero)
    std_v  = (sum((x - mean_v)**2 for x in non_zero) / len(non_zero)) ** 0.5
    fairness_score = round(std_v / mean_v if mean_v > 0 else 0, 3)
else:
    fairness_score = 0.0

hint = {
    'generated_at': datetime.datetime.now().isoformat(),
    'date': today,
    'starvation_count': len(zero_tasks),
    'starvation_detected': len(zero_tasks) > 0,
    'zero_count_tasks': zero_tasks[:10],  # 最多列 10 個
    'fairness_score': fairness_score,
    'pointer_reset': pointer_reset,
    'next_execution_order': tracking.get('next_execution_order', 1),
    'max_execution_order': max_order,
}
with open(hint_path, 'w', encoding='utf-8') as f:
    json.dump(hint, f, ensure_ascii=False, indent=2)

print(json.dumps({'starvation_count': len(zero_tasks), 'fairness_score': fairness_score, 'pointer_reset': pointer_reset}))
"@
    if ($fairnessJson) {
        $fairness = ConvertFrom-Json $fairnessJson
        Write-Log "[Phase0c] ADR-027 fairness-hint: starvation_count=$($fairness.starvation_count) fairness_score=$($fairness.fairness_score) pointer_reset=$($fairness.pointer_reset)"
        if ($fairness.pointer_reset) {
            Write-Log "[Phase0c] ADR-027 next_execution_order 越界，已重置為 1"
        }
    }
} catch {
    Write-Log "[Phase0c] ADR-027 fairness-hint 計算失敗（略過，不影響主流程）: $_"
}

# ============================================
# Phase 0d: Workflow 自動引用前置注入
# 讀取 config/agent-extra-reads.yaml：
#   enabled: false → 不注入（Agent 靠 preamble.md 自律讀取 workflows/index.yaml）
#   enabled: true  → 將 global_reads[].path 組裝為前置指示，注入到 Phase 2 每個 prompt 開頭
# 預設 enabled=false，不影響現有執行流程。
# 啟用方式：將 config/agent-extra-reads.yaml 的 enabled 改為 true。
# ============================================
$script:WorkflowInjectPrefix = ""
$extraReadsPath = Join-Path $AgentDir "config\agent-extra-reads.yaml"
if (Test-Path $extraReadsPath) {
    try {
        $extraReadsCfg = uv run --project $AgentDir python -X utf8 -c @"
import json, yaml
with open(r'$($extraReadsPath -replace '\\', '\\\\')', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
print(json.dumps({'enabled': bool(cfg.get('enabled', False)), 'global_reads': cfg.get('global_reads', [])}))
"@ 2>$null
        if ($extraReadsCfg) {
            $cfg = ConvertFrom-Json $extraReadsCfg
            if ($cfg.enabled -eq $true) {
                $pathList = @($cfg.global_reads | Where-Object { $_.path } | ForEach-Object { "- $($_.path)" }) -join "`n"
                if ($pathList) {
                    $script:WorkflowInjectPrefix = @"

## 執行前置讀取（自動注入，來自 config/agent-extra-reads.yaml）
在執行主要任務的第一個步驟之前，讀取以下 workflow 索引：
$pathList
然後依你的 task_key 篩選 task_types 匹配的 entries，讀取對應 workflow 文件並遵守其規範。

"@
                    Write-Log "[Phase0d] Workflow 注入前綴已準備（$(@($cfg.global_reads).Count) 個 global reads）"
                }
            } else {
                Write-Log "[Phase0d] agent-extra-reads.yaml enabled=false，略過注入（Agent 靠 preamble 自律讀取）"
            }
        }
    } catch {
        Write-Log "[Phase0d] WARN: agent-extra-reads.yaml 讀取失敗，略過注入: $($_.Exception.Message)"
    }
} else {
    Write-Log "[Phase0d] agent-extra-reads.yaml 不存在，略過"
}

# ============================================
# Phase 0e: ADR-037 時段風險評估閘門
# 評估當前小時的執行風險，決定是否降級或跳過非關鍵任務
# ============================================
$script:ADR037_SkipTaskTypes = @()
$script:ADR037_TimeoutMultiplier = 1.0
$script:ADR037_CriticalRisk = $false
try {
    $riskScorerPath = Join-Path $AgentDir "tools\time_slot_risk_scorer.py"
    if (Test-Path $riskScorerPath) {
        $riskJson = uv run --project $AgentDir python $riskScorerPath --format json 2>$null
        if ($riskJson) {
            $riskData = $riskJson | ConvertFrom-Json
            $riskLevel = $riskData.risk.risk_level
            $riskScore = [double]$riskData.risk.risk_score
            $riskAction = $riskData.risk.recommended_action
            Write-Log "[Phase0e] ADR-037 時段風險: hour=$((Get-Date).Hour) level=$riskLevel score=$riskScore action=$riskAction"
            switch ($riskAction) {
                "extend_timeout" {
                    $script:ADR037_TimeoutMultiplier = 1.30
                    Write-Log "[Phase0e] Timeout +30% buffer 已啟用"
                }
                "skip_non_critical" {
                    $script:ADR037_TimeoutMultiplier = 1.30
                    if ($riskData.risk.skip_task_types) {
                        $script:ADR037_SkipTaskTypes = @($riskData.risk.skip_task_types)
                        Write-Log "[Phase0e] 跳過非關鍵任務類型: $($script:ADR037_SkipTaskTypes -join ', ')"
                    }
                }
                "skip_phase2" {
                    $script:ADR037_CriticalRisk = $true
                    Write-Log "[Phase0e] WARN: critical 風險時段，Phase 2 執行受限"
                }
            }
            # 持久化風險評估結果供後續分析
            $riskJson | Set-Content (Join-Path $AgentDir "state\time-slot-risk.json") -Encoding UTF8
        }
    } else {
        Write-Log "[Phase0e] time_slot_risk_scorer.py 不存在，略過風險評估"
    }
} catch {
    Write-Log "[Phase0e] 風險評估失敗（不影響主流程）: $($_.Exception.Message)"
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
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
    exit 1
}

# 預先計算「每日自動任務總上限」並寫入 results/todoist-daily-cap.json，供 Phase 1/3 單一真相來源（避免今日進度顯示 40/45 不一致）
$dailyCapFile = "$ResultsDir\todoist-daily-cap.json"
try {
    $freqPath = Join-Path $AgentDir "config\frequency-limits.yaml"
    $capPath = Join-Path $AgentDir "results\todoist-daily-cap.json"
    $capJson = uv run --project $AgentDir python -c "
import json, yaml, sys
freq_path = r'$($freqPath -replace '\\','\\')'
cap_path = r'$($capPath -replace '\\','\\')'
with open(freq_path, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
tasks = cfg.get('tasks') or {}
import datetime as _dt
_today_wd = _dt.datetime.now().weekday()
def _allowed(t):
    ad = t.get('allowed_days')
    return (not ad) or (_today_wd in ad)
total = sum(int(t.get('daily_limit', 0)) for t in tasks.values() if _allowed(t))
with open(cap_path, 'w', encoding='utf-8') as out:
    json.dump({'total_daily_cap': total}, out, ensure_ascii=False)
print(total)
"
    if ($capJson -match '^\d+$') {
        Write-Log "[Phase1] total_daily_cap pre-computed: $capJson (written to results/todoist-daily-cap.json)"
    }
} catch {
    Write-Log "[Phase1] WARN: todoist-daily-cap.json 未寫入，Phase 1 將自行從 YAML 加總: $_"
}

$queryContent = Strip-Frontmatter (Get-Content -Path $queryPrompt -Raw -Encoding UTF8)
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
            $chatroomContent = Strip-Frontmatter (Get-Content -Path $chatroomQueryPrompt -Raw -Encoding UTF8)
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
            if ($job.State -eq 'Completed') {
                $phase1Success = $true
                # ─── 驗證 plan 檔案是否在本次 Phase 1 執行期間寫入 ───
                # 防止 LLM 給出對話性回應（未寫入 plan）時誤用前次 run 的舊 plan
                if (Test-Path "$ResultsDir\todoist-plan.json") {
                    $planWriteTime = (Get-Item "$ResultsDir\todoist-plan.json").LastWriteTime
                    if ($planWriteTime -lt $phase1Start) {
                        $planAgeMin = [int]((Get-Date) - $planWriteTime).TotalMinutes
                        Write-Log "[Phase1] WARN: plan 檔案（寫入 ${planAgeMin} min ago）早於本次 Phase 1 開始，LLM 疑似對話性回應未寫入新 plan，標記為失敗重試"
                        $phase1Success = $false
                    }
                } else {
                    Write-Log "[Phase1] WARN: LLM job 完成但未產出 plan 檔案，疑似對話性回應，標記為失敗重試"
                    $phase1Success = $false
                }
            }
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

# ─── Phase 1 Fallback: 若計畫檔在本次執行視窗內已寫入，即使 Job 超時也視為成功 ───
# 根因：Claude CLI 寫完 todoist-plan.json 後可能繼續做收尾（日誌/狀態），
# 導致 PS Job 超時而計畫檔實際上已完整產出。
# 注意：必須同時滿足「本次 phase1Start 之後寫入」才能啟用 Fallback，
# 避免對話性回應後誤用前次 run 的舊 plan（若舊 plan 仍在 900s 視窗內）。
if (-not $phase1Success -and (Test-Path "$ResultsDir\todoist-plan.json")) {
    $planItem = Get-Item "$ResultsDir\todoist-plan.json"
    $planAge = [int]((Get-Date) - $planItem.LastWriteTime).TotalSeconds
    $maxValidAge = ($MaxPhase1Retries + 1) * $Phase1TimeoutSeconds + 60  # 執行視窗（2×420）+ 60s 緩衝 = 900s
    $planWrittenThisRun = ($planItem.LastWriteTime -ge $phase1Start)
    if ($planAge -lt $maxValidAge -and $planWrittenThisRun) {
        $phase1Success = $true
        Write-Log "[Phase1] Fallback: 計畫檔在本次執行超時前已寫入（age=${planAge}s），繼續執行"
    }
    else {
        Write-Log "[Phase1] Fallback 跳過：計畫檔過舊（age=${planAge}s）或非本次產出（writtenThisRun=$planWrittenThisRun）"
    }
}

$phase1End = Get-Date
$phase1Seconds = [int]($phase1End - $phase1Start).TotalSeconds
$phase1Duration = [int]($phase1End - $startTime).TotalSeconds
Write-Log "=== Phase 1 complete (${phase1Duration}s from start, ${phase1Seconds}s phase-only) ==="
if ($phase1Success) {
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "completed" -AgentType "todoist" -Detail "plan_type=$($plan.plan_type)"
    # ADR-035: Phase 1 結束預算查核
    try {
        $bc1 = uv run --project $AgentDir python tools/phase_budget_reporter.py `
            --phase phase1 --trace-id $traceId --no-alert --format json 2>$null | ConvertFrom-Json
        if ($bc1 -and $bc1.warn_phase) {
            Write-Log "[ADR-035] Phase 1 token 警告: $($bc1.phase_tokens) / $($bc1.phase_limit) ($([math]::Round($bc1.phase_utilization * 100, 0))%)"
        }
        if ($bc1 -and $bc1.warn_trace) {
            Write-Log "[ADR-035] Trace token 警告: $($bc1.trace_tokens) / $($bc1.trace_warn_limit)"
        }
    } catch { }
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
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
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
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
    exit 1
}

# ─── Plan Schema 驗證：防止 LLM 輸出合法 JSON 但非 plan 格式（對話性 JSON）───
$validPlanTypes = @("tasks", "auto", "idle")
if (-not $plan.plan_type -or $plan.plan_type -notin $validPlanTypes) {
    Write-Log "[ERROR] Plan schema invalid: plan_type='$($plan.plan_type)' 不在 $($validPlanTypes -join '/')"
    Update-FailureStats "parse_error" "phase1" "todoist"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "plan schema invalid: bad plan_type" -Sections @{ query = "failed" }
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
    exit 1
}
if ($plan.plan_type -eq "tasks" -and ($null -eq $plan.tasks)) {
    Write-Log "[ERROR] Plan schema invalid: plan_type=tasks 但 tasks 欄位缺失"
    Update-FailureStats "parse_error" "phase1" "todoist"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "plan schema invalid: tasks missing" -Sections @{ query = "failed" }
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
    exit 1
}
if ($plan.plan_type -eq "auto" -and ($null -eq $plan.auto_tasks -or $null -eq $plan.auto_tasks.selected_tasks)) {
    Write-Log "[ERROR] Plan schema invalid: plan_type=auto 但 auto_tasks.selected_tasks 欄位缺失"
    Update-FailureStats "parse_error" "phase1" "todoist"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "plan schema invalid: auto_tasks missing" -Sections @{ query = "failed" }
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
    exit 1
}
Write-Log "[Phase1] Plan schema OK: plan_type=$($plan.plan_type)"

$forcedAutoTasksRaw = $env:TODOIST_TEAM_FORCE_AUTO_TASKS
if ($forcedAutoTasksRaw) {
    $forcedTaskKeys = @($forcedAutoTasksRaw.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($forcedTaskKeys.Count -gt 0) {
        $autoTaskNameMap = @{}
        try {
            $taskNameJson = uv run --project $AgentDir python -c @"
import json, yaml
with open('config/frequency-limits.yaml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
print(json.dumps({k: v.get('name', k) for k, v in cfg.get('tasks', {}).items()}, ensure_ascii=False))
"@
            if ($taskNameJson) {
                $taskNameObj = ConvertFrom-Json $taskNameJson
                $taskNameObj.PSObject.Properties | ForEach-Object { $autoTaskNameMap[$_.Name] = $_.Value }
            }
        } catch {
            Write-Log "[Phase1] WARN: 無法載入 auto-task 名稱對照，forced override 將使用 key 顯示"
        }

        $forcedSelectedTasks = @()
        foreach ($taskKey in $forcedTaskKeys) {
            $forcedSelectedTasks += [PSCustomObject]@{
                key  = $taskKey
                name = if ($autoTaskNameMap.ContainsKey($taskKey)) { $autoTaskNameMap[$taskKey] } else { $taskKey }
            }
        }

        $plan.plan_type = "auto"
        $plan.tasks = @()
        $plan.auto_tasks = [PSCustomObject]@{
            selected_tasks            = $forcedSelectedTasks
            next_execution_order_after = $null
            forced_by_env             = "TODOIST_TEAM_FORCE_AUTO_TASKS"
        }

        $plan | ConvertTo-Json -Depth 10 |
            Set-Content -Path $planFile -Encoding UTF8 -Force
        Write-Log "[Phase1] Forced auto-tasks override via TODOIST_TEAM_FORCE_AUTO_TASKS: $($forcedTaskKeys -join ', ')"
    }
}

# ============================================
# Autonomous runtime policy (由 supervisor 輸出)
# ============================================
$runtimePolicyFile = Join-Path $AgentDir "state\autonomous-runtime.json"
if (Test-Path $runtimePolicyFile) {
    try {
        $runtimePolicy = Get-Content -Path $runtimePolicyFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $mode = if ($runtimePolicy.mode) { $runtimePolicy.mode } else { "normal" }
        Write-Log "[Autonomy] runtime mode=$mode"

        if ($plan.plan_type -eq "auto" -and $null -ne $plan.auto_tasks -and $null -ne $plan.auto_tasks.selected_tasks) {
            $selectedTasks = @($plan.auto_tasks.selected_tasks)
            $beforeCount = $selectedTasks.Count
            $allowHeavy = $true
            $allowResearch = $true
            $maxParallel = 4

            if ($runtimePolicy.policies) {
                if ($null -ne $runtimePolicy.policies.allow_heavy_auto_tasks) {
                    $allowHeavy = [bool]$runtimePolicy.policies.allow_heavy_auto_tasks
                }
                if ($null -ne $runtimePolicy.policies.allow_research_auto_tasks) {
                    $allowResearch = [bool]$runtimePolicy.policies.allow_research_auto_tasks
                }
                if ($runtimePolicy.policies.max_parallel_auto_tasks) {
                    $maxParallel = [int]$runtimePolicy.policies.max_parallel_auto_tasks
                }
            }

            $heavyTaskKeys = @(
                "podcast_create", "podcast_jiaoguangzong", "tech_research", "ai_deep_research",
                "ai_github_research", "ai_workflow_github", "shurangama", "jiaoguangzong",
                "fahua", "jingtu", "insight_briefing", "workflow_forge", "future_plan_optimize"
            )
            $researchTaskKeys = @(
                "tech_research", "ai_deep_research", "ai_github_research", "ai_workflow_github",
                "ai_smart_city", "ai_sysdev", "shurangama", "jiaoguangzong", "fahua", "jingtu"
            )
            $blockedTaskKeys = @()

            if (-not $allowHeavy) {
                if ($runtimePolicy.policies.heavy_task_keys) {
                    $heavyTaskKeys = @($runtimePolicy.policies.heavy_task_keys)
                }
            }
            if (-not $allowResearch) {
                if ($runtimePolicy.policies.research_task_keys) {
                    $researchTaskKeys = @($runtimePolicy.policies.research_task_keys)
                }
            }
            if ($runtimePolicy.policies.blocked_task_keys) {
                $blockedTaskKeys = @($runtimePolicy.policies.blocked_task_keys)
            }

            $tasksBeforeFilter = @($selectedTasks)

            if (-not $allowHeavy) {
                $selectedTasks = @($selectedTasks | Where-Object { $_.key -notin $heavyTaskKeys })
            }
            if (-not $allowResearch) {
                $selectedTasks = @($selectedTasks | Where-Object { $_.key -notin $researchTaskKeys })
            }
            if ($blockedTaskKeys.Count -gt 0) {
                $selectedTasks = @($selectedTasks | Where-Object { $_.key -notin $blockedTaskKeys })
            }
            if ($selectedTasks.Count -gt $maxParallel) {
                $selectedTasks = @($selectedTasks | Select-Object -First $maxParallel)
            }

            # ADR-037: 時段風險評估降級過濾（Phase 0e 計算的高風險時段）
            if ($script:ADR037_SkipTaskTypes.Count -gt 0) {
                $adr037Blocked = @($selectedTasks | Where-Object {
                    $taskType = $_.task_type
                    $script:ADR037_SkipTaskTypes | Where-Object { $taskType -like "*$_*" }
                })
                $selectedTasks = @($selectedTasks | Where-Object {
                    $taskType = $_.task_type
                    -not ($script:ADR037_SkipTaskTypes | Where-Object { $taskType -like "*$_*" })
                })
                foreach ($bt in $adr037Blocked) {
                    $skippedResultPath = "results/todoist-auto-$($bt.key).json"
                    $adr037Result = [ordered]@{
                        agent     = "todoist-auto-$($bt.key)"
                        status    = "skipped"
                        task_id   = $null
                        type      = $bt.key
                        topic     = $null
                        summary   = "ADR-037 時段風險降級：$($bt.task_type) 類型在高風險時段暫停"
                        error     = "adr037_time_slot_risk"
                        done_cert = $null
                    }
                    $adr037Result | ConvertTo-Json -Depth 5 | Set-Content -Path $skippedResultPath -Encoding UTF8 -Force
                    Write-Log "[Phase0e] ADR-037 跳過任務: $($bt.key) (type=$($bt.task_type))"
                }
                if ($adr037Blocked.Count -gt 0) {
                    Write-Log "[Phase0e] ADR-037 降級過濾: $($adr037Blocked.Count) 個任務被跳過"
                }
            }

            # 為被自主模式過濾掉的任務補寫佔位結果檔（skipped），
            # 避免 Phase 3 誤報「未產出結果檔案」
            $filteredOutTasks = @($tasksBeforeFilter | Where-Object { $_.key -notin ($selectedTasks | ForEach-Object { $_.key }) })
            foreach ($ft in $filteredOutTasks) {
                $skippedResultPath = "results/todoist-auto-$($ft.key).json"
                $skipReason = if (-not $allowHeavy -and $ft.key -in $heavyTaskKeys) { "autonomy_heavy_blocked" }
                              elseif (-not $allowResearch -and $ft.key -in $researchTaskKeys) { "autonomy_research_blocked" }
                              elseif ($ft.key -in $blockedTaskKeys) { "autonomy_explicit_blocked" }
                              else { "autonomy_max_parallel_exceeded" }
                $skippedResult = [ordered]@{
                    agent   = "todoist-auto-$($ft.key)"
                    status  = "skipped"
                    task_id = $null
                    type    = $ft.key
                    topic   = $null
                    summary = "自主模式降速：任務被阻擋（$skipReason）"
                    error   = $skipReason
                    done_cert = $null
                }
                $skippedResult | ConvertTo-Json -Depth 5 | Set-Content -Path $skippedResultPath -Encoding UTF8 -Force
                Write-Log "[Autonomy] Wrote skipped placeholder: $skippedResultPath (reason=$skipReason)"
            }

            $plan.auto_tasks.selected_tasks = $selectedTasks
            $plan | ConvertTo-Json -Depth 10 | Set-Content -Path $planFile -Encoding UTF8 -Force
            Write-Log "[Autonomy] auto-tasks adjusted: $beforeCount -> $($selectedTasks.Count) (allowHeavy=$allowHeavy, allowResearch=$allowResearch, maxParallel=$maxParallel, blocked=$($blockedTaskKeys.Count))"
        }
    } catch {
        Write-Log "[Autonomy] WARN: runtime policy parse failed: $_"
    }
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
        if ($selectedTasks.Count -gt 1) {
            $multiAutoBuffer = [Math]::Min(180, [int]([Math]::Ceiling($maxAutoTimeout * 0.15)))
            $Phase2TimeoutSeconds += $multiAutoBuffer
            Write-Log "[Dynamic] +${multiAutoBuffer}s auto buffer for $($selectedTasks.Count) parallel tasks"
        }
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
# ADR-018: 記錄每個 Phase 2 job 的 descriptor，供 timeout 時重試使用（max 1 retry, 30s backoff）
$phase2JobDescriptors = @()
$sections = @{ query = "success" }

if ($script:ADR024_SkipPhase2) {
    Write-Log "[Phase2] ADR-024: 前置健康檢查 Todoist 不可用，跳過 Phase 2 執行，直接進入 Phase 3 組裝"
}
elseif ($plan.plan_type -eq "tasks") {
    # Scenario A: Execute Todoist tasks in parallel
    foreach ($task in $plan.tasks) {
        $promptFile = $task.prompt_file
        if (-not (Test-Path "$AgentDir\$promptFile")) {
            Write-Log "[Phase2] Task prompt not found: $promptFile"
            continue
        }
        $taskPrompt = Strip-Frontmatter (Get-Content -Path "$AgentDir\$promptFile" -Raw -Encoding UTF8)
        # 確保 Write 在 allowedTools（子 Agent 需要 Write 才能產出結果 JSON）
        $taskTools = $task.allowed_tools
        if ($taskTools -notmatch '\bWrite\b') {
            $taskTools = "$taskTools,Write"
            Write-Log "[Phase2] allowedTools 缺少 Write，已自動補入（task rank=$($task.rank)）"
        }
        $taskRank = $task.rank
        $taskContent = $task.content
        $taskId = $task.task_id

        # Fix: 強制注入結果 JSON 寫入指示（不依賴 Phase 1 LLM 是否有附加）
        # 使用單引號 here-string 避免 backtick 被 PS 解析為轉義字元，再用 -replace 替換變數
        $safeContent = $taskContent -replace '"', '\"'
        $resultJsonTemplate = @'

---

## ⚠️ 重要：執行完成後必須寫入結果檔案（強制）

**無論任務成功、部分完成或失敗，最後一步都必須用 Write 工具建立 `results/todoist-result-RANK.json`**：

```json
{
  "agent": "todoist-task-RANK",
  "status": "success",
  "task_id": "TASKID",
  "type": "todoist_task",
  "content": "TASKCONTENT",
  "duration_seconds": 0,
  "done_cert": { "status": "DONE", "quality_score": 4, "remaining_issues": [] },
  "summary": "一句話摘要",
  "error": null
}
```

- `status` 填 `"success"`、`"partial"` 或 `"failed"`
- `summary` 填實際完成內容的一句話描述
- `quality_score` 填 1-5
- **此步驟不可省略，否則 Phase 3 組裝無法取得本任務結果**
'@
        $resultJsonInstruction = $resultJsonTemplate `
            -replace 'RANK', $taskRank `
            -replace 'TASKID', $taskId `
            -replace 'TASKCONTENT', $safeContent
        $taskPrompt = $taskPrompt.TrimEnd() + $resultJsonInstruction

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
        $phase2JobDescriptors += @{ plan_type = "tasks"; taskPrompt = $taskPrompt; taskTools = $taskTools; taskName = $taskName }
        Write-Log "[Phase2] Started: $taskName (Job $($job.Id)) - $($task.content)"
    }
}
elseif ($plan.plan_type -eq "auto") {
    # Scenario B: Execute auto-tasks selected by Phase 1 (up to 4 in parallel)
    $selectedTasks = $plan.auto_tasks.selected_tasks

    if ($null -eq $selectedTasks -or $selectedTasks.Count -eq 0) {
        Write-Log "[Phase2] No auto-tasks selected (all exhausted or error)"
        # all_exhausted_fallback：達上限時先執行排程（如淨土教觀學苑 1 集）再進入 Phase 3 通知
        $allExhausted = $plan.auto_tasks.all_exhausted -eq $true
        if ($allExhausted -and (Test-Path "$AgentDir\config\frequency-limits.yaml")) {
            try {
                $fl = ConvertFrom-YamlViapy -YamlPath "$AgentDir\config\frequency-limits.yaml"
                $fallback = $fl.all_exhausted_fallback
                $notifyMsg = $fl.all_exhausted_notify_message
                if ($fallback -eq "jiaoguang_podcast_one" -and $notifyMsg) {
                    $fallbackScript = Join-Path $AgentDir "tools\run-jiaoguang-podcast-next.ps1"
                    $primaryBackend = $fl.all_exhausted_fallback_primary
                    if (-not $primaryBackend) { $primaryBackend = "claude" }
                    $fallbackBackend = if ($primaryBackend -eq "cursor_cli") { "claude" } else { "cursor_cli" }
                    # 每日上限預檢：今日已達上限則靜默跳過，不寫 fallback.json、不通知
                    $podcastStatePath = Join-Path $AgentDir "context\jiaoguang-podcast-next.json"
                    $podcastDailyLimit = if ($fl.all_exhausted_fallback_daily_limit) { [int]$fl.all_exhausted_fallback_daily_limit } else { 3 }
                    $todayStr = Get-Date -Format "yyyy-MM-dd"
                    $podcastTodayCount = 0
                    if (Test-Path $podcastStatePath) {
                        try { $ps = Get-Content $podcastStatePath -Raw -Encoding UTF8 | ConvertFrom-Json; if ($ps.today_date -eq $todayStr) { $podcastTodayCount = [int]$ps.today_count } } catch {}
                    }
                    if ($podcastTodayCount -ge $podcastDailyLimit) {
                        Write-Log "[Phase2] all_exhausted_fallback: 今日已達上限 $podcastDailyLimit 集（today_count=$podcastTodayCount），靜默跳過"
                    } elseif (Test-Path $fallbackScript) {
                        Write-Log "[Phase2] all_exhausted_fallback: 製作第 $($podcastTodayCount + 1)/$podcastDailyLimit 集（primary=$primaryBackend, 備援=$fallbackBackend）"
                        $jiaoguangOk = $false
                        $fallbackUrl = ""
                        foreach ($backend in @($primaryBackend, $fallbackBackend)) {
                            $fbOutput = & pwsh -ExecutionPolicy Bypass -File $fallbackScript -Backend $backend 2>&1
                            $fbOutput | ForEach-Object { Write-Log "  [jiaoguang-$backend] $_" }
                            if ($LASTEXITCODE -eq 0) {
                                $jiaoguangOk = $true
                                $urlLine = $fbOutput | Where-Object { $_ -match '^PODCAST_URL: ' } | Select-Object -Last 1
                                if ($urlLine) { $fallbackUrl = $urlLine -replace '^PODCAST_URL: ', '' }
                                Write-Log "[Phase2] all_exhausted_fallback 完成（backend=$backend）$(if ($fallbackUrl) { " URL=$fallbackUrl" })"
                                break
                            }
                            Write-Log "[Phase2] all_exhausted_fallback primary=$backend 失敗，嘗試備援 $fallbackBackend"
                        }
                        $resultsDir = Join-Path $AgentDir "results"
                        if (-not (Test-Path $resultsDir)) { New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null }
                        # 讀取最新集數標題以納入通知
                        $latestEpTitle = ""
                        try {
                            $phist = Get-Content (Join-Path $AgentDir "context\podcast-history.json") -Raw -Encoding UTF8 | ConvertFrom-Json
                            $latestEp = $phist.episodes | Select-Object -First 1
                            if ($latestEp.episode_title) { $latestEpTitle = $latestEp.episode_title }
                        } catch {}
                        $finalNotifyMsg = if (-not $jiaoguangOk) {
                            "⚠️ 淨土教觀學苑 podcast 製作失敗（primary 與備援皆未成功）"
                        } elseif ($latestEpTitle) { "$notifyMsg：$latestEpTitle" } else { $notifyMsg }
                        @{ ran = "jiaoguang_podcast_one"; notify_message = $finalNotifyMsg; episode_title = $latestEpTitle; episode_url = $fallbackUrl; failed = (-not $jiaoguangOk) } | ConvertTo-Json -Depth 2 | Set-Content -Path (Join-Path $resultsDir "todoist-exhausted-fallback.json") -Encoding UTF8
                        if (-not $jiaoguangOk) { Write-Log "[Phase2] all_exhausted_fallback primary 與備援皆未成功" }
                    }
                }
            } catch {
                Write-Log "[Phase2] all_exhausted_fallback 讀取或執行失敗: $_"
            }
        }
    }
    else {
        Write-Log "[Phase2] Starting $($selectedTasks.Count) auto-task agents in parallel..."

        # ADR-024：需 KB 的任務 key（前置健康檢查 KB 不可用時跳過）
        $ADR024_KB_TASK_KEYS = @(
            "shurangama", "jiaoguangzong", "fahua", "jingtu",
            "tech_research", "ai_deep_research", "unsloth_research", "ai_github_research", "ai_workflow_github", "ai_smart_city", "ai_sysdev",
            "skill_audit", "log_audit", "system_insight", "arch_evolution", "kb_insight_evaluation", "insight_briefing", "future_plan_optimize", "workflow_forge",
            "podcast_create", "podcast_jiaoguangzong"
        )

        # Dedicated team prompts：動態掃描實際檔案，防止重命名後路徑失效
        # 命名規則：prompts/team/todoist-auto-{plan_key}.md（底線，與 frequency-limits.yaml key 一致）
        $dedicatedPrompts = @{}
        Get-ChildItem "$AgentDir\prompts\team\todoist-auto-*.md" -ErrorAction SilentlyContinue | ForEach-Object {
            $key = $_.BaseName -replace "^todoist-auto-", ""
            $dedicatedPrompts[$key] = $_.FullName
        }
        Write-Log "[Phase2] Discovered $($dedicatedPrompts.Count) dedicated prompts: $($dedicatedPrompts.Keys -join ', ')"

        # ADR-028: Phase 2 Resume — 跳過 60 分鐘內已產出結果檔的任務（斷點續跑）
        $resumeSkippedKeys = @()
        $resumeableTasks = [System.Collections.Generic.List[object]]::new()
        foreach ($rtask in $selectedTasks) {
            $rKey = ($rtask.key -replace '-', '_')
            $rResultFile = "$ResultsDir\todoist-auto-$rKey.json"
            if (Test-Path $rResultFile) {
                $fileAgeMins = ((Get-Date) - (Get-Item $rResultFile).LastWriteTime).TotalMinutes
                if ($fileAgeMins -lt 60) {
                    $resumeSkippedKeys += $rKey
                    Write-Log "[Phase2-Resume] ADR-028 跳過 $rKey（結果檔距今 $([int]$fileAgeMins) min，視為已完成）"
                    continue
                }
            }
            $resumeableTasks.Add($rtask) | Out-Null
        }
        if ($resumeSkippedKeys.Count -gt 0) {
            $selectedTasks = $resumeableTasks.ToArray()
            Write-Log "[Phase2-Resume] ADR-028 resume 完成：跳過 $($resumeSkippedKeys.Count) 個，剩餘 $($selectedTasks.Count) 個任務"
        }
        # 寫入 Phase 2 snapshot（供後續診斷）
        try {
            @{ run_id = $RunId; timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"); selected_tasks = @($selectedTasks | ForEach-Object { $_.key }); skipped_resume = $resumeSkippedKeys } |
                ConvertTo-Json | Set-Content "$AgentDir\state\phase2-snapshot.json" -Encoding UTF8 -Force
        } catch { Write-Log "[Phase2-Resume] snapshot 寫入失敗（不影響主流程）: $_" "WARN" }

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
                "insightbriefing"    = "insight_briefing"
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
            # ADR-024: KB 不可用時跳過需 KB 的自動任務
            if ($script:ADR024_SkipKBTasks -and ($ADR024_KB_TASK_KEYS -contains $normalizedKey)) {
                Write-Log "[Phase2] ADR-024: 跳過需 KB 的任務 $normalizedKey（前置健康檢查 KB 不可用）"
                continue
            }

            # ADR-028: Phase 2 快照恢復 — 若結果檔存在且 < 45 分鐘，視為前次中斷後的已完成任務，跳過重跑
            $snapshotResultFile = "$AgentDir\results\todoist-auto-$normalizedKey.json"
            if (Test-Path $snapshotResultFile) {
                $snapshotAge = [int]((Get-Date) - (Get-Item $snapshotResultFile).LastWriteTime).TotalMinutes
                if ($snapshotAge -lt 45) {
                    Write-Log "[Phase2] ADR-028 snapshot-resume: $normalizedKey 結果檔存在（${snapshotAge} min ago），跳過重跑"
                    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "running" -AgentType "todoist" -Detail "snapshot-resume:$normalizedKey"
                    $sections["auto-$normalizedKey"] = "snapshot-resume"
                    continue
                }
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

            $promptContent = Strip-Frontmatter (Get-Content -Path $promptToUse -Raw -Encoding UTF8)

            # Phase 0d: Workflow 前置注入（agent-extra-reads.yaml enabled=true 時有效）
            if ($script:WorkflowInjectPrefix -and $script:WorkflowInjectPrefix.Length -gt 0) {
                $promptContent = $script:WorkflowInjectPrefix + $promptContent
                Write-Log "[Phase2] Phase0d workflow prefix injected for $normalizedKey"
            }

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
            $stderrFile = $null

            if ($backend.type -eq "codex") {
                $job = Start-CodexJob -TaskKey $taskKey -PromptContent $promptContent `
                    -LiveWebSearch $backend.live_ws -TraceId $traceId -AgentName $agentName `
                    -ModelFlag $backend.model_flag
            } elseif ($backend.type -eq "openrouter_runner") {
                $job = Start-OpenRouterJob -TaskKey $taskKey -PromptContent $promptContent `
                    -TraceId $traceId -AgentName $agentName
            } elseif ($backend.type -eq "cursor_cli") {
                $cursorTaskFile = Join-Path $AgentDir "temp\cursor-cli-task-$taskKey.md"
                if (-not (Test-Path $cursorTaskFile)) {
                    Write-Log "[Phase2] WARN: cursor_cli task file missing ($cursorTaskFile), skip $taskKey"
                    $job = $null
                } else {
                    $timeout = if ($backend.timeout_seconds) { [int]$backend.timeout_seconds } else { 600 }
                    $job = Start-CursorCliJob -TaskKey $taskKey -TaskFile $cursorTaskFile `
                        -AgentDir $AgentDir -TimeoutSeconds $timeout -TraceId $traceId
                    $stderrFile = Join-Path $AgentDir "logs\cursor-cli-$taskKey-stderr.log"
                }
            } else {
                # claude_code: 原有 Start-Job，注入可選的 cli_flag（如 --model claude-haiku-4-5）
                $cliFlag = $backend.cli_flag
                $stderrFile = "$LogDir\$agentName-stderr-$Timestamp.log"
                $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                    param($prompt, $agentName, $logDir, $timestamp, $traceId, $apiToken, $cliFlag, $stderrFile)

                    [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                    [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                    [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2-auto", "Process")
                    [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
                    if ($apiToken) {
                        [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
                    }

                    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                    $OutputEncoding = [System.Text.Encoding]::UTF8

                    # 動態組合 claude 參數（支援 --model 旗標注入）
                    $claudeArgs = @("-p", "--allowedTools", "Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch")
                    if ($cliFlag) { $claudeArgs += ($cliFlag -split '\s+') }
                    $output = $prompt | claude @claudeArgs 2>$stderrFile

                    if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                        $stderrSize = (Get-Item $stderrFile).Length
                        if ($stderrSize -eq 0) { Remove-Item $stderrFile -Force }
                    }
                    return $output
                } -ArgumentList $promptContent, $agentName, $LogDir, $Timestamp, $traceId, $todoistToken, $cliFlag, $stderrFile
            }

            $job | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $agentName -Force
            $job | Add-Member -NotePropertyName "BackendName" -NotePropertyValue $backend.backend -Force
            if ($stderrFile) {
                $job | Add-Member -NotePropertyName "StdErrFile" -NotePropertyValue $stderrFile -Force
            }
            $phase2Jobs += $job
            $phase2JobDescriptors += @{ plan_type = "auto"; promptContent = $promptContent; taskKey = $taskKey; backend = $backend; agentName = $agentName; taskName = $taskName }
            Write-Log "[Phase2] Started: $agentName ($taskName) backend=$($backend.backend) (Job $($job.Id))"
        }
    }
}
else {
    # Scenario C: idle（全部達上限）
    Write-Log "[Phase2] Idle - all auto-tasks at daily limit"
    # all_exhausted_fallback：先執行排程（如淨土教觀學苑 1 集）再進入 Phase 3
    if (Test-Path "$AgentDir\config\frequency-limits.yaml") {
        try {
            $fl = ConvertFrom-YamlViapy -YamlPath "$AgentDir\config\frequency-limits.yaml"
            $fallback = $fl.all_exhausted_fallback
            $notifyMsg = $fl.all_exhausted_notify_message
            if ($fallback -eq "jiaoguang_podcast_one" -and $notifyMsg) {
                $fallbackScript = Join-Path $AgentDir "tools\run-jiaoguang-podcast-next.ps1"
                $primaryBackend = $fl.all_exhausted_fallback_primary
                if (-not $primaryBackend) { $primaryBackend = "claude" }
                $fallbackBackend = if ($primaryBackend -eq "cursor_cli") { "claude" } else { "cursor_cli" }
                # 每日上限預檢：今日已達上限則靜默跳過，不寫 fallback.json、不通知
                $podcastStatePath = Join-Path $AgentDir "context\jiaoguang-podcast-next.json"
                $podcastDailyLimit = if ($fl.all_exhausted_fallback_daily_limit) { [int]$fl.all_exhausted_fallback_daily_limit } else { 3 }
                $todayStr = Get-Date -Format "yyyy-MM-dd"
                $podcastTodayCount = 0
                if (Test-Path $podcastStatePath) {
                    try { $ps = Get-Content $podcastStatePath -Raw -Encoding UTF8 | ConvertFrom-Json; if ($ps.today_date -eq $todayStr) { $podcastTodayCount = [int]$ps.today_count } } catch {}
                }
                if ($podcastTodayCount -ge $podcastDailyLimit) {
                    Write-Log "[Phase2] all_exhausted_fallback: 今日已達上限 $podcastDailyLimit 集（today_count=$podcastTodayCount），靜默跳過"
                } elseif (Test-Path $fallbackScript) {
                    Write-Log "[Phase2] all_exhausted_fallback: 製作第 $($podcastTodayCount + 1)/$podcastDailyLimit 集（primary=$primaryBackend, 備援=$fallbackBackend）"
                    $jiaoguangOk = $false
                    $fallbackUrl = ""
                    foreach ($backend in @($primaryBackend, $fallbackBackend)) {
                        $fbOutput = & pwsh -ExecutionPolicy Bypass -File $fallbackScript -Backend $backend 2>&1
                        $fbOutput | ForEach-Object { Write-Log "  [jiaoguang-$backend] $_" }
                        if ($LASTEXITCODE -eq 0) {
                            $jiaoguangOk = $true
                            $urlLine = $fbOutput | Where-Object { $_ -match '^PODCAST_URL: ' } | Select-Object -Last 1
                            if ($urlLine) { $fallbackUrl = $urlLine -replace '^PODCAST_URL: ', '' }
                            Write-Log "[Phase2] all_exhausted_fallback 完成（backend=$backend）$(if ($fallbackUrl) { " URL=$fallbackUrl" })"
                            break
                        }
                        Write-Log "[Phase2] all_exhausted_fallback primary=$backend 失敗，嘗試備援 $fallbackBackend"
                    }
                    $resultsDir = Join-Path $AgentDir "results"
                    if (-not (Test-Path $resultsDir)) { New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null }
                    # 讀取最新集數標題以納入通知
                    $latestEpTitle = ""
                    try {
                        $phist = Get-Content (Join-Path $AgentDir "context\podcast-history.json") -Raw -Encoding UTF8 | ConvertFrom-Json
                        $latestEp = $phist.episodes | Select-Object -First 1
                        if ($latestEp.episode_title) { $latestEpTitle = $latestEp.episode_title }
                    } catch {}
                    $finalNotifyMsg = if (-not $jiaoguangOk) {
                        "⚠️ 淨土教觀學苑 podcast 製作失敗（primary 與備援皆未成功）"
                    } elseif ($latestEpTitle) { "$notifyMsg：$latestEpTitle" } else { $notifyMsg }
                    @{ ran = "jiaoguang_podcast_one"; notify_message = $finalNotifyMsg; episode_title = $latestEpTitle; episode_url = $fallbackUrl; failed = (-not $jiaoguangOk) } | ConvertTo-Json -Depth 2 | Set-Content -Path (Join-Path $resultsDir "todoist-exhausted-fallback.json") -Encoding UTF8
                    if (-not $jiaoguangOk) { Write-Log "[Phase2] all_exhausted_fallback primary 與備援皆未成功" }
                }
            }
        } catch {
            Write-Log "[Phase2] all_exhausted_fallback 讀取或執行失敗: $_"
        }
    }
}

# Wait for Phase 2 jobs
if ($phase2Jobs.Count -gt 0) {
    Write-Log "[Phase2] Waiting for $($phase2Jobs.Count) agents (timeout: ${Phase2TimeoutSeconds}s)..."
    $phase2Jobs | Wait-Job -Timeout $Phase2TimeoutSeconds | Out-Null
}

# Collect Phase 2 results
$phase2QuotaFallbacks = @()    # Codex quota error → openrouter_research fallback
$phase2SandboxFallbacks = @()  # Codex exit 0 但結果檔缺失 → claude_sonnet45 fallback
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

        if ($agentName -like "auto-*") {
            $tkKey = $agentName -replace '^auto-', ''
            $stderrFile = if ($job.PSObject.Properties["StdErrFile"]) { $job.StdErrFile } else { "" }
            Repair-CompletedAutoTaskResultFile -TaskKey $tkKey -AgentName $agentName `
                -BackendName $job.BackendName -Output @($output) -StdErrFile $stderrFile `
                -JobElapsed $jobElapsed

            # Codex 失敗偵測（兩種模式）
            if ($job.BackendName -in @("codex_exec","codex_standard")) {
                $outputStr = (@($output) -join "`n")
                $desc = $phase2JobDescriptors | Where-Object { $_.agentName -eq $agentName } | Select-Object -First 1

                # 模式 A：quota exceeded（立即退出，output 含 limit 關鍵字）
                if ($outputStr -match "usage.limit|hit.*limit|quota.*exceeded|try.again.*Mar|monthly.limit|exceeded.*quota") {
                    Write-Log "[Phase2] $agentName Codex quota exceeded，排隊 cursor_cli / claude_sonnet45 fallback"
                    if ($desc) {
                        $phase2QuotaFallbacks += @{ taskKey = $tkKey; agentName = $agentName; promptContent = $desc.promptContent }
                    }
                }
                # 模式 B：沙箱持久化失敗（exit 0 跑完，但結果檔缺失）
                # 排除已在 quota 佇列的（避免雙重 fallback）
                elseif ($desc) {
                    $resultFilePath = "$AgentDir\results\todoist-auto-$tkKey.json"
                    $isSandboxFailure = $false
                    if (Test-Path $resultFilePath) {
                        try {
                            $rf = Get-Content $resultFilePath -Raw -Encoding UTF8 | ConvertFrom-Json
                            $isSandboxFailure = ($rf.reason -eq "result_file_missing_or_invalid")
                        } catch {}
                    }
                    if ($isSandboxFailure) {
                        Write-Log "[Phase2] $agentName Codex sandbox persistence failure（exit 0 但結果檔缺失），排隊 claude_sonnet45 fallback"
                        $phase2SandboxFallbacks += @{ taskKey = $tkKey; agentName = $agentName; promptContent = $desc.promptContent }
                    }
                }
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

        # Codex Failed state（ScriptBlock 拋出例外）→ 加入 quota fallback 佇列觸發備援
        if ($agentName -like "auto-*" -and $job.PSObject.Properties["BackendName"] -and $job.BackendName -in @("codex_exec","codex_standard")) {
            $tkKey = $agentName -replace '^auto-', ''
            $desc = $phase2JobDescriptors | Where-Object { $_.agentName -eq $agentName } | Select-Object -First 1
            if ($desc) {
                Write-Log "[Phase2] $agentName Codex job Failed（ScriptBlock 例外），排隊 quota fallback 備援"
                $phase2QuotaFallbacks += @{ taskKey = $tkKey; agentName = $agentName; promptContent = $desc.promptContent }
            }
        }
    }
}

# Codex quota fallback → cursor_cli（優先）→ claude_sonnet45（次選）
# openrouter / groq 嚴禁作為 fallback（結果不可靠）
if ($phase2QuotaFallbacks.Count -gt 0) {
    Write-Log "[Phase2] Codex quota fallback: $($phase2QuotaFallbacks.Count) 個任務（cursor_cli 優先，次選 claude_sonnet45）..."
    $quotaFallbackJobs = @()
    foreach ($qf in $phase2QuotaFallbacks) {
        $qfCursorTaskFile = Join-Path $AgentDir "temp\cursor-cli-task-$($qf.taskKey).md"
        if ((Get-Command agent -ErrorAction SilentlyContinue) -and (Test-Path $qfCursorTaskFile)) {
            # 第一優先：cursor_cli（有任務檔且 agent CLI 可用）
            $fbJob = Start-CursorCliJob -TaskKey $qf.taskKey -TaskFile $qfCursorTaskFile -AgentDir $AgentDir -TimeoutSeconds (Get-TaskTimeout $qf.taskKey) -TraceId $traceId
            if ($fbJob) {
                $fbJob | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $qf.agentName -Force
                $fbJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue "cursor_cli" -Force
                $quotaFallbackJobs += $fbJob
                Write-Log "[Phase2] quota-fallback started: $($qf.agentName) -> cursor_cli"
            }
        } else {
            # 次選：claude_sonnet45（無 cursor_cli task file 或 agent CLI 不可用）
            $reason = if (-not (Get-Command agent -ErrorAction SilentlyContinue)) { "agent CLI 不可用" } else { "無 cursor-cli-task 檔" }
            Write-Log "[Phase2] quota-fallback: $reason，改用 claude_sonnet45 ($($qf.agentName))"
            $qfStderrFile = "$LogDir\$($qf.agentName)-quota-fb-stderr-$Timestamp.log"
            $fbJob = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                param($prompt, $agentName, $traceId, $apiToken, $stderrFile)
                [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2-auto", "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
                if ($apiToken) { [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process") }
                [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                $OutputEncoding = [System.Text.Encoding]::UTF8
                $prompt | claude -p --allowedTools Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch --model claude-sonnet-4-5 2>$stderrFile
            } -ArgumentList $qf.promptContent, $qf.agentName, $traceId, $todoistToken, $qfStderrFile
            if ($fbJob) {
                $fbJob | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $qf.agentName -Force
                $fbJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue "claude_sonnet45" -Force
                $fbJob | Add-Member -NotePropertyName "StdErrFile" -NotePropertyValue $qfStderrFile -Force
                $quotaFallbackJobs += $fbJob
                Write-Log "[Phase2] quota-fallback started: $($qf.agentName) -> claude_sonnet45"
            }
        }
    }
    if ($quotaFallbackJobs.Count -gt 0) {
        $quotaFallbackJobs | Wait-Job -Timeout $Phase2TimeoutSeconds | Out-Null
        foreach ($fj in $quotaFallbackJobs) {
            $an = $fj.AgentName
            $fbOutput = Receive-Job -Job $fj -ErrorAction SilentlyContinue
            $tkKey = $an -replace '^auto-', ''
            if ($fj.State -eq "Completed") {
                $fbBackend = if ($fj.PSObject.Properties["BackendName"]) { $fj.BackendName } else { "claude_sonnet45" }
                Write-Log "[Phase2] quota-fallback $an completed ($fbBackend)"
                $fbResultPath = "$AgentDir\results\todoist-auto-$tkKey.json"
                $afterFallback = $null
                if (Test-Path $fbResultPath) {
                    try { $afterFallback = Get-Content $fbResultPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
                }
                if ($afterFallback -and $afterFallback.status -in @("success", "skipped", "partial")) {
                    # 備援成功（含非執行日 skipped、多階段任務 partial）：加註 fallback_backend，summary 前綴說明
                    $afterFallback | Add-Member -NotePropertyName "fallback_backend" -NotePropertyValue $fbBackend -Force
                    $origSummary = if ($afterFallback.summary) { $afterFallback.summary } else { "" }
                    $statusLabel = if ($afterFallback.status -eq "skipped") { "非執行日跳過" } elseif ($afterFallback.status -eq "partial") { "階段性完成" } else { "執行成功" }
                    $afterFallback.summary = "（以備援模型 $fbBackend $statusLabel）$origSummary"
                    $afterFallback | ConvertTo-Json -Depth 6 | Set-Content -Path $fbResultPath -Encoding UTF8 -Force
                    Write-Log "[Phase2] quota-fallback ${an}: $fbBackend 備援完成（status=$($afterFallback.status)）✓"
                } else {
                    $fbPreview = if ($fbOutput) { (@($fbOutput) -join "`n") } else { "" }
                    $fbPreviewShort = if ($fbPreview.Length -gt 500) { $fbPreview.Substring(0, 500) + "..." } else { $fbPreview }
                    @{
                        agent = "todoist-auto-$tkKey"; type = $tkKey
                        status = "failed"; reason = "codex_quota_fallback_no_result"
                        backend = $fbBackend
                        summary = "Codex 配額耗盡，$fbBackend fallback 執行完畢但無任何產出"
                        backend_stdout_preview = $fbPreviewShort
                        timestamp = (Get-Date -Format "o")
                    } | ConvertTo-Json -Depth 3 | Set-Content -Path $fbResultPath -Encoding UTF8 -Force
                    Write-Log "[Phase2] quota-fallback ${an}: $fbBackend 未產出 success 結果"
                }
                $sections[$an] = "success"
            } else {
                Write-Log "[Phase2] quota-fallback ${an} failed/timeout (state: $($fj.State))"
                Stop-Job -Job $fj -ErrorAction SilentlyContinue
            }
            Remove-Job -Job $fj -Force -ErrorAction SilentlyContinue
        }
    }
}

# Codex sandbox fallback → cursor_cli（優先）→ claude_sonnet45（次選）
# openrouter / groq 嚴禁作為 fallback
if ($phase2SandboxFallbacks.Count -gt 0) {
    Write-Log "[Phase2] Codex sandbox fallback: $($phase2SandboxFallbacks.Count) 個任務（cursor_cli 優先，次選 claude_sonnet45）..."
    $sandboxFallbackJobs = @()
    foreach ($sf in $phase2SandboxFallbacks) {
        $sfCursorTaskFile = Join-Path $AgentDir "temp\cursor-cli-task-$($sf.taskKey).md"
        $sfStderrFile = "$LogDir\$($sf.agentName)-sandbox-fb-stderr-$Timestamp.log"
        $sfJob = $null
        $sfBackendName = "claude_sonnet45"
        if ((Get-Command agent -ErrorAction SilentlyContinue) -and (Test-Path $sfCursorTaskFile)) {
            # 第一優先：cursor_cli
            $sfJob = Start-CursorCliJob -TaskKey $sf.taskKey -TaskFile $sfCursorTaskFile -AgentDir $AgentDir -TimeoutSeconds (Get-TaskTimeout $sf.taskKey) -TraceId $traceId
            $sfBackendName = "cursor_cli"
            Write-Log "[Phase2] sandbox-fallback started: $($sf.agentName) -> cursor_cli"
        } else {
            # 次選：claude_sonnet45
            $sfReason = if (-not (Get-Command agent -ErrorAction SilentlyContinue)) { "agent CLI 不可用" } else { "無 cursor-cli-task 檔" }
            Write-Log "[Phase2] sandbox-fallback: $sfReason，改用 claude_sonnet45 ($($sf.agentName))"
            $sfJob = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                param($prompt, $agentName, $traceId, $apiToken, $stderrFile)
                [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2-auto", "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
                if ($apiToken) { [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process") }
                [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                $OutputEncoding = [System.Text.Encoding]::UTF8
                $prompt | claude -p --allowedTools Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch --model claude-sonnet-4-5 2>$stderrFile
            } -ArgumentList $sf.promptContent, $sf.agentName, $traceId, $todoistToken, $sfStderrFile
            Write-Log "[Phase2] sandbox-fallback started: $($sf.agentName) -> claude_sonnet45"
        }
        if ($sfJob) {
            $sfJob | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $sf.agentName -Force
            $sfJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue $sfBackendName -Force
            $sfJob | Add-Member -NotePropertyName "StdErrFile" -NotePropertyValue $sfStderrFile -Force
            $sandboxFallbackJobs += $sfJob
        }
    }
    if ($sandboxFallbackJobs.Count -gt 0) {
        $sandboxFallbackJobs | Wait-Job -Timeout $Phase2TimeoutSeconds | Out-Null
        foreach ($sfj in $sandboxFallbackJobs) {
            $an = $sfj.AgentName
            $sfOutput = Receive-Job -Job $sfj -ErrorAction SilentlyContinue
            $tkKey = $an -replace '^auto-', ''
            if ($sfj.State -eq "Completed") {
                $sfBackend = if ($sfj.PSObject.Properties["BackendName"]) { $sfj.BackendName } else { "claude_sonnet45" }
                Write-Log "[Phase2] sandbox-fallback $an completed ($sfBackend)"
                # Repair 會因現有 partial_success 結果檔提早返回，改為直接檢查並強制補記
                $sfResultPath = "$AgentDir\results\todoist-auto-$tkKey.json"
                $afterSfFallback = $null
                if (Test-Path $sfResultPath) {
                    try { $afterSfFallback = Get-Content $sfResultPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
                }
                if ($afterSfFallback -and $afterSfFallback.status -in @("success", "skipped", "partial")) {
                    # 備援成功（含非執行日 skipped、多階段任務 partial）：加註 fallback_backend，summary 前綴說明
                    $afterSfFallback | Add-Member -NotePropertyName "fallback_backend" -NotePropertyValue $sfBackend -Force
                    $origSfSummary = if ($afterSfFallback.summary) { $afterSfFallback.summary } else { "" }
                    $sfStatusLabel = if ($afterSfFallback.status -eq "skipped") { "非執行日跳過" } elseif ($afterSfFallback.status -eq "partial") { "階段性完成" } else { "執行成功" }
                    $afterSfFallback.summary = "（以備援模型 $sfBackend $sfStatusLabel）$origSfSummary"
                    $afterSfFallback | ConvertTo-Json -Depth 6 | Set-Content -Path $sfResultPath -Encoding UTF8 -Force
                    Write-Log "[Phase2] sandbox-fallback ${an}: $sfBackend 備援完成（status=$($afterSfFallback.status)）✓"
                } else {
                    $sfPreview = if ($sfOutput) { (@($sfOutput) -join "`n") } else { "" }
                    $sfPreviewShort = if ($sfPreview.Length -gt 500) { $sfPreview.Substring(0, 500) + "..." } else { $sfPreview }
                    @{
                        agent = "todoist-auto-$tkKey"; type = $tkKey
                        status = "failed"; reason = "codex_sandbox_fallback_no_result"
                        backend = $sfBackend
                        summary = "Codex 沙箱持久化失敗，$sfBackend fallback 執行完畢但無任何產出"
                        backend_stdout_preview = $sfPreviewShort
                        timestamp = (Get-Date -Format "o")
                    } | ConvertTo-Json -Depth 3 | Set-Content -Path $sfResultPath -Encoding UTF8 -Force
                    Write-Log "[Phase2] sandbox-fallback ${an}: $sfBackend 未產出 success 結果，已強制補記 partial_success"
                }
                $sections[$an] = "success"
            } else {
                Write-Log "[Phase2] sandbox-fallback $an failed/timeout (state: $($sfj.State))"
                Stop-Job -Job $sfj -ErrorAction SilentlyContinue
            }
            Remove-Job -Job $sfj -Force -ErrorAction SilentlyContinue
        }
    }
}

# ADR-018: Phase 2 retry — 僅對 timeout 重試 1 次，exponential backoff 初始 30s，retry 事件寫入 spans
$phase2RetryJobs = @()
$toRetry = @()
for ($i = 0; $i -lt $phase2Jobs.Count; $i++) {
    $an = $phase2Jobs[$i].AgentName
    if ($sections[$an] -eq "timeout" -and $phase2JobDescriptors.Count -gt $i) {
        $toRetry += @{ index = $i; descriptor = $phase2JobDescriptors[$i] }
    }
}
if ($toRetry.Count -gt 0) {
    $backoffSec = 30
    Write-Log "[Phase2] ADR-018 retry: $($toRetry.Count) job(s) (timeout), backoff ${backoffSec}s..."
    Start-Sleep -Seconds $backoffSec
    foreach ($r in $toRetry) {
        $d = $r.descriptor
        $agentName = if ($d.plan_type -eq "tasks") { $d.taskName } else { $d.agentName }
        $retryStart = Get-Date
        $newJob = $null
        if ($d.plan_type -eq "tasks") {
            $newJob = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                param($prompt, $tools, $taskName, $logDir, $timestamp, $traceId, $apiToken)
                [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2", "Process")
                [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $taskName, "Process")
                if ($apiToken) { [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process") }
                [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                $OutputEncoding = [System.Text.Encoding]::UTF8
                $stderrFile = "$logDir\$taskName-stderr-$timestamp.log"
                $output = $prompt | claude -p --allowedTools $tools 2>$stderrFile
                if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) { $stderrSize = (Get-Item $stderrFile).Length; if ($stderrSize -eq 0) { Remove-Item $stderrFile -Force } }
                return $output
            } -ArgumentList $d.taskPrompt, $d.taskTools, $d.taskName, $LogDir, $Timestamp, $traceId, $todoistToken
        } else {
            $be = $d.backend
            $stderrFile = "$LogDir\$($d.agentName)-stderr-$Timestamp.log"
            if ($be.type -eq "codex") {
                # ADR-018 修正：Codex timeout 重試改用備援 backend（避免 quota/沙箱失敗無限重試）
                # 備援規則：非 cursor_cli → cursor_cli → claude（規則同 Get-TaskBackend）
                $retryCursorTaskFile = Join-Path $AgentDir "temp\cursor-cli-task-$($d.taskKey).md"
                if ((Get-Command agent -ErrorAction SilentlyContinue) -and (Test-Path $retryCursorTaskFile)) {
                    Write-Log "[Phase2] ADR-018 retry: $($d.agentName) codex timeout -> cursor_cli"
                    $newJob = Start-CursorCliJob -TaskKey $d.taskKey -TaskFile $retryCursorTaskFile -AgentDir $AgentDir -TimeoutSeconds (Get-TaskTimeout $d.taskKey) -TraceId $traceId
                    if ($newJob) { $newJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue "cursor_cli" -Force }
                } else {
                    # openrouter / groq 嚴禁作為 fallback，直接用 claude_sonnet45
                    $retryReason = if (-not (Get-Command agent -ErrorAction SilentlyContinue)) { "agent CLI 不可用" } else { "無 cursor-cli-task 檔" }
                    Write-Log "[Phase2] ADR-018 retry: $($d.agentName) codex timeout -> claude_sonnet45 ($retryReason)"
                    $newJob = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                        param($prompt, $agentName, $traceId, $apiToken, $stderrFile)
                        [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                        [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                        [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2-auto", "Process")
                        [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
                        if ($apiToken) { [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process") }
                        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                        $OutputEncoding = [System.Text.Encoding]::UTF8
                        $prompt | claude -p --allowedTools Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch --model claude-sonnet-4-5 2>$stderrFile
                    } -ArgumentList $d.promptContent, $d.agentName, $traceId, $todoistToken, $stderrFile
                    if ($newJob) { $newJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue "claude_sonnet45" -Force }
                }
                if ($newJob) {
                    $newJob | Add-Member -NotePropertyName "StdErrFile" -NotePropertyValue $stderrFile -Force
                }
            } elseif ($be.type -eq "openrouter_runner") {
                # 備援規則：非 cursor_cli → cursor_cli；cursor_cli → claude
                $retryOrCursorTaskFile = Join-Path $AgentDir "temp\cursor-cli-task-$($d.taskKey).md"
                if ((Get-Command agent -ErrorAction SilentlyContinue) -and (Test-Path $retryOrCursorTaskFile)) {
                    Write-Log "[Phase2] ADR-018 retry: $($d.agentName) openrouter timeout -> cursor_cli"
                    $newJob = Start-CursorCliJob -TaskKey $d.taskKey -TaskFile $retryOrCursorTaskFile -AgentDir $AgentDir -TimeoutSeconds (Get-TaskTimeout $d.taskKey) -TraceId $traceId
                    if ($newJob) { $newJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue "cursor_cli" -Force }
                } else {
                    Write-Log "[Phase2] ADR-018 retry: $($d.agentName) openrouter timeout -> openrouter (no cursor_cli task file)"
                    $newJob = Start-OpenRouterJob -TaskKey $d.taskKey -PromptContent $d.promptContent -TraceId $traceId -AgentName $d.agentName
                    if ($newJob) { $newJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue $be.backend -Force }
                }
            } else {
                # claude_code 類型：timeout 後優先嘗試 cursor_cli（若有任務檔），否則原模型重試
                # 備援規則：非 cursor_cli → cursor_cli；cursor_cli → claude（原地重試屬於 claude 備援鏈末端）
                $cliFlag = $be.cli_flag
                $retryClaudeCursorTaskFile = Join-Path $AgentDir "temp\cursor-cli-task-$($d.taskKey).md"
                if ((Get-Command agent -ErrorAction SilentlyContinue) -and (Test-Path $retryClaudeCursorTaskFile)) {
                    Write-Log "[Phase2] ADR-018 retry: $($d.agentName) claude timeout -> cursor_cli"
                    $newJob = Start-CursorCliJob -TaskKey $d.taskKey -TaskFile $retryClaudeCursorTaskFile -AgentDir $AgentDir -TimeoutSeconds (Get-TaskTimeout $d.taskKey) -TraceId $traceId
                    if ($newJob) { $newJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue "cursor_cli" -Force }
                } else {
                    Write-Log "[Phase2] ADR-018 retry: $($d.agentName) claude timeout -> claude (same model, no cursor_cli task file)"
                    $newJob = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
                        param($prompt, $agentName, $logDir, $timestamp, $traceId, $apiToken, $cliFlag, $stderrFile)
                        [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
                        [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
                        [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2-auto", "Process")
                        [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
                        if ($apiToken) { [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process") }
                        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                        $OutputEncoding = [System.Text.Encoding]::UTF8
                        $claudeArgs = @("-p", "--allowedTools", "Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch"); if ($cliFlag) { $claudeArgs += ($cliFlag -split '\s+') }
                        $output = $prompt | claude @claudeArgs 2>$stderrFile
                        if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) { $stderrSize = (Get-Item $stderrFile).Length; if ($stderrSize -eq 0) { Remove-Item $stderrFile -Force } }
                        return $output
                    } -ArgumentList $d.promptContent, $d.agentName, $LogDir, $Timestamp, $traceId, $todoistToken, $cliFlag, $stderrFile
                }
            }
            if ($newJob) {
                $newJob | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $d.agentName -Force
                # BackendName 可能已由 codex fallback 邏輯設定（openrouter_research / claude_sonnet45），不覆蓋
                if (-not $newJob.PSObject.Properties["BackendName"]) {
                    $newJob | Add-Member -NotePropertyName "BackendName" -NotePropertyValue $be.backend -Force
                }
                if (-not $newJob.PSObject.Properties["StdErrFile"]) {
                    $newJob | Add-Member -NotePropertyName "StdErrFile" -NotePropertyValue $stderrFile -Force
                }
            }
        }
        if ($newJob) {
            if (-not $newJob.PSObject.Properties["AgentName"]) {
                $newJob | Add-Member -NotePropertyName "AgentName" -NotePropertyValue $agentName -Force
            }
            $phase2RetryJobs += @{ job = $newJob; agentName = $agentName; retryStart = $retryStart }
        }
    }
    if ($phase2RetryJobs.Count -gt 0) {
        $retryJobsOnly = $phase2RetryJobs | ForEach-Object { $_.job }
        Write-Log "[Phase2] Waiting for $($retryJobsOnly.Count) retry job(s) (timeout: ${Phase2TimeoutSeconds}s)..."
        $retryJobsOnly | Wait-Job -Timeout $Phase2TimeoutSeconds | Out-Null
        foreach ($entry in $phase2RetryJobs) {
            $rj = $entry.job
            $an = $entry.agentName
            $output = Receive-Job -Job $rj -ErrorAction SilentlyContinue
            $retryEnd = Get-Date
            if ($rj.State -eq "Completed") {
                $sections[$an] = "success"
                if ($output) { $outputLines = @($output); $startIdx = [Math]::Max(0, $outputLines.Count - 5); for ($idx = $startIdx; $idx -lt $outputLines.Count; $idx++) { Write-Log "  [$an] $($outputLines[$idx])" } }
                $jobElapsed = if ($rj.PSBeginTime -and $rj.PSEndTime) { [int]($rj.PSEndTime - $rj.PSBeginTime).TotalSeconds } else { $null }
                Write-Log "[Phase2] $an retry completed$(if ($jobElapsed) { " (${jobElapsed}s)" })"
                Write-Span -TraceId $traceId -SpanType "retry" -Phase "phase2" -Agent $an -StartTime $entry.retryStart -EndTime $retryEnd -Status "retry_ok"
                if ($an -like "auto-*") {
                    $tkKey = $an -replace '^auto-', ''
                    $stderrFile = if ($rj.PSObject.Properties["StdErrFile"]) { $rj.StdErrFile } else { "" }
                    Repair-CompletedAutoTaskResultFile -TaskKey $tkKey -AgentName $an -BackendName $rj.BackendName -Output @($output) -StdErrFile $stderrFile -JobElapsed $jobElapsed
                }
            } else {
                if ($rj.State -eq "Running") { Stop-Job -Job $rj }
                Write-Span -TraceId $traceId -SpanType "retry" -Phase "phase2" -Agent $an -StartTime $entry.retryStart -EndTime $retryEnd -Status "retry_failed"
                Write-Log "[Phase2] $an retry failed (state: $($rj.State))"
            }
            $rj | Remove-Job -Force -ErrorAction SilentlyContinue
        }
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
# ADR-035: Phase 2 結束預算查核
try {
    $bc2 = uv run --project $AgentDir python tools/phase_budget_reporter.py `
        --phase phase2 --trace-id $traceId --no-alert --format json 2>$null | ConvertFrom-Json
    if ($bc2 -and $bc2.warn_phase) {
        Write-Log "[ADR-035] Phase 2 token 警告: $($bc2.phase_tokens) / $($bc2.phase_limit) ($([math]::Round($bc2.phase_utilization * 100, 0))%)"
    }
    if ($bc2 -and $bc2.suspend_trace) {
        Write-Log "[ADR-035] Trace token 超過暫停閾值，後續任務已中止"
    }
} catch { }
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
            $taskObj = $plan.tasks[$rank - 1]
            $taskContent = $taskObj.content
            $taskId = $taskObj.task_id
            $shortContent = if ($taskContent.Length -gt 40) { $taskContent.Substring(0, 40) + "…" } else { $taskContent }
            $missingResults += "task-$rank (todoist-result-$rank.json)"
            $sectionKey = "task-$rank"
            $jobState = $sections[$sectionKey]
            Write-Log "[Phase2] Missing result file: todoist-result-$rank.json — job state=$jobState — content: $shortContent" "WARN"

            # 補寫 fallback 結果檔（對齊 Repair-CompletedAutoTaskResultFile 行為）
            $fallbackStatus = if ($jobState -eq "timeout") { "failed" } elseif ($jobState -eq "success") { "partial" } else { "failed" }
            $fallbackReason = if ($jobState -eq "timeout") { "phase2_timeout" } else { "result_file_missing" }
            $fallback = @{
                agent            = "todoist-task-$rank"
                status           = $fallbackStatus
                task_id          = $taskId
                type             = "todoist_task"
                content          = $taskContent
                duration_seconds = 0
                done_cert        = @{ status = "FAILED"; quality_score = 0; remaining_issues = @("result_file_missing") }
                summary          = "Phase 2 Agent 未產出結果檔，已由排程自動補記（job_state=$jobState）"
                error            = $fallbackReason
            }
            $fallback | ConvertTo-Json -Depth 4 | Set-Content -Path $resultPath -Encoding UTF8 -Force
            Write-Log "[Phase2] task-$rank result file 補寫 (status=$fallbackStatus, job_state=$jobState)"
        }
    }
    if ($missingResults.Count -gt 0) {
        Write-Log "[Phase2] Backfilled $($missingResults.Count) missing result files: $($missingResults -join ', ')" "WARN"
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
# Phase 2.5: OODA Act 強制觸發
# arch_evolution 完成且有 pending immediate_fix 時，直接觸發 self_heal，
# 無需等待下輪 round-robin（參考 run-system-audit-team.ps1 Phase 4 模式）
# ============================================
if ($plan.plan_type -eq "auto") {
    $archEvoRan  = ($sections["auto-arch_evolution"] -eq "success")
    $selfHealRan = ($sections["auto-self_heal"] -ne $null)
    $archDecPath = "$AgentDir\context\arch-decision.json"

    if ($archEvoRan -and -not $selfHealRan -and (Test-Path $archDecPath)) {
        try {
            $archDec = Get-Content $archDecPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $archAgeMin = if ($archDec.generated_at) {
                [int]((Get-Date) - [DateTime]$archDec.generated_at).TotalMinutes
            } else { 999 }
            $pendingFixes = @()
            if ($archDec.decisions) {
                $pendingFixes = @($archDec.decisions | Where-Object {
                    $_.action -eq "immediate_fix" -and $_.execution_status -eq "pending"
                })
            }

            if ($archAgeMin -le 90 -and $pendingFixes.Count -gt 0) {
                Write-Log "[Phase2.5] OODA Act：arch_evolution 產出 $($pendingFixes.Count) 個 immediate_fix，直接觸發 self_heal"
                $selfHealPromptPath = "$AgentDir\prompts\team\todoist-auto-self_heal.md"
                if (Test-Path $selfHealPromptPath) {
                    $phase25LogFile = "$LogDir\phase25-selfheal-$($traceId.Substring(0,8)).log"
                    $phase25Start   = Get-Date
                    try {
                        $selfHealContent = Strip-Frontmatter (Get-Content $selfHealPromptPath -Raw -Encoding UTF8)
                        Write-Log "[Phase2.5] self_heal 啟動（OODA Act 強制觸發）"
                        $selfHealContent | claude -p --allowedTools "Read,Write,Edit,Bash,Glob,Grep" `
                            --model claude-sonnet-4-5-20251001 2>$phase25LogFile
                        $phase25Sec = [int]((Get-Date) - $phase25Start).TotalSeconds
                        Write-Log "[Phase2.5] self_heal 完成（OODA Act, ${phase25Sec}s）"
                        Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase25" -State "completed" `
                            -AgentType "todoist" -Detail "$($pendingFixes.Count) immediate_fix 已執行"
                    } catch {
                        $phase25Sec = [int]((Get-Date) - $phase25Start).TotalSeconds
                        Write-Log "[Phase2.5] self_heal 失敗（OODA Act, ${phase25Sec}s）：$_" "WARN"
                    }
                } else {
                    Write-Log "[Phase2.5] self_heal prompt 不存在，跳過 OODA Act 觸發" "WARN"
                }
            } else {
                Write-Log "[Phase2.5] OODA Act 跳過：pending=$($pendingFixes.Count) arch-age=${archAgeMin}m"
            }
        } catch {
            Write-Log "[Phase2.5] 讀取 arch-decision.json 失敗，跳過 OODA Act：$_" "WARN"
        }
    } elseif (-not $archEvoRan) {
        # arch_evolution 本輪未執行，靜默跳過（round-robin 正常輪轉）
    } elseif ($selfHealRan) {
        Write-Log "[Phase2.5] OODA Act 跳過：self_heal 本輪已執行"
    }
}

# ============================================
# Phase 3: Assembly (close + update + notify)
# ============================================
Write-Log ""
Write-Log "=== Phase 3: Assembly start ==="

# ─── Phase 1 結果驗證（防止 Phase 3 在 Phase 1 失敗時執行無效組裝）───
# 根因：Phase 1 LLM 對話性回應後 Fallback 若繞過驗證，Phase 3 會拿到舊 plan
# 組裝出完全無意義的結果（且 Phase 3 LLM 自身也會對話性崩潰）。
if (-not $phase1Success) {
    Write-Log "[Phase3] SKIP: Phase 1 未成功（phase1Success=false），跳過組裝以避免髒資料"
    Update-FailureStats "phase_failure" "phase3" "todoist"
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "skipped" -AgentType "todoist" -Detail "phase1 failed"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "phase 1 failed, phase 3 skipped" -Sections @{ query = "failed"; assemble = "skipped" }
    if (Test-Path $TodoistTeamLockFile) {
        Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue
        Write-Log "[Cleanup] Lock file removed (pre-exit)"
    }
    exit 1
}

Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "running" -AgentType "todoist"

$assemblePrompt = "$AgentDir\prompts\team\todoist-assemble.md"
if (-not (Test-Path $assemblePrompt)) {
    Write-Log "[ERROR] Assembly prompt not found: $assemblePrompt"
    $totalDuration = [int]((Get-Date) - $startTime).TotalSeconds
    Update-State -Status "failed" -Duration $totalDuration -ErrorMsg "assembly prompt not found" -Sections $sections
    if (Test-Path $TodoistTeamLockFile) { Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue }
    exit 1
}

$assembleContent = Strip-Frontmatter (Get-Content -Path $assemblePrompt -Raw -Encoding UTF8)
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
        $certJson = ($certResult | Out-String).Trim()
        if ($certJson -and $certJson -match '^\s*\{') {
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
    $phase3StderrTimestamp = Get-Date -Format "yyyyMMdd_HHmmss"

    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        # Set trace ID and phase marker for Phase 3
        $env:DIGEST_TRACE_ID = $traceId
        $env:AGENT_PHASE = "phase3"
        $env:AGENT_NAME = "todoist-assemble"

        $stderrFile = "$LogDir\assemble-stderr-$phase3StderrTimestamp.log"
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
            # ─── 偵測 LLM 對話性回應（未真正執行組裝）───
            $outputText = $output -join "`n"
            # ADR-20260322-log-audit: 修正過嚴 regex，涵蓋「請問你想要我做什麼」等變體
            # 移除 ^ 行首錨定（因 log 有 [assemble] 前綴），改匹配行內任意位置
            $conversationalPattern = '(?:你貼了|已收到.*完整內容|請問你.*(?:希望|想要|需要).*做什麼|請說明你的需求|請告訴我你的需求)'
            if ($outputText -match $conversationalPattern) {
                $phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
                Write-Log "[Phase3] WARN: LLM 給出對話性回應（${phase3Seconds}s），未執行組裝，標記為失敗重試"
                Update-FailureStats "phase_failure" "phase3" "todoist"
                Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "failed" -AgentType "todoist" -Detail "conversational response"
            } else {
                $phase3Success = $true
                $phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
                Write-Log "[Phase3] Assembly completed (${phase3Seconds}s)"
                Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase3" -State "completed" -AgentType "todoist"
                break
            }
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

# Clean up lock file (強制清理，確保正常結束時一定釋放鎖定)
if (Test-Path $TodoistTeamLockFile) {
    Remove-Item $TodoistTeamLockFile -Force -ErrorAction SilentlyContinue
    Write-Log "[Cleanup] Lock file removed"
}
