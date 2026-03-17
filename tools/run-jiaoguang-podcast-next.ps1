# ============================================================
# 淨土教觀學苑 Podcast 依序製作 1 集
# 用於 all_exhausted_fallback：依 docs/plans/淨土教觀學苑podcast專輯.md 題目列表依序製作
# ============================================================
# 用法：pwsh -ExecutionPolicy Bypass -File tools/run-jiaoguang-podcast-next.ps1 [-Backend claude|cursor_cli]
# Backend: claude = 腳本流程（article-to-podcast）；cursor_cli = cursor-cli skill 模型（claude -p 依 prompt 執行）
# 讀取 context/jiaoguang-podcast-next.json 的 next_episode，製作該集後將 next_episode+1 寫回
# ============================================================

param(
    [ValidateSet("claude", "cursor_cli")]
    [string]$Backend = "claude"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$AgentDir = (Get-Item $PSScriptRoot).Parent.FullName
if ((Split-Path -Leaf $PSScriptRoot) -eq "tools") {
    $AgentDir = $PSScriptRoot | Split-Path -Parent
}
Set-Location $AgentDir

$AlbumPath = Join-Path $AgentDir "docs\plans\淨土教觀學苑podcast專輯.md"
$StatePath = Join-Path $AgentDir "context\jiaoguang-podcast-next.json"
$MaxEpisode = 750

# --- 讀取下一集編號 + 每日上限檢查 ---
$next = 1
$state = $null
if (Test-Path $StatePath) {
    try {
        $state = Get-Content $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $next = [int]$state.next_episode
        if ($next -lt 1 -or $next -gt $MaxEpisode) { $next = 1 }
    } catch {
        $next = 1
    }
}

# 每日上限：讀取 frequency-limits.yaml 的 all_exhausted_fallback_daily_limit（預設 3）
$DailyLimit = 3
$FreqLimitsPath = Join-Path $AgentDir "config\frequency-limits.yaml"
if (Test-Path $FreqLimitsPath) {
    try {
        $flContent = Get-Content $FreqLimitsPath -Raw -Encoding UTF8
        if ($flContent -match 'all_exhausted_fallback_daily_limit:\s*(\d+)') {
            $DailyLimit = [int]$Matches[1]
        }
    } catch {}
}

# 計算今日已產出集數
$today = (Get-Date -Format "yyyy-MM-dd")
$todayCount = 0
if ($state -and $state.today_date -eq $today) {
    $todayCount = [int]($state.today_count)
}

if ($todayCount -ge $DailyLimit) {
    Write-Host "[jiaoguang-podcast-next] 今日已達上限 $DailyLimit 集（today_count=$todayCount），跳過。"
    exit 0
}

Write-Host "[jiaoguang-podcast-next] 今日第 $($todayCount + 1)/$DailyLimit 集"

# --- 從專輯 md 取得第 N 列（表格：表頭 27-28 行，第 1 集資料 = 第 29 行 = index 28）---
if (-not (Test-Path $AlbumPath)) {
    Write-Error "專輯不存在: $AlbumPath"
    exit 1
}
$lines = Get-Content $AlbumPath -Encoding UTF8
# 第 N 集資料行 = lines[28 + (N-1)] = lines[27 + N]
$rowIndex = 27 + $next
if ($rowIndex -ge $lines.Count) {
    Write-Host "[WARN] 專輯僅 750 集，下一集 $next 超出；重置為第 1 集"
    $next = 1
    $rowIndex = 28
}
$row = $lines[$rowIndex]
$cells = $row -split '\|' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
# cells[0]=集數, cells[1]=題目名稱, cells[2]=對應課程, ...
$epNum = $cells[0]
$topicName = $cells[1]
if (-not $topicName) {
    Write-Error "無法解析專輯第 $next 列題目: $row"
    exit 1
}

Write-Host "[jiaoguang-podcast-next] Backend=$Backend 製作第 $next 集：$topicName"

$err = $null
if ($Backend -eq "cursor_cli") {
    $promptPath = Join-Path $AgentDir "prompts\team\jiaoguang-podcast-one-episode.md"
    if (-not (Test-Path $promptPath)) {
        Write-Error "找不到 cursor_cli prompt: $promptPath"
        exit 1
    }
    try {
        Get-Content $promptPath -Raw -Encoding UTF8 | claude -p --allowedTools Read,Bash,Write,Edit 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { $err = "cursor_cli (claude -p) 結束碼 $LASTEXITCODE" }
    } catch {
        $err = $_.Exception.Message
    }
} else {
    $Slug = "jiaoguang-ep$next-$(Get-Date -Format 'yyyyMMdd')"
    $PodcastScript = Join-Path $AgentDir "tools\article-to-podcast.ps1"
    if (-not (Test-Path $PodcastScript)) {
        Write-Error "找不到 article-to-podcast.ps1: $PodcastScript"
        exit 1
    }
    try {
        & pwsh -ExecutionPolicy Bypass -File $PodcastScript -Query $topicName -Slug $Slug 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { $err = "article-to-podcast 結束碼 $LASTEXITCODE" }
    } catch {
        $err = $_.Exception.Message
    }
}

# --- 寫回下一集編號 + 今日計數（僅 claude 模式；cursor_cli 由 agent 依 prompt 更新）---
if ($Backend -eq "claude") {
    $nextNext = if ($next -ge $MaxEpisode) { 1 } else { $next + 1 }
    $stateDir = Split-Path -Parent $StatePath
    if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Force -Path $stateDir | Out-Null }
    @{
        next_episode  = $nextNext
        last_produced = $next
        last_topic    = $topicName
        today_date    = $today
        today_count   = $todayCount + 1
        updated_at    = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    } | ConvertTo-Json -Depth 3 | Set-Content -Path $StatePath -Encoding UTF8
}

if ($err) {
    Write-Host "[jiaoguang-podcast-next] 製作完成但發生錯誤: $err"
    exit 1
}
if ($Backend -eq "claude") {
    $nextNext = if ($next -ge $MaxEpisode) { 1 } else { $next + 1 }
    Write-Host "[jiaoguang-podcast-next] 完成；下一集將為第 $nextNext 集"
} else {
    Write-Host "[jiaoguang-podcast-next] 完成（cursor_cli 模式）"
}
exit 0
