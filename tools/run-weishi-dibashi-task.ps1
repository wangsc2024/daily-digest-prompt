# ============================================================
# 唯識第八識任務：匯入知識庫 + 製作 Podcast + 上傳 R2
# 依 temp/cursor-cli-task-weishi-dibashi.md 執行
# ============================================================

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$AgentDir = (Get-Item $PSScriptRoot).Parent.FullName

Set-Location $AgentDir

Write-Host "=== 唯識第八識任務 ===`n"

# --- Step 0: 確認報告存在 ---
$Report = Join-Path $AgentDir "docs\research\唯識第八識深度洞察報告_20260314.md"
if (-not (Test-Path $Report)) {
    Write-Error "報告不存在: $Report"
    exit 1
}
Write-Host "[1/4] 報告存在: $Report`n"

# --- Step 1: 建立 import_note.json ---
Write-Host "[2/4] 建立 import_note.json ..."
uv run --project $AgentDir python tools/create_import_dibashi.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "建立 import_note.json 失敗"
    exit 1
}

# --- Step 2: 匯入知識庫 ---
Write-Host "`n[3/4] 匯入知識庫 ..."
try {
    $importResult = Invoke-RestMethod -Uri "http://localhost:3000/api/import" -Method POST `
        -ContentType "application/json; charset=utf-8" `
        -InFile "import_note.json" `
        -TimeoutSec 30
    Write-Host "匯入成功: $($importResult.message)"
    $noteIds = $importResult.result.noteIds
} catch {
    Write-Host "[WARN] 知識庫匯入失敗（localhost:3000 可能未啟動）: $_"
    Write-Host "請先啟動知識庫服務，然後手動執行："
    Write-Host "  1. uv run python tools/create_import_dibashi.py"
    Write-Host "  2. curl -s -X POST `"http://localhost:3000/api/import`" -H `"Content-Type: application/json; charset=utf-8`" -d @import_note.json"
    Write-Host "  3. 取得筆記 id 後執行 article-to-podcast.ps1 -Slug weishi-dibashi-20260314"
    exit 1
}

# --- 取得筆記 id ---
$NoteId = ""
if ($noteIds -and $noteIds.Count -gt 0) {
    $NoteId = $noteIds[0]
    Write-Host "新筆記 id: $NoteId"
} else {
    $notes = Invoke-RestMethod -Uri "http://localhost:3000/api/notes?limit=5" -Method GET
    $notesList = if ($notes -is [Array]) { $notes } else { $notes.notes ?? $notes.results ?? @() }
    if ($notesList.Count -gt 0) {
        $NoteId = $notesList[0].id
        Write-Host "從最近筆記取得 id: $NoteId"
    }
}

if (-not $NoteId) {
    Write-Error "無法取得筆記 id"
    exit 1
}

Remove-Item "import_note.json" -Force -ErrorAction SilentlyContinue

# --- Step 3: 製作 Podcast 並上傳 R2 ---
Write-Host "`n[4/4] 製作 Podcast ..."
pwsh -ExecutionPolicy Bypass -File "tools\article-to-podcast.ps1" -NoteId $NoteId -Slug "weishi-dibashi-20260314"

Write-Host "`n=== 任務完成 ==="
