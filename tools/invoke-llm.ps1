<#
.SYNOPSIS
  LLM 路由呼叫器 — 讀取 llm-router.yaml 後決定打 Groq 或 Claude

.DESCRIPTION
  透過 tools/llm_router.py 取得路由決策，再依 provider 分派。
  Groq 路徑：直接回傳 Relay 結果字串。
  Claude 路徑：若有 -ClaudePromptFile，執行 claude -p；否則回傳決策物件。

.PARAMETER TaskType
  對應 llm-router.yaml 的 task_type（如 news_summary、research_synthesis）

.PARAMETER InputText
  要處理的文字（與 -InputFile 二選一）

.PARAMETER InputFile
  從檔案讀取輸入（優先於 -InputText）

.PARAMETER ClaudePromptFile
  若路由到 Claude，傳入的 prompt 檔路徑（用於 claude -p）

.PARAMETER DryRun
  只顯示路由決策，不實際呼叫

.EXAMPLE
  # 新聞摘要 → 自動路由到 Groq
  .\tools\invoke-llm.ps1 -TaskType "news_summary" -InputText "ByteDance releases DeerFlow 2.0"

  # 研究合成 → 自動路由到 Claude
  .\tools\invoke-llm.ps1 -TaskType "research_synthesis" -ClaudePromptFile "prompts/research.md"

  # 只查路由決策
  .\tools\invoke-llm.ps1 -TaskType "en_to_zh" -DryRun
#>
param(
    [Parameter(Mandatory)][string]$TaskType,
    [string]$InputText = "",
    [string]$InputFile = "",
    [string]$ClaudePromptFile = "",
    [switch]$DryRun
)

$RepoRoot = Split-Path -Parent $PSScriptRoot

# Step 1：組裝 Python Router 參數
$routerArgs = @("--task-type", $TaskType)
if ($InputFile -and (Test-Path $InputFile)) {
    $routerArgs += "--input-file", $InputFile
} elseif ($InputText) {
    $routerArgs += "--input", $InputText
}
if ($DryRun) { $routerArgs += "--dry-run" }

# Step 2：呼叫 Python Router 取得路由決策
$routerOutput = uv run --project $RepoRoot python "$PSScriptRoot/llm_router.py" @routerArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "[LLM-Router] llm_router.py 執行失敗：$routerOutput"
    return $null
}

try {
    $decision = $routerOutput | ConvertFrom-Json
} catch {
    Write-Warning "[LLM-Router] 無法解析 Router 輸出：$routerOutput"
    return $null
}

# Step 3：依決策分派
switch ($decision.provider) {
    "groq" {
        Write-Host "[LLM-Router] ✓ Groq ($($decision.model)) task=$TaskType cached=$($decision.cached)"
        return $decision.result
        break
    }
    "claude" {
        Write-Host "[LLM-Router] → Claude task=$TaskType ($($decision.rationale))"
        if ($DryRun) {
            return $decision
        }
        if ($ClaudePromptFile -and (Test-Path $ClaudePromptFile)) {
            return claude -p $ClaudePromptFile
        }
        # 無 prompt 檔：回傳決策供呼叫方自行處理
        return $decision
        break
    }
    "budget_suspended" {
        Write-Warning "[LLM-Router] ⛔ 預算暫停 reason=$($decision.reason) utilization=$($decision.utilization)"
        return $null
        break
    }
    "fallback_skipped" {
        Write-Warning "[LLM-Router] ⚠ Groq 不可用，動作=$($decision.action)，錯誤=$($decision.error)"
        return $null
        break
    }
    default {
        Write-Warning "[LLM-Router] 未知 provider=$($decision.provider)"
        return $null
        break
    }
}
