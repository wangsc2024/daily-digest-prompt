<#
.SYNOPSIS
  Vite 增量知識庫同步管線（P2-A）— Extract → Transform → Load → Deploy

.DESCRIPTION
  1. 讀取 state/records.json 的 last_kb_sync 時間戳（增量起點）
  2. GET http://localhost:3000/api/notes?updated_after={last_sync}（KB API）
  3. 轉換為靜態 JSON（供 Cloudflare Workers 邊緣部署）
  4. 寫入 workers/podcast-index/data/kb-snapshot.json
  5. 觸發 deploy-podcast-worker.ps1（若存在）
  6. 更新 state/records.json 的 last_kb_sync 時間戳

.PARAMETER DryRun
  只顯示同步計畫，不實際呼叫 API 或部署

.PARAMETER ForceFullSync
  強制全量同步（忽略 last_kb_sync，拉取所有資料）

.EXAMPLE
  # 增量同步
  .\tools\kb-sync-incremental.ps1

  # 強制全量同步
  .\tools\kb-sync-incremental.ps1 -ForceFullSync

  # 模擬執行（不實際呼叫）
  .\tools\kb-sync-incremental.ps1 -DryRun
#>
param(
    [switch]$DryRun,
    [switch]$ForceFullSync
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RecordsPath = Join-Path $RepoRoot "state/records.json"
$SnapshotDir = Join-Path $RepoRoot "workers/podcast-index/data"
$SnapshotPath = Join-Path $SnapshotDir "kb-snapshot.json"
$KbApiBase = "http://localhost:3000"
$StartTime = Get-Date

# ── Step 1：讀取上次同步時間戳 ────────────────────────────────────────────────
$lastSync = $null
if (-not $ForceFullSync -and (Test-Path $RecordsPath)) {
    try {
        $records = Get-Content $RecordsPath -Raw | ConvertFrom-Json
        if ($records -is [PSCustomObject] -and $records.last_kb_sync) {
            $lastSync = $records.last_kb_sync
        } elseif ($records -is [array]) {
            # 舊格式（array），忽略並全量同步
            $lastSync = $null
        }
    } catch {
        Write-Warning "[KB-Sync] 解析 records.json 失敗，改為全量同步"
        $lastSync = $null
    }
}

$syncMode = if ($lastSync) { "增量 (since $lastSync)" } else { "全量" }
Write-Host "[KB-Sync] 開始 $syncMode 同步 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

if ($DryRun) {
    Write-Host "[KB-Sync] DryRun 模式 — 不實際呼叫 API"
    Write-Host "[KB-Sync] 模擬端點：$KbApiBase/api/notes"
    Write-Host "[KB-Sync] 快照目標：$SnapshotPath"
    exit 0
}

# ── Step 2：GET KB API（增量或全量）─────────────────────────────────────────
$apiUrl = if ($lastSync) {
    "$KbApiBase/api/notes?updated_after=$([System.Uri]::EscapeDataString($lastSync))"
} else {
    "$KbApiBase/api/notes"
}

try {
    $response = Invoke-RestMethod -Uri $apiUrl -Method Get -TimeoutSec 30
    $notes = if ($response -is [array]) { $response }
             elseif ($response.results) { $response.results }
             else { @($response) }
    Write-Host "[KB-Sync] 取得 $($notes.Count) 筆筆記"
} catch {
    Write-Warning "[KB-Sync] KB API 不可用（$apiUrl）：$($_.Exception.Message)"
    exit 1
}

if ($notes.Count -eq 0) {
    Write-Host "[KB-Sync] 無新增或更新筆記，跳過部署"
    # 仍更新 last_kb_sync 時間戳
    $syncTime = (Get-Date -Format "o")
    _UpdateRecords $RecordsPath $syncTime 0
    exit 0
}

# ── Step 3：Transform — 轉換為靜態快照格式 ───────────────────────────────────
$snapshot = @{
    generated_at  = (Get-Date -Format "o")
    sync_mode     = $syncMode
    total_notes   = $notes.Count
    notes         = @($notes | ForEach-Object {
        @{
            id       = $_.id
            title    = $_.title
            tags     = $_.tags ?? @()
            summary  = if ($_.content) { $_.content.Substring(0, [Math]::Min(200, $_.content.Length)) } else { "" }
            updated_at = $_.updatedAt ?? $_.updated_at ?? ""
        }
    })
}

# ── Step 4：Load — 寫入快照檔案 ──────────────────────────────────────────────
if (-not (Test-Path $SnapshotDir)) {
    New-Item -ItemType Directory -Path $SnapshotDir -Force | Out-Null
}
$snapshot | ConvertTo-Json -Depth 5 -Compress:$false | Set-Content -Path $SnapshotPath -Encoding UTF8
Write-Host "[KB-Sync] 快照已寫入：$SnapshotPath ($($notes.Count) 筆)"

# ── Step 5：Deploy — 觸發 Cloudflare Workers 部署 ────────────────────────────
$deployScript = Join-Path $RepoRoot "deploy-podcast-worker.ps1"
if (Test-Path $deployScript) {
    Write-Host "[KB-Sync] 觸發 Workers 部署..."
    try {
        & $deployScript
        Write-Host "[KB-Sync] 部署完成"
    } catch {
        Write-Warning "[KB-Sync] 部署失敗（不影響本地快照）：$($_.Exception.Message)"
    }
} else {
    Write-Host "[KB-Sync] deploy-podcast-worker.ps1 不存在，跳過部署"
}

# ── Step 6：更新 state/records.json 同步時間戳 ──────────────────────────────
$syncTime = (Get-Date -Format "o")
function _UpdateRecords {
    param([string]$path, [string]$syncAt, [int]$count)
    try {
        $data = if (Test-Path $path) {
            $raw = Get-Content $path -Raw | ConvertFrom-Json
            if ($raw -is [array]) { @{} }      # 舊 array 格式，重置為 dict
            else { $raw }
        } else { @{} }

        if ($data -isnot [hashtable]) {
            $data = @{}
        }
        $data.last_kb_sync    = $syncAt
        $data.last_sync_count = $count
        $data | ConvertTo-Json -Depth 3 | Set-Content -Path $path -Encoding UTF8
    } catch {
        Write-Warning "[KB-Sync] 更新 records.json 失敗：$($_.Exception.Message)"
    }
}

_UpdateRecords $RecordsPath $syncTime $notes.Count

$elapsed = [math]::Round(((Get-Date) - $StartTime).TotalSeconds, 1)
Write-Host "[KB-Sync] 完成 — 同步 $($notes.Count) 筆，耗時 ${elapsed}s"
