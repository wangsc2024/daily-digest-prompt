# ============================================
# System Audit Agent Team - Parallel Orchestrator (PowerShell 7)
# ============================================
# Usage:
#   Manual: pwsh -ExecutionPolicy Bypass -File run-system-audit-team.ps1
#   Task Scheduler: same command (daily 00:40)
# ============================================
# Architecture:
#   Phase 1: 4 parallel audit agents (dim1+5, dim2+6, dim3+7, dim4)
#   Phase 2: 1 assembly agent (collect + fix + report + RAG)
#   Phase 3: Decide（arch-evolution，審查後積極觸發；僅受 arch-decision 冷卻時間節流）
#   Phase 4: Act（self-heal，Phase 3 執行後直接觸發，執行 immediate_fix）
# ============================================

# PowerShell 7 defaults to UTF-8, explicit set for safety
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Set paths
$AgentDir = $PSScriptRoot
$LogDir = "$AgentDir\logs"
$StateFile = "$AgentDir\state\scheduler-state.json"
$ResultsDir = "$AgentDir\results"

# Config
$MaxPhase2Retries = 1
$Phase1TimeoutSeconds = 600  # 10 minutes per agent
$Phase2TimeoutSeconds = 1200  # 20 minutes
# Phase 3：與上次 arch-decision 最短間隔（分鐘）；0 = 每次審查皆跑 arch-evolution
$Phase3ArchDecisionCooldownMinutes = 90

# 從 config/timeouts.yaml 讀取 audit_team（與 run-agent-team.ps1 相同 uv+yaml 模式）
$timeoutsPath = Join-Path $AgentDir "config\timeouts.yaml"
if (Test-Path $timeoutsPath) {
    try {
        $tPath = $timeoutsPath -replace '\\', '/'
        $json = uv run --project $AgentDir python -c "import json,yaml; d=yaml.safe_load(open(r'$tPath',encoding='utf-8')); a=d.get('audit_team') or {}; print(json.dumps({'phase1_timeout':a.get('phase1_timeout'),'phase2_timeout':a.get('phase2_timeout'),'phase2_max_retries':a.get('phase2_max_retries'),'phase3_arch_decision_cooldown_minutes':a.get('phase3_arch_decision_cooldown_minutes')}))"
        $ta = $json | ConvertFrom-Json
        if ($ta.phase1_timeout) { $Phase1TimeoutSeconds = [int]$ta.phase1_timeout }
        if ($ta.phase2_timeout) { $Phase2TimeoutSeconds = [int]$ta.phase2_timeout }
        if ($null -ne $ta.phase2_max_retries -and $ta.phase2_max_retries -ne '') { $MaxPhase2Retries = [int]$ta.phase2_max_retries }
        if ($null -ne $ta.phase3_arch_decision_cooldown_minutes -and $ta.phase3_arch_decision_cooldown_minutes -ne '') {
            $Phase3ArchDecisionCooldownMinutes = [int]$ta.phase3_arch_decision_cooldown_minutes
        }
    } catch {
        # 保留上方 fallback
    }
}

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path "$LogDir\structured" | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\docs" | Out-Null

# ============================================
# Helper Functions
# ============================================

