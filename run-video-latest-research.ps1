# ============================================================
# run-video-latest-research.ps1
# 每日 13:20 排程：從知識庫選最新深度研究報告，製作影片
# ============================================================
# 用法：
#   pwsh -ExecutionPolicy Bypass -File run-video-latest-research.ps1
# ============================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = $PSScriptRoot
$LogDir = Join-Path $AgentDir "logs"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "video-research_$Timestamp.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $LogDir "structured") | Out-Null

function Write-Log($Message) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "=== run-video-latest-research 啟動 ==="

# ─── Step 1：確認 KB 服務 ───
try {
    $health = Invoke-RestMethod -Uri "http://localhost:3000/api/health" -TimeoutSec 5
    Write-Log "KB 服務正常"
} catch {
    Write-Log "[SKIP] 知識庫服務未啟動，跳過本次執行"
    exit 0
}

# ─── Step 2：搜尋最新深度研究報告 ───
# 策略：hybrid search 取 topK=5，優先選 createdAt 最新且匹配的筆記
Write-Log "搜尋知識庫中的深度研究報告..."

$searchBody = @{
    query = "深度研究報告 技術分析 AI 系統設計"
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
        Write-Log "[WARN] 未找到符合條件的深度研究報告，改用最新筆記 fallback"
        $candidates = @()
    }
} catch {
    Write-Log "[WARN] 搜尋失敗: $_，使用最新筆記 fallback"
    $candidates = @()
}

# Fallback：取最新 10 筆，人工篩選含「研究」字樣的筆記
if ($candidates.Count -eq 0) {
    try {
        $recentNotes = Invoke-RestMethod -Uri "http://localhost:3000/api/notes?limit=10" -TimeoutSec 10
        $candidates = $recentNotes.notes | Where-Object {
            $_.title -match "研究|分析|報告|技術|架構" -or
            ($_.tags -and ($_.tags | Where-Object { $_ -match "研究|技術|AI" }))
        }
    } catch {
        Write-Log "[ERROR] 無法取得筆記列表: $_"
        exit 1
    }
}

if (-not $candidates -or $candidates.Count -eq 0) {
    Write-Log "[SKIP] 知識庫中未找到適合的深度研究報告，本次跳過"
    exit 0
}

# 取分數最高（hybrid search）或第一筆（fallback）
$targetNote = $candidates[0]
$noteId = $targetNote.id ?? $targetNote.noteId ?? ""
$noteTitle = $targetNote.title ?? "（未知標題）"

if (-not $noteId) {
    Write-Log "[ERROR] 無法取得筆記 ID"
    exit 1
}

Write-Log "目標筆記：[$noteId] $noteTitle"

# ─── Step 3：呼叫影片工具 ───
Write-Log "--- 呼叫 article-to-video.ps1 ---"
$videoScript = Join-Path $AgentDir "tools\article-to-video.ps1"

pwsh -ExecutionPolicy Bypass -File $videoScript -NoteId $noteId
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Log "=== 影片製作完成 ==="
} else {
    Write-Log "[ERROR] 影片製作失敗（exit code: $exitCode）"
    exit $exitCode
}
