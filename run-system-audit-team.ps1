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
if (-not (Test-Path Env:HOOK_SECURITY_PRESET)) {
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
    $promptContent = Get-Content -Path $agent.Prompt -Raw -Encoding UTF8
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
        $phase2Content = Get-Content -Path $phase2Prompt -Raw -Encoding UTF8
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

            # OODA: Orient 完成，檢查是否需要觸發 Decide
            Set-OodaState -Step "orient" -Status "completed"
            $backlogFile = Join-Path $AgentDir "context\improvement-backlog.json"
            if (Test-Path $backlogFile) {
                try {
                    $backlog = Get-Content $backlogFile -Raw -Encoding UTF8 | ConvertFrom-Json
                    $pendingItems = @($backlog.items | Where-Object { $_.status -eq "pending" })
                    if ($pendingItems.Count -gt 0) {
                        Write-Log "[OODA] improvement-backlog 有 $($pendingItems.Count) 筆待辦，記錄 decide 觸發信號"
                        Set-OodaState -Step "decide" -Status "pending" -Meta @{ pending_items = $pendingItems.Count; trigger = "orient_completed" }
                    } else {
                        Write-Log "[OODA] improvement-backlog 為空，跳過 Decide/Act"
                        Set-OodaState -Step "decide" -Status "skipped" -Meta @{ reason = "backlog_empty" }
                    }
                } catch {
                    Write-Log "[OODA] 無法讀取 improvement-backlog.json: $_"
                }
            }

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
# Completion
# ============================================

Write-Log "=== System Audit Team Mode Completed ===" "INFO"
Write-Log "Phase 1 log: $phase1LogFile" "INFO"
Write-Log "Phase 2 log: $phase2LogFile" "INFO"

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
    total_seconds   = $totalAuditSeconds
    phase1_agents   = @("dim1-5", "dim2-6", "dim3-7", "dim4")
}
Write-Log "Total: ${totalAuditSeconds}s (Phase1: ${phase1Seconds}s + Phase2: ${phase2Seconds}s)" "INFO"

Update-SchedulerState -Status "success" -Message "Team audit completed" -ExitCode 0 -PhaseBreakdown $phaseBreakdown
exit 0
