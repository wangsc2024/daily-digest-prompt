# new-auto-task.ps1 — 一鍵建立新自動任務樣板
# 用法：.\new-auto-task.ps1 -Name "foo-research" -DailyLimit 2 -ExecutionOrder 21
param(
    [Parameter(Mandatory=$true)]
    [string]$Name,
    [int]$DailyLimit = 1,
    [int]$ExecutionOrder = 99
)

$AgentDir = $PSScriptRoot

# 驗證名稱（只允許小寫英文、數字、連字號）
if ($Name -notmatch '^[a-z0-9\-]+$') {
    Write-Host "❌ 名稱只允許小寫英文、數字和連字號（如 foo-research）" -ForegroundColor Red
    exit 1
}

$templatePath = "$AgentDir\templates\auto-tasks\$Name.md"
$teamPromptPath = "$AgentDir\prompts\team\todoist-auto-$Name.md"
$keyUnder = $Name.Replace("-", "_")

# 檢查是否已存在
if ((Test-Path $templatePath) -or (Test-Path $teamPromptPath)) {
    Write-Host "⚠️  以下檔案已存在，請先確認再重新執行：" -ForegroundColor Yellow
    if (Test-Path $templatePath)  { Write-Host "  $templatePath" -ForegroundColor Yellow }
    if (Test-Path $teamPromptPath) { Write-Host "  $teamPromptPath" -ForegroundColor Yellow }
    exit 1
}

# 建立 template
$templateContent = @"
---
name: $Name
version: 1.0.0
description: "TODO: 描述此自動任務的用途"
task_type: $keyUnder
---

# $Name 自動任務

<!-- 請依照專案的 auto-task 模板慣例填寫以下五個步驟 -->

## 步驟 0：去重確認
讀取 ``context/research-registry.json`` 的 ``summary`` 欄位：
- 若最近 3 天 ``recent_3d_topics`` 中已有類似主題 → 跳過，回報「已研究，跳過」
- 否則繼續

## 步驟 1：讀取 Skill
讀取相關 SKILL.md（TODO: 填入 skill 名稱）。

## 步驟 2：執行核心任務
TODO: 填入具體執行步驟。

## 步驟 3：匯入知識庫
用 ``knowledge-query`` Skill 將結果匯入知識庫。

## 步驟 4：更新 Registry
更新 ``context/research-registry.json``：
1. entries 陣列加入新條目 ``{"date":"...", "task_type":"$keyUnder", "topic":"主題", "kb_imported":true, "tags":[...]}``
2. 更新 ``summary.total``（+1）、``summary.by_type.$keyUnder``（+1）
3. 更新 ``summary.recent_3d_topics``（前插新主題，保留最多 10 條）
4. 更新 ``summary.last_updated``（今日日期）

## 步驟 5：輸出結果
以 JSON 格式寫入結果（供 Phase 3 組裝用）。
"@

$teamPromptContent = @"
你是 $Name 自動任務執行 Agent，全程使用正體中文。
讀取 ``templates/shared/preamble.md``，遵守所有規則。

## 任務
執行 ``templates/auto-tasks/$Name.md`` 中定義的自動任務。

## 輸出
用 Write 工具將結果寫入 ``results/todoist-auto-$Name.json``，格式：
\`\`\`json
{
  "agent": "todoist-auto-$Name",
  "task_type": "$keyUnder",
  "status": "success 或 failed",
  "summary": "執行摘要（1-2 句）",
  "kb_imported": true,
  "topic": "本次研究/執行的主題",
  "error": null
}
\`\`\`
"@

# 寫入檔案
Set-Content $templatePath $templateContent -Encoding UTF8
Set-Content $teamPromptPath $teamPromptContent -Encoding UTF8

Write-Host ""
Write-Host "✅ 已建立自動任務樣板：" -ForegroundColor Green
Write-Host "  templates:   $templatePath" -ForegroundColor Cyan
Write-Host "  team prompt: $teamPromptPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 請手動補充以下步驟：" -ForegroundColor Yellow
Write-Host "  1. 編輯 $templatePath（填入核心執行邏輯）"
Write-Host "  2. 在 config/frequency-limits.yaml 新增："
Write-Host "     ${keyUnder}:"
Write-Host "       daily_limit: $DailyLimit"
Write-Host "       execution_order: $ExecutionOrder"
Write-Host "       template: templates/auto-tasks/$Name.md"
Write-Host ""

# 執行一致性驗證
Write-Host "🔍 執行一致性驗證..." -ForegroundColor DarkCyan
uv run python "$AgentDir\hooks\validate_config.py" --check-auto-tasks
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "⚠️  驗證發現問題，請檢查上述輸出並補全 frequency-limits.yaml。" -ForegroundColor Yellow
}
