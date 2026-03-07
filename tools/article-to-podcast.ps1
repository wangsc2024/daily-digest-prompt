# ============================================================
# tools/article-to-podcast.ps1
# Podcast 生成工具：知識庫文章 → 雙主持人對話 MP3
# ============================================================
# 用法：
#   pwsh -ExecutionPolicy Bypass -File tools/article-to-podcast.ps1 -NoteId "6c25f7f9"
#   pwsh -ExecutionPolicy Bypass -File tools/article-to-podcast.ps1 -Query "Remotion 影片自動化"
# ============================================================

param(
    [string]$NoteId = "",
    [string]$Query = "",
    [string]$Slug = "",
    [string]$Model = "claude-sonnet-4-5"
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ─── 參數驗證 ───
if (-not $NoteId -and -not $Query) {
    Write-Error "請提供 -NoteId <筆記ID> 或 -Query <搜尋關鍵字>"
    exit 1
}

# ─── 路徑設定 ───
$AgentDir = Split-Path -Parent $PSScriptRoot
if ((Split-Path -Leaf $PSScriptRoot) -eq "tools") {
    $AgentDir = $PSScriptRoot | Split-Path -Parent
} else {
    $AgentDir = $PSScriptRoot
}
$ToolsDir = Join-Path $AgentDir "tools"
$LogDir = Join-Path $AgentDir "logs"
$OutputDir = Join-Path $AgentDir "output\podcasts"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$FileTimestamp = Get-Date -Format "yyyyMMddHHmm"

# ─── 短 ID → 完整 UUID 解析 ───
if ($NoteId -and $NoteId.Length -lt 36) {
    try {
        $allNotes = curl -s "http://localhost:3000/api/notes?limit=200" | ConvertFrom-Json
        $notesList = if ($allNotes -is [System.Array]) { $allNotes } else { $allNotes.notes ?? $allNotes.results ?? @() }
        $matched = @($notesList | Where-Object { $_.id -like "$NoteId*" })
        if ($matched.Count -eq 1) {
            $NoteId = $matched[0].id
            Write-Host "[INFO] 短 ID 解析為完整 UUID: $NoteId ($($matched[0].title))"
        } elseif ($matched.Count -gt 1) {
            Write-Error "短 ID '$NoteId' 匹配到 $($matched.Count) 筆筆記，請提供更長的前綴"
            exit 1
        } else {
            Write-Error "短 ID '$NoteId' 未匹配到任何筆記"
            exit 1
        }
    } catch {
        Write-Error "知識庫查詢失敗（短 ID 解析）: $_"
        exit 1
    }
}

# ─── Slug 產生 ───
if (-not $Slug) {
    if ($NoteId) {
        $Slug = "note-$($NoteId.Substring(0, [Math]::Min(8, $NoteId.Length)))-$(Get-Date -Format 'yyyyMMdd')"
    } else {
        $slugBase = $Query -replace "[^\w]", "-" -replace "-+", "-" -replace "^-|-$", ""
        $slugBase = $slugBase.Substring(0, [Math]::Min(20, $slugBase.Length)).ToLower()
        $Slug = "$slugBase-$(Get-Date -Format 'yyyyMMdd')"
    }
}

$ResultsDir = Join-Path $AgentDir "results\article-$Slug"
$AudioDir = Join-Path $ResultsDir "podcast-audio"
$ScriptFile = Join-Path $ResultsDir "podcast-script.jsonl"
$MetaFile = Join-Path $ResultsDir "podcast-meta.json"
$HistoryFile = Join-Path $AgentDir "context\podcast-history.json"

# ─── 建立目錄 ───
foreach ($dir in @($LogDir, (Join-Path $LogDir "structured"), $ResultsDir, $AudioDir, $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$LogFile = Join-Path $LogDir "podcast_$Timestamp.log"

function Write-Log($Message) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "=== Article → Podcast 開始 ==="
Write-Log "Slug: $Slug"
if ($NoteId) { Write-Log "NoteId: $NoteId" }
if ($Query) { Write-Log "Query: $Query" }

# ─── 讀取 Podcast 歷史，建立排除清單（僅 Query 模式有效）───
$UsedNoteIds = "[]"
if ($Query -and (Test-Path $HistoryFile)) {
    try {
        $history = Get-Content $HistoryFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($history.entries) {
            $usedIds = @($history.entries | Where-Object { $_.query -eq $Query } | Select-Object -ExpandProperty note_id)
            if ($usedIds.Count -gt 0) {
                $UsedNoteIds = "[" + ($usedIds | ForEach-Object { "`"$_`"" } | Join-String -Separator ",") + "]"
                Write-Log "已用筆記（排除）：$($usedIds -join ', ')"
            }
        }
    } catch {
        Write-Log "[WARN] 讀取 podcast-history.json 失敗（非致命）: $_"
    }
}

# ============================================================
# Phase 1：Claude Podcast Script Agent
# ============================================================
Write-Log "--- Phase 1: Claude 生成對話腳本 [model: $Model] ---"

$promptTemplate = Get-Content (Join-Path $AgentDir "prompts\article-to-podcast-script.md") -Raw -Encoding UTF8
$prompt = $promptTemplate `
    -replace "\{\{NOTE_ID\}\}", $NoteId `
    -replace "\{\{QUERY\}\}", $Query `
    -replace "\{\{SLUG\}\}", $Slug `
    -replace "\{\{USED_NOTE_IDS\}\}", $UsedNoteIds

$stderrFile = Join-Path $LogDir "podcast-phase1-stderr-$Timestamp.log"
$phase1Start = Get-Date

try {
    $phase1Output = $prompt | claude -p --model $Model --allowedTools "Read,Write,Bash" 2>$stderrFile
    $phase1Success = ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE)
} catch {
    Write-Log "[ERROR] Phase 1 執行失敗: $_"
    $phase1Success = $false
}

$phase1Seconds = [int]((Get-Date) - $phase1Start).TotalSeconds
Write-Log "Phase 1 完成，耗時 ${phase1Seconds}s，成功: $phase1Success"

# 清理空 stderr
if ((Test-Path $stderrFile) -and (Get-Item $stderrFile).Length -eq 0) {
    Remove-Item $stderrFile -Force -ErrorAction SilentlyContinue
}

if (-not $phase1Success -or -not (Test-Path $ScriptFile)) {
    Write-Log "[ERROR] Phase 1 失敗或腳本檔案未生成: $ScriptFile"
    exit 1
}

$turnCount = (Get-Content $ScriptFile -Encoding UTF8 | Where-Object { $_.Trim() }) | Measure-Object | Select-Object -ExpandProperty Count
Write-Log "腳本生成完成，共 $turnCount 段對話"

# 讀取 Phase 1 記錄的筆記 meta（供後續更新歷史）
$selectedNoteId = ""
$selectedNoteTitle = ""
$podcastTitle = ""
if (Test-Path $MetaFile) {
    try {
        $podcastMeta = Get-Content $MetaFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $selectedNoteId    = $podcastMeta.note_id
        $selectedNoteTitle = $podcastMeta.note_title
        $podcastTitle      = $podcastMeta.podcast_title
        Write-Log "選用筆記：$selectedNoteTitle（ID: $selectedNoteId）"
        if ($podcastTitle) { Write-Log "播客主題標題：$podcastTitle" }
    } catch {
        Write-Log "[WARN] 讀取 podcast-meta.json 失敗: $_"
    }
}

# 若 meta 未提供 podcast_title，以 Query 或 note 短 ID 作為後備
if (-not $podcastTitle) {
    $podcastTitle = if ($Query) { $Query } else { "note-$($NoteId.Substring(0, [Math]::Min(8, $NoteId.Length)))" }
    Write-Log "[WARN] podcast_title 未寫入 meta，使用後備值：$podcastTitle"
}

# ============================================================
# Phase 2：雙聲道 TTS 生成
# ============================================================
Write-Log "--- Phase 2: TTS 音訊生成 ---"

$phase2Start = Get-Date
$ttsArgs = @(
    (Join-Path $ToolsDir "generate_podcast_audio.py"),
    "--input", $ScriptFile,
    "--output", $AudioDir,
    "--abbrev-rules", (Join-Path $AgentDir "config\tts-abbreviation-rules.yaml")
)

# 讀取聲音配置
$cfgPath = Join-Path $AgentDir "config\media-pipeline.yaml"
if (Test-Path $cfgPath) {
    # 簡單 grep 取得 voice_a / voice_b（避免需要 Python 解析 YAML）
    $voiceA = (Get-Content $cfgPath | Select-String "voice_a:") -replace '.*voice_a:\s*"?([^"#\s]+)"?.*', '$1'
    $voiceB = (Get-Content $cfgPath | Select-String "voice_b:") -replace '.*voice_b:\s*"?([^"#\s]+)"?.*', '$1'
    if ($voiceA) { $ttsArgs += "--voice-a", $voiceA.Trim() }
    if ($voiceB) { $ttsArgs += "--voice-b", $voiceB.Trim() }
}

uv run --project $AgentDir python @ttsArgs
$phase2Success = ($LASTEXITCODE -eq 0)
$phase2Seconds = [int]((Get-Date) - $phase2Start).TotalSeconds
Write-Log "Phase 2 完成，耗時 ${phase2Seconds}s，成功: $phase2Success"

if (-not $phase2Success) {
    Write-Log "[ERROR] Phase 2 TTS 生成失敗"
    exit 1
}

# ============================================================
# Phase 3：音訊合併 → MP3
# ============================================================
Write-Log "--- Phase 3: 音訊合併 + 正規化 → MP3 ---"

# 以 podcast_title 建立檔名（移除非法字元，限 20 字）
$safeTitle = $podcastTitle -replace '[/\\:*?"<>|\r\n]', '' -replace '\s+', ''
$safeTitle = $safeTitle.Substring(0, [Math]::Min(20, $safeTitle.Length))
$OutFile = Join-Path $OutputDir "${safeTitle}_${FileTimestamp}.mp3"
$phase3Start = Get-Date

$concatArgs = @(
    (Join-Path $ToolsDir "concat_audio.py"),
    "--audio-dir", $AudioDir,
    "--script", $ScriptFile,
    "--output", $OutFile,
    "--config", $cfgPath
)

uv run --project $AgentDir python @concatArgs
$phase3Success = ($LASTEXITCODE -eq 0)
$phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
Write-Log "Phase 3 完成，耗時 ${phase3Seconds}s，成功: $phase3Success"

if (-not $phase3Success) {
    Write-Log "[ERROR] Phase 3 音訊合併失敗"
    exit 1
}

# ============================================================
# Phase 4：儲存對話腳本至知識庫（非致命）
# ============================================================
Write-Log "--- Phase 4: 儲存對話腳本至知識庫 ---"
$phase4Seconds = 0
try {
    $turns = Get-Content $ScriptFile -Encoding UTF8 |
        Where-Object { $_.Trim() } |
        ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
        Where-Object { $_ }

    $kbTitle = "Podcast 腳本：$podcastTitle"

    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.AppendLine("# $kbTitle")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("> 生成時間：$Timestamp | 輸出：``$OutFile``")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## 對話腳本")
    [void]$sb.AppendLine("")
    foreach ($turn in $turns) {
        $label = if ($turn.host -eq "host_a") { "**主持人 A（解說）**" } else { "**主持人 B（提問）**" }
        [void]$sb.AppendLine("${label}：$($turn.text)")
        [void]$sb.AppendLine("")
    }

    $noteBody = @{
        title   = $kbTitle
        content = $sb.ToString()
        source  = "import"
        tags    = @("Podcast製作", "對話腳本", "雙主持人", $Slug)
    } | ConvertTo-Json -Compress -Depth 3

    $phase4Start = Get-Date
    $created = Invoke-RestMethod -Uri "http://localhost:3000/api/notes" -Method POST `
        -ContentType "application/json; charset=utf-8" `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($noteBody)) `
        -TimeoutSec 10
    $phase4Seconds = [int]((Get-Date) - $phase4Start).TotalSeconds
    $kbId = if ($created.id) { $created.id } elseif ($created.noteId) { $created.noteId } else { "unknown" }
    Write-Log "對話腳本已儲存至知識庫，noteId: $kbId，耗時 ${phase4Seconds}s"
} catch {
    Write-Log "[WARN] 儲存知識庫失敗（非致命）: $_"
}

# ============================================================
# Phase 5：上傳至 Cloudflare R2（非致命）
# ============================================================
Write-Log "--- Phase 5: 上傳至 Cloudflare R2 ---"
$phase5Seconds = 0
$publicUrl = ""

try {
    $uploadScript = Join-Path $ToolsDir "upload-podcast.ps1"
    if (-not (Test-Path $uploadScript)) {
        Write-Log "[WARN] 找不到 upload-podcast.ps1，跳過上傳"
    } else {
        $uploadTitle = if ($selectedNoteTitle) { $selectedNoteTitle } elseif ($Query) { $Query } else { $podcastTitle }
        $uploadTopic  = $podcastTitle
        $phase5Start = Get-Date
        $uploadJson = pwsh -ExecutionPolicy Bypass -File $uploadScript -LocalPath $OutFile -Title $uploadTitle -Topic $uploadTopic -Slug $Slug 2>&1 |
            Where-Object { $_ -match '^\{' } | Select-Object -Last 1
        $phase5Seconds = [int]((Get-Date) - $phase5Start).TotalSeconds

        if ($uploadJson) {
            $uploadResult = $uploadJson | ConvertFrom-Json
            if ($uploadResult.url) {
                $publicUrl = $uploadResult.url
                $sizeMB = [math]::Round($uploadResult.size_bytes / 1MB, 1)
                Write-Log "上傳成功：$publicUrl（${sizeMB} MB）耗時 ${phase5Seconds}s"
            } else {
                Write-Log "[WARN] 上傳回傳無 URL：$uploadJson"
            }
        } else {
            Write-Log "[WARN] upload-podcast.ps1 無回傳結果"
        }
    }
} catch {
    Write-Log "[WARN] Phase 5 上傳失敗（非致命）: $_"
}

# ─── 更新 Podcast 歷史記錄（供下次去重使用）───
if ($selectedNoteId -and (Test-Path $OutFile)) {
    try {
        $history = if (Test-Path $HistoryFile) {
            Get-Content $HistoryFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } else {
            [PSCustomObject]@{ version = 1; updated_at = ""; entries = @() }
        }
        if ($null -eq $history.entries) { $history | Add-Member -MemberType NoteProperty -Name entries -Value @() -Force }
        $newEntry = [PSCustomObject]@{
            note_id    = $selectedNoteId
            note_title = $selectedNoteTitle
            query      = $Query
            note_id_input = $NoteId
            slug       = $Slug
            used_at    = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        }
        $updatedHistory = [PSCustomObject]@{
            version    = 1
            updated_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
            entries    = @($history.entries) + $newEntry
        }
        $updatedHistory | ConvertTo-Json -Depth 5 | Set-Content $HistoryFile -Encoding UTF8
        Write-Log "已更新 podcast-history.json（共 $($updatedHistory.entries.Count) 筆）"
    } catch {
        Write-Log "[WARN] 更新 podcast-history.json 失敗（非致命）: $_"
    }
}

# ============================================================
# Phase 6：ntfy 完成通知
# ============================================================
Write-Log "--- Phase 6: ntfy 通知 ---"
try {
    $title = "Podcast 完成：$podcastTitle"
    $sizeMBDisplay = if (Test-Path $OutFile) {
        [math]::Round((Get-Item $OutFile).Length / 1MB, 1)
    } else { "?" }

    $msgLines = @("已生成雙主持人對話 Podcast（${sizeMBDisplay} MB）")
    if ($publicUrl) { $msgLines += "點此播放 $publicUrl" }
    $ntfyMsg = $msgLines -join "`n"

    $ntfyBody = [ordered]@{
        topic   = "wangsc2025"
        title   = $title
        message = $ntfyMsg
        tags    = @("headphones", "white_check_mark")
        priority = 3
    }
    if ($publicUrl) { $ntfyBody["click"] = $publicUrl }

    $ntfyJson = $ntfyBody | ConvertTo-Json -Compress -Depth 3
    $ntfyTmp = Join-Path $LogDir "ntfy_podcast_$Timestamp.json"
    Set-Content -Path $ntfyTmp -Value $ntfyJson -Encoding UTF8

    curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyTmp" https://ntfy.sh | Out-Null
    Remove-Item $ntfyTmp -Force -ErrorAction SilentlyContinue
    Write-Log "ntfy 通知已發送"
} catch {
    Write-Log "[WARN] ntfy 通知失敗（非致命）: $_"
}

$totalSeconds = $phase1Seconds + $phase2Seconds + $phase3Seconds + $phase4Seconds + $phase5Seconds
Write-Log "=== 完成！==="
Write-Log "輸出檔案: $OutFile"
if ($publicUrl) { Write-Log "公開 URL:  $publicUrl" }
Write-Log "總耗時: ${totalSeconds}s（Phase1: ${phase1Seconds}s, Phase2: ${phase2Seconds}s, Phase3: ${phase3Seconds}s, Phase4-KB: ${phase4Seconds}s, Phase5-Upload: ${phase5Seconds}s）"