# FSM 狀態管理
function Set-FsmState {
    param(
        [string]$RunId,
        [string]$Phase,
        [string]$State,
        [string]$AgentType = "system-audit",
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

function Set-OodaState {
    param(
        [string]$Step,           # observe/orient/decide/act/complete
        [string]$Status,         # pending/running/completed/failed/skipped
        [hashtable]$Meta = @{}
    )

    $workflowFile = Join-Path $AgentDir "context\workflow-state.json"
    $transitionFile = Join-Path $AgentDir "logs\structured\ooda-transitions.jsonl"

    $now = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    $entry = @{
        ts       = $now
        run_id   = $traceId
        step     = $Step
        status   = $Status
        meta     = $Meta
    }

    # 更新 workflow-state.json（原子寫入，I1 修復：try/finally 清理 tmp 檔）
    $tmpFile = "$workflowFile.tmp"
    try {
        $state = @{
            run_id       = $traceId
            current_step = $Step
            status       = $Status
            updated_at   = $now
            history      = @()
        }
        if (Test-Path $workflowFile) {
            try {
                $existing = Get-Content $workflowFile -Raw -Encoding UTF8 | ConvertFrom-Json
                $state.history = @($existing.history) + @(@{ step = $existing.current_step; status = $existing.status; ts = $existing.updated_at })
                # 保留最近 20 筆歷史
                if ($state.history.Count -gt 20) {
                    $state.history = $state.history[-20..-1]
                }
            } catch {
                Write-Log "[OodaState] workflow-state.json 損壞，歷史記錄重置: $_"
            }
        }
        $state | ConvertTo-Json -Depth 5 | Set-Content $tmpFile -Encoding UTF8
        Move-Item $tmpFile $workflowFile -Force
        $tmpFile = $null  # 成功後清除 tmp 路徑，finally 不清理
    } catch {
        Write-Log "[OodaState] 寫入失敗: $_"
    } finally {
        if ($tmpFile -and (Test-Path $tmpFile)) {
            Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
        }
    }

    # Append to transitions JSONL
    try {
        $entry | ConvertTo-Json -Compress | Add-Content $transitionFile -Encoding UTF8
    } catch {
        Write-Log "[OodaState] JSONL 追加失敗: $_"
    }

    Write-Log "[OODA] $Step → $Status"
}

function Get-Timestamp {
    return Get-Date -Format "yyyy-MM-dd HH:mm:ss"
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Timestamp
    $logMessage = "[$timestamp] [$Level] $Message"
    Write-Host $logMessage
}

# Remove stderr file if empty or contains only benign warnings
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

function Update-SchedulerState {
    param(
        [string]$Status,
        [string]$Message = "",
        [int]$ExitCode = 0,
        [PSCustomObject]$PhaseBreakdown
    )

    if (-not (Test-Path $StateFile)) {
        $state = @{ executions = @() }
    } else {
        $state = Get-Content $StateFile -Encoding UTF8 | ConvertFrom-Json
    }

    $execution = @{
        timestamp       = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        start_time      = if ($script:auditStartTime) { $script:auditStartTime.ToString("yyyy-MM-ddTHH:mm:ss") } else { $null }
        agent           = "system-audit-team"
        status          = $Status
        message         = $Message
        exit_code       = $ExitCode
        phase_breakdown = $PhaseBreakdown
    }

    $state.executions += $execution

    # Keep last 200 executions
    if ($state.executions.Count -gt 200) {
        $state.executions = $state.executions[-200..-1]
    }

    $state | ConvertTo-Json -Depth 10 | Set-Content $StateFile -Encoding UTF8
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
    } catch { Write-Host "[Span] Write failed: $_" }
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

# JSON 反序列化後的 generated_at 可能是 string / DateTime / DateTimeOffset
function ConvertTo-DateTimeOffsetFromAuditJson {
    param($Raw)
    if ($null -eq $Raw) { return $null }
    if ($Raw -is [datetimeoffset]) { return $Raw }
    if ($Raw -is [datetime]) { return [datetimeoffset]::new($Raw) }
    $t = $Raw.ToString().Trim()
    if ([string]::IsNullOrWhiteSpace($t)) { return $null }
    try {
        return [datetimeoffset]::Parse(
            $t,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind
        )
    } catch {
        return $null
    }
}

# 審查剛完成時：有自動修正或明顯退步 → 略過 arch-decision 冷卻，強制跑 Phase 3
function Get-AuditPhase3CooldownBypass {
    param([string]$LastAuditPath)
    $out = [PSCustomObject]@{ Bypass = $false; Reason = "" }
    if (-not (Test-Path $LastAuditPath)) { return $out }
    try {
        $la = Get-Content $LastAuditPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $fixes = 0
        if ($null -ne $la.fixes_applied -and "$($la.fixes_applied)" -ne "") {
            $fixes = [int]$la.fixes_applied
        }
        if ($fixes -gt 0) {
            $out.Bypass = $true
            $out.Reason = "fixes_applied=$fixes"
            return $out
        }
        if ($la.previous -and $null -ne $la.previous.delta -and "$($la.previous.delta)" -ne "") {
            [double]$dv = 0
            if ([double]::TryParse($la.previous.delta.ToString(), [System.Globalization.NumberStyles]::Any, [cultureinfo]::InvariantCulture, [ref]$dv)) {
                if ($dv -lt -0.25) {
                    $out.Bypass = $true
                    $out.Reason = "score_regression_delta=$dv"
                    return $out
                }
            }
        }
    } catch {
        Write-Log "[Phase 3] 讀取 last-audit 以判斷冷卻略過失敗: $_" "WARN"
    }
    return $out
}

# ============================================
# Main Execution
# ============================================

$auditStartTime = Get-Date
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$phase1LogFile = "$LogDir\audit-phase1-$timestamp.log"
$phase2LogFile = "$LogDir\audit-phase2-$timestamp.log"

# ─── 載入 Todoist API Token（一次性，安全讀取）───
if (-not $env:TODOIST_API_TOKEN) {
    $envFile = "$AgentDir\.env"
    if (Test-Path $envFile) {
        $envLine = Get-Content $envFile | Where-Object { $_ -match '^TODOIST_API_TOKEN=' }
        if ($envLine) {
            $todoistToken = ($envLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $todoistToken, "Process")
            Write-Host "[Token] TODOIST_API_TOKEN loaded from .env"
        }
        else { $todoistToken = ""; Write-Host "[WARN] TODOIST_API_TOKEN not found in .env" }
    }
    else { $todoistToken = ""; Write-Host "[WARN] .env not found, TODOIST_API_TOKEN may be missing" }
}
else {
    $todoistToken = $env:TODOIST_API_TOKEN
    Write-Host "[Token] TODOIST_API_TOKEN loaded from environment"
}

# ─── 生產環境安全策略 ───
# 若未設定則預設 strict（排程器執行環境），手動執行可覆蓋
$validPresets = @("strict", "normal", "permissive")
if (-not (Test-Path Env:HOOK_SECURITY_PRESET)) {
    $env:HOOK_SECURITY_PRESET = "strict"
} elseif ($env:HOOK_SECURITY_PRESET -notin $validPresets) {
    Write-Log "[Security] WARN: Invalid HOOK_SECURITY_PRESET='$($env:HOOK_SECURITY_PRESET)', falling back to 'strict'" "WARN"
    $env:HOOK_SECURITY_PRESET = "strict"
}
Write-Log "[Security] HOOK_SECURITY_PRESET = $($env:HOOK_SECURITY_PRESET)" "INFO"

# Generate trace ID for distributed tracing
$traceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
Write-Log "=== System Audit Team Mode Started ===" "INFO"
Write-Log "Trace ID: $traceId" "INFO"

# ============================================
# Phase 0: Circuit Breaker 預檢查
# ============================================

Write-Log "Phase 0: Circuit Breaker precheck..." "INFO"

# 載入預檢查工具
$utilsPath = "$AgentDir\circuit-breaker-utils.ps1"
$knowledgeAvailable = $true

if (Test-Path $utilsPath) {
    . $utilsPath
    Write-Log "  Loaded circuit-breaker-utils.ps1" "INFO"

    # 檢查 knowledge API 狀態（用於 RAG 寫入）
    $knowledgeState = Test-CircuitBreaker "knowledge"

    if ($knowledgeState -eq "open") {
        Write-Log "  ✗ Knowledge API is OPEN - RAG import will be skipped" "WARN"
        $knowledgeAvailable = $false
    }
    elseif ($knowledgeState -eq "half_open") {
        Write-Log "  ⚠ Knowledge API is HALF_OPEN - RAG import will proceed (trial)" "WARN"
    }
    else {
        Write-Log "  ✓ Knowledge API is CLOSED - RAG import will proceed" "INFO"
    }
}
else {
    Write-Log "  circuit-breaker-utils.ps1 not found, skipping precheck" "WARN"
}

# Set environment variable to inform Phase 2 assembly agent
if ($knowledgeAvailable) {
    $env:KNOWLEDGE_API_AVAILABLE = "1"
}
else {
    $env:KNOWLEDGE_API_AVAILABLE = "0"
}

# ============================================
# Phase 1: Parallel Audit (4 Agents)
# ============================================

Write-Log "Phase 1: Starting 4 parallel audit agents..." "INFO"
$phase1Start = Get-Date
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "running" -AgentType "system-audit"
# OODA: 系統審查 = Orient 階段
Set-OodaState -Step "orient" -Status "running" -Meta @{ trigger = "scheduled" }

$phase1Jobs = @()
$phase1Prompts = @(
    @{ Name = "dim1-5"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim1-5.md" },
    @{ Name = "dim2-6"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim2-6.md" },
    @{ Name = "dim3-7"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim3-7.md" },
    @{ Name = "dim4"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim4.md" }
)

foreach ($agent in $phase1Prompts) {
    $promptContent = Strip-Frontmatter (Get-Content -Path $agent.Prompt -Raw -Encoding UTF8)
    $job = Start-Job -ScriptBlock {
        param($promptContent, $agentDir, $agentName, $logDir, $timestamp, $traceId, $apiToken)

        # 明確設定 Process 級別環境變數（會傳遞到子 process）
        [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
        [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
        [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase1", "Process")
        [System.Environment]::SetEnvironmentVariable("AGENT_NAME", $agentName, "Process")
        if ($apiToken) {
            [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
        }

        Set-Location $agentDir
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        Write-Host "[$agentName] Starting audit..." -ForegroundColor Cyan

        $stderrFile = "$logDir\$agentName-stderr-$timestamp.log"
        $output = $promptContent | claude -p --allowedTools "Read,Bash,Glob,Grep,Write" 2>$stderrFile

        # 執行成功且 stderr 為空 → 刪除
        if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
            $stderrSize = (Get-Item $stderrFile).Length
            if ($stderrSize -eq 0) {
                Remove-Item $stderrFile -Force
            }
        }

        Write-Host "[$agentName] Completed" -ForegroundColor Green
        return @{
            Name = $agentName
            Output = $output
            ExitCode = $LASTEXITCODE
        }
    } -ArgumentList $promptContent, $AgentDir, $agent.Name, $LogDir, $timestamp, $traceId, $todoistToken -WorkingDirectory $AgentDir

    $phase1Jobs += @{
        Job = $job
        Name = $agent.Name
    }
}

Write-Log "Waiting for Phase 1 agents to complete (timeout: $Phase1TimeoutSeconds seconds)..." "INFO"

# Wait for all Phase 1 jobs
$phase1Results = @()
$phase1Success = $true

foreach ($jobInfo in $phase1Jobs) {
    $job = $jobInfo.Job
    $name = $jobInfo.Name

    $completed = Wait-Job -Job $job -Timeout $Phase1TimeoutSeconds

    if ($null -eq $completed) {
        Write-Log "Phase 1 agent $name timed out" "ERROR"
        Stop-Job -Job $job
        Remove-Job -Job $job -Force
        $phase1Success = $false
    } else {
        $result = Receive-Job -Job $job
        Remove-Job -Job $job -Force

        $phase1Results += $result
        Write-Log "Phase 1 agent $name completed (exit code: $($result.ExitCode))" "INFO"

        # Save output to log
        $result.Output | Out-File -FilePath $phase1LogFile -Append -Encoding UTF8
    }
}

# Check if all Phase 1 agents succeeded
if (-not $phase1Success) {
    Write-Log "Phase 1 failed - some agents timed out" "ERROR"
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "failed" -AgentType "system-audit" -Detail "timeout or missing result files"
    Update-SchedulerState -Status "error" -Message "Phase 1 timeout" -ExitCode 1
    exit 1
}

# Verify Phase 1 outputs
$expectedResults = @("dim1-5", "dim2-6", "dim3-7", "dim4")
foreach ($expected in $expectedResults) {
    $resultFile = "$ResultsDir\audit-$expected.json"
    if (-not (Test-Path $resultFile)) {
        Write-Log "Phase 1 result missing: $resultFile" "ERROR"
        $phase1Success = $false
    }
}

if (-not $phase1Success) {
    Write-Log "Phase 1 failed - missing result files" "ERROR"
    Update-SchedulerState -Status "error" -Message "Phase 1 incomplete" -ExitCode 1
    exit 1
}

$phase1Seconds = [int]((Get-Date) - $phase1Start).TotalSeconds
Write-Log "Phase 1 completed successfully (${phase1Seconds}s)" "INFO"
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase1" -State "completed" -AgentType "system-audit" -Detail "4 agents completed"
# Level 3-A: Phase 1 span
Write-Span -TraceId $traceId -SpanType "phase" -Phase "phase1" `
    -StartTime $phase1Start -EndTime (Get-Date) -Status "ok"

# Clean up stderr files from Phase 1
Get-ChildItem "$LogDir\*-stderr-*.log" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-StderrIfBenign $_.FullName
}

# ============================================
# Phase 2: Assembly & Fixing
# ============================================

Write-Log "Phase 2: Starting assembly agent..." "INFO"
$phase2Start = Get-Date
Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "running" -AgentType "system-audit"

$phase2Prompt = "$AgentDir\prompts\team\assemble-audit.md"
$phase2Attempt = 1
$maxPhase2Attempts = $MaxPhase2Retries + 1
$phase2Success = $false
$phase2Seconds = 0

while ($phase2Attempt -le $maxPhase2Attempts -and -not $phase2Success) {
    if ($phase2Attempt -gt 1) {
        Write-Log "Phase 2 retry attempt $phase2Attempt of $maxPhase2Attempts after 60 seconds delay..." "WARN"
        Start-Sleep -Seconds 60
    }

    try {
        $phase2Content = Strip-Frontmatter (Get-Content -Path $phase2Prompt -Raw -Encoding UTF8)
        $job = Start-Job -ScriptBlock {
            param($phase2Content, $agentDir, $logDir, $timestamp, $traceId, $apiToken)

            # 明確設定 Process 級別環境變數（會傳遞到子 process）
            [System.Environment]::SetEnvironmentVariable("CLAUDE_TEAM_MODE", "1", "Process")
            [System.Environment]::SetEnvironmentVariable("DIGEST_TRACE_ID", $traceId, "Process")
            [System.Environment]::SetEnvironmentVariable("AGENT_PHASE", "phase2", "Process")
            [System.Environment]::SetEnvironmentVariable("AGENT_NAME", "assemble-audit", "Process")
            if ($apiToken) {
                [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", $apiToken, "Process")
            }

            Set-Location $agentDir
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $OutputEncoding = [System.Text.Encoding]::UTF8

            $stderrFile = "$logDir\assemble-stderr-$timestamp.log"
            $output = $phase2Content | claude -p --allowedTools "Read,Bash,Glob,Grep,Write,Edit" 2>$stderrFile

            # 執行成功且 stderr 為空 → 刪除
            if ($LASTEXITCODE -eq 0 -and (Test-Path $stderrFile)) {
                $stderrSize = (Get-Item $stderrFile).Length
                if ($stderrSize -eq 0) {
                    Remove-Item $stderrFile -Force
                }
            }

            return $output
        } -ArgumentList $phase2Content, $AgentDir, $LogDir, $timestamp, $traceId, $todoistToken -WorkingDirectory $AgentDir

        $completed = Wait-Job -Job $job -Timeout $Phase2TimeoutSeconds

        if ($null -eq $completed) {
            Write-Log "Phase 2 timed out after $Phase2TimeoutSeconds seconds" "ERROR"
            Stop-Job -Job $job
            Remove-Job -Job $job -Force
            $phase2Attempt++
            continue
        }

        $output = Receive-Job -Job $job
        Remove-Job -Job $job -Force

        # Clean up Phase 2 stderr
        Get-ChildItem "$LogDir\assemble-stderr-*.log" -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-StderrIfBenign $_.FullName
        }

        # Save output to log
        $output | Out-File -FilePath $phase2LogFile -Encoding UTF8

        # Check if successful (look for completion indicators)
        $outputStr = $output -join "`n"
        if ($outputStr -match "審查完成|Step 8.*清理|知識庫.*成功|state/last-audit.json.*已更新") {
            $phase2Seconds = [int]((Get-Date) - $phase2Start).TotalSeconds
            Write-Log "Phase 2 completed successfully (${phase2Seconds}s)" "INFO"
            $phase2Success = $true
            Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "completed" -AgentType "system-audit"

            # OODA: Orient 完成（Decide 由 Phase 3 執行；不再因 backlog 空而預先標記 skipped）
            Set-OodaState -Step "orient" -Status "completed"
            $backlogFileOODA = Join-Path $AgentDir "context\improvement-backlog.json"
            $blTotal = 0
            $blPending = 0
            if (Test-Path $backlogFileOODA) {
                try {
                    $bl = Get-Content $backlogFileOODA -Raw -Encoding UTF8 | ConvertFrom-Json
                    $blTotal = @($bl.items).Count
                    $blPending = @($bl.items | Where-Object { $_.status -eq "pending" }).Count
                } catch {
                    Write-Log "[OODA] 無法解析 improvement-backlog.json: $_"
                }
            }
            Write-Log "[OODA] orient 完成；backlog items=$blTotal pending=$blPending（Phase 3 arch-evolution 依冷卻與 prompt 處理空清單）" "INFO"

            # ─── Circuit Breaker 自動更新（knowledge API）───
            if ($knowledgeAvailable) {
                if (Get-Command Update-CircuitBreaker -ErrorAction SilentlyContinue) {
                    Update-CircuitBreaker -ApiName "knowledge" -Success $true
                    Write-Log "Circuit Breaker knowledge 更新: success（Phase 2 完成）" "INFO"
                }
            }
        } else {
            Write-Log "Phase 2 completed but may have issues" "WARN"
            if ($phase2Attempt -eq $maxPhase2Attempts) {
                # Last attempt, accept as success
                $phase2Success = $true
            }
        }
    } catch {
        Write-Log "Error in Phase 2: $_" "ERROR"
        if ($phase2Attempt -eq $maxPhase2Attempts) {
            Update-SchedulerState -Status "error" -Message $_.Exception.Message -ExitCode 1
        }
    }

    $phase2Attempt++
}

if (-not $phase2Success) {
    Write-Log "Phase 2 failed after $maxPhase2Attempts attempts" "ERROR"
    Set-FsmState -RunId $traceId.Substring(0, 8) -Phase "phase2" -State "failed" -AgentType "system-audit" -Detail "failed after $maxPhase2Attempts attempts"
    Set-OodaState -Step "orient" -Status "failed" -Meta @{ error = "phase2_failed" }
    Update-SchedulerState -Status "error" -Message "Phase 2 failed" -ExitCode 1
    exit 1
}

# ============================================
# Phase 3: Decide（arch-evolution，審查後積極觸發；backlog 空／缺檔由 prompt 內建處理）
# ============================================
Write-Host "[Phase 3] OODA Decide 階段" -ForegroundColor Cyan
$script:phase3Ran = $false
$phase3Seconds = 0

$backlogFile     = Join-Path $AgentDir "context\improvement-backlog.json"
$archDecisionFile = Join-Path $AgentDir "context\arch-decision.json"
$archPromptFile  = Join-Path $AgentDir "prompts\team\todoist-auto-arch_evolution.md"

# 節流：僅當 arch-decision.json 的 generated_at 距今短於冷卻時間時跳過（取代「當日僅一次」）
$skipPhase3Cooldown = $false
$ageMin = 0
$cooldownMins = [int]$Phase3ArchDecisionCooldownMinutes
if ($cooldownMins -gt 0 -and (Test-Path $archDecisionFile)) {
    try {
        $ad = Get-Content $archDecisionFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
        if ($ad.generated_at) {
            $genDto = ConvertTo-DateTimeOffsetFromAuditJson $ad.generated_at
            if ($null -ne $genDto) {
                $ageMin = [int]([datetimeoffset]::UtcNow - $genDto).TotalMinutes
                if ($ageMin -lt 0) { $ageMin = 0 }
                if ($ageMin -lt $cooldownMins) {
                    $skipPhase3Cooldown = $true
                }
            } else {
                Write-Log "[Phase 3] arch-decision generated_at 無法解析為時間，不套用冷卻" "WARN"
            }
        }
    } catch {
        Write-Log "[Phase 3] arch-decision.json 解析失敗，不套用冷卻: $_" "WARN"
    }
}

# 審查有落地修正或總分退步 → 略過冷卻（仍防一般重複觸發）
if ($skipPhase3Cooldown) {
    $auditLastPath = Join-Path $AgentDir "state\last-audit.json"
    $cooldownBypass = Get-AuditPhase3CooldownBypass -LastAuditPath $auditLastPath
    if ($cooldownBypass.Bypass) {
        Write-Host ("  [Phase 3] 冷卻略過：{0}，仍執行 arch-evolution" -f $cooldownBypass.Reason) -ForegroundColor Cyan
        Write-Log "[Phase 3] Cooldown overridden: $($cooldownBypass.Reason)" "INFO"
        $skipPhase3Cooldown = $false
    }
}

if ($skipPhase3Cooldown) {
    $ageMinShow = $ageMin
    Write-Host ("  [Phase 3] arch-decision 距今 {0} 分鐘（冷卻 {1} 分鐘），跳過 arch-evolution" -f $ageMinShow, $cooldownMins) -ForegroundColor Yellow
    Write-Log "[Phase 3] Skipped: arch-decision cooldown (${ageMinShow}m < ${cooldownMins}m)" "INFO"
    Set-OodaState -Step "decide" -Status "skipped" -Meta @{ reason = "arch_decision_cooldown"; age_minutes = $ageMinShow; cooldown_minutes = $cooldownMins }
}

if (-not $skipPhase3Cooldown) {
    if (-not (Test-Path $archPromptFile)) {
        Write-Host "  [Phase 3] arch-evolution prompt 不存在，跳過" -ForegroundColor Yellow
        Write-Log "[Phase 3] Skipped: $archPromptFile not found" "WARN"
        Set-OodaState -Step "decide" -Status "skipped" -Meta @{ reason = "arch_prompt_missing" }
    } else {
        $blCount = -1
        if (Test-Path $backlogFile) {
            try {
                $backlog = Get-Content $backlogFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
                $blCount = @($backlog.items).Count
            } catch {
                Write-Log "[Phase 3] improvement-backlog.json 解析失敗，仍執行 arch-evolution（由 prompt 處理）: $_" "WARN"
                $blCount = -1
            }
        } else {
            Write-Log "[Phase 3] improvement-backlog.json 不存在，仍執行 arch-evolution（由 prompt 告警路徑處理）" "INFO"
            $blCount = -1
        }
        if ($blCount -ge 0) {
            Write-Host ("  [Phase 3] improvement-backlog items={0}，觸發 arch-evolution…" -f $blCount) -ForegroundColor Green
        } else {
            Write-Host "  [Phase 3] improvement-backlog 狀態未知，仍觸發 arch-evolution…" -ForegroundColor Green
        }

        Set-OodaState -Step "decide" -Status "pending" -Meta @{ triggered_by = "phase3_direct"; backlog_items = $blCount }

        $archLogFile = "$AgentDir\logs\phase3-arch-$($traceId.Substring(0,8)).log"
        $phase3Start = Get-Date

        try {
            $archContent = Strip-Frontmatter (Get-Content $archPromptFile -Raw -Encoding UTF8)
            Write-Log "[Phase 3] Starting arch-evolution (direct trigger, aggressive follow-through)" "INFO"

            $archContent | claude -p --allowedTools "Read,Write,Edit,Bash,Glob,Grep" 2>$archLogFile
            $archExit = $LASTEXITCODE
            $phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
            if ($archExit -ne 0) {
                Write-Host ("  [Phase 3] arch-evolution 失敗：claude 結束代碼 {0}" -f $archExit) -ForegroundColor Red
                Write-Log "[Phase 3] arch-evolution failed: claude exit code $archExit (${phase3Seconds}s)" "ERROR"
                Set-OodaState -Step "decide" -Status "failed" -Meta @{ error = "claude_exit_$archExit"; duration_s = $phase3Seconds }
            } else {
                Write-Host ("  [Phase 3] arch-evolution 完成（{0}s）" -f $phase3Seconds) -ForegroundColor Green
                Write-Log "[Phase 3] arch-evolution completed in ${phase3Seconds}s" "INFO"
                Set-OodaState -Step "decide" -Status "completed" -Meta @{
                    duration_s    = $phase3Seconds
                    output_file   = "context/arch-decision.json"
                }
                $script:phase3Ran = $true
            }
        } catch {
            $phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
            Write-Host "  [Phase 3] arch-evolution 失敗：$_" -ForegroundColor Red
            Write-Log "[Phase 3] arch-evolution failed: $_" "ERROR"
            Set-OodaState -Step "decide" -Status "failed" -Meta @{ error = $_.ToString() }
            # Phase 3 失敗不中止整體流程（orient 已成功）
        }
    }
}

# ============================================
# Phase 4: Act（self-heal，Phase 3 執行後直接觸發）
# ============================================
# 僅在 Phase 3 實際執行 arch-evolution 後觸發，讓 immediate_fix 在同一輪完成，無需等待 round-robin。
$phase4Ran = $false
$phase4Seconds = 0
if ($script:phase3Ran -eq $true) {
    $selfHealPromptFile = Join-Path $AgentDir "prompts\team\todoist-auto-self_heal.md"
    if (Test-Path $selfHealPromptFile) {
        Write-Host "[Phase 4] OODA Act 階段（self-heal）" -ForegroundColor Cyan
        $phase4LogFile = "$AgentDir\logs\phase4-selfheal-$($traceId.Substring(0,8)).log"
        $phase4Start = Get-Date
        try {
            $selfHealContent = Strip-Frontmatter (Get-Content $selfHealPromptFile -Raw -Encoding UTF8)
            Write-Log "[Phase 4] Starting self-heal (direct trigger after arch-evolution)" "INFO"
            $selfHealContent | claude -p --allowedTools "Read,Write,Edit,Bash,Glob,Grep" 2>$phase4LogFile
            $shExit = $LASTEXITCODE
            $phase4Seconds = [int]((Get-Date) - $phase4Start).TotalSeconds
            if ($shExit -ne 0) {
                Write-Host ("  [Phase 4] self-heal 失敗：claude 結束代碼 {0}" -f $shExit) -ForegroundColor Red
                Write-Log "[Phase 4] self-heal failed: claude exit code $shExit (${phase4Seconds}s)" "ERROR"
            } else {
                Write-Host ("  [Phase 4] self-heal 完成（{0}s）" -f $phase4Seconds) -ForegroundColor Green
                Write-Log "[Phase 4] self-heal completed in ${phase4Seconds}s" "INFO"
                $phase4Ran = $true
            }
        } catch {
            $phase4Seconds = [int]((Get-Date) - $phase4Start).TotalSeconds
            Write-Host "  [Phase 4] self-heal 失敗：$_" -ForegroundColor Red
            Write-Log "[Phase 4] self-heal failed: $_" "ERROR"
        }
    } else {
        Write-Host "  [Phase 4] self-heal prompt 不存在，跳過" -ForegroundColor Yellow
        Write-Log "[Phase 4] Skipped: $selfHealPromptFile not found" "WARN"
    }
}

# ============================================
# Completion
# ============================================

Write-Log "=== System Audit Team Mode Completed ===" "INFO"
Write-Log "Phase 1 log: $phase1LogFile" "INFO"
Write-Log "Phase 2 log: $phase2LogFile" "INFO"
$phase3LogCandidate = "$AgentDir\logs\phase3-arch-$($traceId.Substring(0,8)).log"
if ($script:phase3Ran -and (Test-Path $phase3LogCandidate)) {
    Write-Log "Phase 3 log: $phase3LogCandidate" "INFO"
}
if ($phase4Ran -and (Test-Path variable:phase4LogFile)) {
    Write-Log "Phase 4 log: $phase4LogFile" "INFO"
}

# 若 phase2 未成功賦值，用外層計時估算
if ($phase2Seconds -eq 0) {
    $phase2Seconds = [int]((Get-Date) - $phase2Start).TotalSeconds
}

# Check if audit state was updated
$auditStateFile = "$AgentDir\state\last-audit.json"
if (Test-Path $auditStateFile) {
    $auditState = Get-Content $auditStateFile -Encoding UTF8 | ConvertFrom-Json
    Write-Log "Audit score: $($auditState.total_score) (Grade: $($auditState.grade))" "INFO"
    if ($auditState.fixes_applied) {
        Write-Log "Auto-fixes applied: $($auditState.fixes_applied)" "INFO"
    }
}

$totalAuditSeconds = [int]((Get-Date) - $auditStartTime).TotalSeconds
$phaseBreakdown = [PSCustomObject]@{
    phase1_seconds  = $phase1Seconds
    phase2_seconds  = $phase2Seconds
    phase3_seconds  = if ($script:phase3Ran) { $phase3Seconds } else { 0 }
    phase4_seconds  = if ($phase4Ran) { $phase4Seconds } else { 0 }
    total_seconds   = $totalAuditSeconds
    phase1_agents   = @("dim1-5", "dim2-6", "dim3-7", "dim4")
}
$phaseLogParts = "Total: ${totalAuditSeconds}s (Phase1: ${phase1Seconds}s + Phase2: ${phase2Seconds}s"
if ($script:phase3Ran) { $phaseLogParts += " + Phase3: ${phase3Seconds}s" }
if ($phase4Ran) { $phaseLogParts += " + Phase4: ${phase4Seconds}s" }
Write-Log "$phaseLogParts)" "INFO"

# Level 3-A: Phase 2 + Overall span
$auditEnd = Get-Date
Write-Span -TraceId $traceId -SpanType "phase" -Phase "phase2" `
    -StartTime $phase2Start -EndTime $auditEnd `
    -Status (if ($phase2Success) { "ok" } else { "failed" })
Write-Span -TraceId $traceId -SpanType "phase" -Phase "overall" `
    -StartTime $auditStartTime -EndTime $auditEnd `
    -Status (if ($phase2Success) { "ok" } else { "failed" })

Update-SchedulerState -Status "success" -Message "Team audit completed" -ExitCode 0 -PhaseBreakdown $phaseBreakdown

# Clean up spans files older than 7 days
Get-ChildItem "$ResultsDir\spans-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force

exit 0
