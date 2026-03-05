# generate-arch-diagrams.ps1 — 從 prompt 文件自動生成三條 Pipeline 的 Mermaid 架構圖
# 用法：.\generate-arch-diagrams.ps1
#       .\generate-arch-diagrams.ps1 -Pipeline daily-digest
param(
    [string]$Pipeline = "all"   # all | daily-digest | todoist | audit
)

$AgentDir = $PSScriptRoot

# 確認 docs/ 目錄存在
if (-not (Test-Path "$AgentDir\docs")) {
    New-Item -ItemType Directory -Path "$AgentDir\docs" | Out-Null
}

# 確認 ARCHITECTURE.md 存在且含有 AUTO-GENERATED 標記
$archFile = "$AgentDir\docs\ARCHITECTURE.md"
if (-not (Test-Path $archFile)) {
    Write-Host "⚠️  docs/ARCHITECTURE.md 不存在，請先建立（P0-A 應已完成）" -ForegroundColor Yellow
    exit 1
}

Write-Host "🏗️  生成架構圖（Pipeline=$Pipeline）..." -ForegroundColor Cyan

# 讀取相關 prompt 文件清單
$filesToRead = @(
    "run-agent-team.ps1",
    "run-todoist-agent-team.ps1",
    "run-system-audit-team.ps1",
    "prompts/team/fetch-todoist.md",
    "prompts/team/fetch-news.md",
    "prompts/team/fetch-hackernews.md",
    "prompts/team/fetch-gmail.md",
    "prompts/team/fetch-security.md",
    "prompts/team/assemble-digest.md",
    "prompts/team/todoist-query.md",
    "prompts/team/todoist-assemble.md",
    "prompts/team/fetch-audit-dim1-5.md",
    "prompts/team/fetch-audit-dim2-6.md",
    "prompts/team/fetch-audit-dim3-7.md",
    "prompts/team/fetch-audit-dim4.md",
    "prompts/team/assemble-audit.md"
)

# 過濾 Pipeline
if ($Pipeline -ne "all") {
    $filesToRead = switch ($Pipeline) {
        "daily-digest" {
            @("run-agent-team.ps1",
              "prompts/team/fetch-todoist.md", "prompts/team/fetch-news.md",
              "prompts/team/fetch-hackernews.md", "prompts/team/fetch-gmail.md",
              "prompts/team/fetch-security.md", "prompts/team/assemble-digest.md")
        }
        "todoist" {
            @("run-todoist-agent-team.ps1",
              "prompts/team/todoist-query.md", "prompts/team/todoist-assemble.md")
        }
        "audit" {
            @("run-system-audit-team.ps1",
              "prompts/team/fetch-audit-dim1-5.md", "prompts/team/fetch-audit-dim2-6.md",
              "prompts/team/fetch-audit-dim3-7.md", "prompts/team/fetch-audit-dim4.md",
              "prompts/team/assemble-audit.md")
        }
        default { $filesToRead }
    }
}

# 讀取現有文件內容（限制各文件前 50 行，避免 prompt 太長）
$fileContents = ""
foreach ($f in $filesToRead) {
    $fullPath = Join-Path $AgentDir $f
    if (Test-Path $fullPath) {
        $lines = Get-Content $fullPath -TotalCount 50 -Encoding UTF8
        $fileContents += "`n`n=== $f ===`n" + ($lines -join "`n")
    }
}

# 建構 claude 指令用的 prompt（存入暫存檔）
$promptContent = @"
你是一個架構圖生成工具，全程輸出繁體中文說明、英文節點 ID。
請閱讀以下專案文件，為每條 Pipeline 生成 Mermaid flowchart 圖。

**要求**：
1. 為以下 Pipeline 各生成一個 Mermaid flowchart LR 圖（僅生成被要求的）：
   - daily-digest（每日摘要）
   - todoist（Todoist 任務規劃）
   - audit（系統審查）
2. 節點代表每個 Agent（fetch-todoist、assemble-digest 等）
3. 邊代表資料流，標示傳遞的檔案（如 results/todoist.json）
4. 用 ``\`\`\`mermaid`` 包裹，可直接貼入 Markdown
5. 每個節點 ID 用英文，顯示名稱用中文（如 ``FT[Fetch Todoist]``）
6. Phase 分組用 subgraph
7. 完整但精簡：每個 Pipeline 圖不超過 25 個節點

**以下是專案文件片段**：
$fileContents

**輸出格式（保持此結構）**：

## Daily Digest Pipeline（每日摘要）

[mermaid 圖]

## Todoist Pipeline（Todoist 任務規劃）

[mermaid 圖]

## System Audit Pipeline（系統審查）

[mermaid 圖]
"@

$promptFile = "$AgentDir\temp_arch_prompt.txt"
$promptContent | Set-Content $promptFile -Encoding UTF8

Write-Host "  呼叫 Claude 生成架構圖..." -ForegroundColor DarkCyan

# 呼叫 claude -p 生成圖表
$diagrams = Get-Content $promptFile -Raw | claude -p --allowedTools "" 2>&1 | Out-String

Remove-Item $promptFile -Force -ErrorAction SilentlyContinue

if ($LASTEXITCODE -ne 0 -or -not $diagrams.Trim()) {
    Write-Host "❌ claude -p 執行失敗或無輸出" -ForegroundColor Red
    exit 1
}

# 注入至 docs/ARCHITECTURE.md 的 AUTO-GENERATED 區段
$arch = Get-Content $archFile -Raw -Encoding UTF8
$markerStart = "<!-- AUTO-GENERATED DIAGRAMS START -->"
$markerEnd   = "<!-- AUTO-GENERATED DIAGRAMS END -->"
$timestamp   = Get-Date -Format "yyyy-MM-dd HH:mm"
$block = "$markerStart`n`n*自動生成於 $timestamp（`.\generate-arch-diagrams.ps1 -Pipeline $Pipeline`）*`n`n$($diagrams.Trim())`n`n$markerEnd"

if ($arch -match [regex]::Escape($markerStart)) {
    $escapedStart = [regex]::Escape($markerStart)
    $escapedEnd   = [regex]::Escape($markerEnd)
    $arch = [regex]::Replace($arch, "(?s)${escapedStart}.*?${escapedEnd}", $block)
} else {
    $arch += "`n`n$block"
}

$arch | Set-Content $archFile -Encoding UTF8
Write-Host "✅ 架構圖已更新至 docs/ARCHITECTURE.md" -ForegroundColor Green
Write-Host "   請用 VSCode Markdown Preview 或 GitHub 查看 Mermaid 圖表" -ForegroundColor DarkCyan
