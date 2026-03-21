#Requires -Version 7
<#
.SYNOPSIS
  執行 Agent Harness 自治週期：build_plan + enqueue_recovery + recovery_worker 消費佇列。
.DESCRIPTION
  依 docs/deployment/agent-harness-autonomy-deployment_20260320.md 建議，
  每 5 分鐘執行一次，形成監控與恢復閉環。
  建議由 HEARTBEAT.md 排程驅動。
.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File run-autonomous-harness.ps1
#>
$ErrorActionPreference = "Stop"
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AgentDir

# Phase 1: build plan + enqueue
& uv run python tools/autonomous_harness.py --format json | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "[AutonomousHarness] build_plan failed, exit=$LASTEXITCODE"
    exit $LASTEXITCODE
}

# Phase 2: consume recovery queue
& uv run python tools/autonomous_recovery_worker.py | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "[AutonomousHarness] recovery_worker failed, exit=$LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "[AutonomousHarness] cycle completed"
