# ============================================================
# run-podcast-latest-buddhist.ps1
# 每日 15:20 排程：從知識庫選最新教觀綱宗研究筆記，製作 Podcast
# ============================================================
# 用法：
#   pwsh -ExecutionPolicy Bypass -File run-podcast-latest-buddhist.ps1
# ============================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = $PSScriptRoot
$LogDir = Join-Path $AgentDir "logs"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "podcast-buddhist_$Timestamp.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $LogDir "structured") | Out-Null

function Write-Log($Message) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "=== run-podcast-latest-buddhist 啟動 ==="

# ─── Step 1：確認 KB 服務 ───
try {
    $health = Invoke-RestMethod -Uri "http://localhost:3000/api/health" -TimeoutSec 5
    Write-Log "KB 服務正常"
} catch {
    Write-Log "[SKIP] 知識庫服務未啟動，跳過本次執行"
    exit 0
}

# ─── Step 2：搜尋最新教觀綱宗研究筆記 ───
# 策略：以「教觀綱宗」為核心關鍵字做 hybrid search，topK=5
Write-Log "搜尋知識庫中的教觀綱宗研究筆記..."

$searchBody = @{
    query = "教觀綱宗 佛學研究 天台 止觀"
    topK  = 5
} | ConvertTo-Json -Compress

try {
    $searchResult = Invoke-RestMethod `
        -Uri "http://localhost:3000/api/search/hybrid" `
        -Method POST `
        -ContentType "application/json; charset=utf-8" `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($searchBody)) `
        -TimeoutSec 15

    $candidates = $searchResult.results
    if (-not $candidates -or $candidates.Count -eq 0) {
        Write-Log "[WARN] 搜尋未回傳結果，嘗試關鍵字 fallback"
        $candidates = @()
    }
} catch {
    Write-Log "[WARN] 搜尋失敗: $_，嘗試最新筆記 fallback"
    $candidates = @()
}

# Fallback：從最新 20 筆中篩選佛學相關
if ($candidates.Count -eq 0) {
    try {
        $recentNotes = Invoke-RestMethod -Uri "http://localhost:3000/api/notes?limit=20" -TimeoutSec 10
        $candidates = $recentNotes.notes | Where-Object {
            $_.title -match "教觀綱宗|佛學|楞嚴|止觀|天台|禪|修行" -or
            ($_.tags -and ($_.tags | Where-Object { $_ -match "佛學|教觀綱宗|楞嚴|天台|禪修" }))
        }
    } catch {
        Write-Log "[ERROR] 無法取得筆記列表: $_"
        exit 1
    }
}

if (-not $candidates -or $candidates.Count -eq 0) {
    Write-Log "[SKIP] 知識庫中未找到教觀綱宗相關筆記，本次跳過"
    exit 0
}

$targetNote = $candidates[0]
$noteId = $targetNote.id ?? $targetNote.noteId ?? ""
$noteTitle = $targetNote.title ?? "（未知標題）"

if (-not $noteId) {
    Write-Log "[ERROR] 無法取得筆記 ID"
    exit 1
}

Write-Log "目標筆記：[$noteId] $noteTitle"

# ─── Step 3：呼叫 Podcast 工具 ───
Write-Log "--- 呼叫 article-to-podcast.ps1 ---"
$podcastScript = Join-Path $AgentDir "tools\article-to-podcast.ps1"
$resolver = Join-Path $AgentDir "tools\resolve_podcast_series.py"
$seriesNtfy = "淨土學苑"
if (Test-Path $resolver) {
    try {
        $raw = & uv run --project $AgentDir python $resolver --task podcast_jiaoguangzong 2>$null
        if ($null -ne $raw) {
            $t = if ($raw -is [System.Array]) { [string]$raw[-1] } else { [string]$raw }
            if ($t.Trim()) { $seriesNtfy = $t.Trim() }
        }
    } catch {}
}

pwsh -ExecutionPolicy Bypass -File $podcastScript -NoteId $noteId -SeriesDisplayName $seriesNtfy
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Log "=== Podcast 製作完成 ==="
} else {
    Write-Log "[ERROR] Podcast 製作失敗（exit code: $exitCode）"
    exit $exitCode
}
