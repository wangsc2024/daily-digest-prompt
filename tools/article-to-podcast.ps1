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

# ─── Slug 產生 ───
if (-not $Slug) {
    if ($NoteId) {
        $Slug = "note-$($NoteId.Substring(0, [Math]::Min(8, $NoteId.Length)))-$(Get-Date -Format 'yyyyMMdd')"
    } else {
        # Query slug 化：取前 20 字，替換非英數為連字號
        $slugBase = $Query -replace "[^\w]", "-" -replace "-+", "-" -replace "^-|-$", ""
        $slugBase = $slugBase.Substring(0, [Math]::Min(20, $slugBase.Length)).ToLower()
        $Slug = "$slugBase-$(Get-Date -Format 'yyyyMMdd')"
    }
}

$ResultsDir = Join-Path $AgentDir "results\article-$Slug"
$AudioDir = Join-Path $ResultsDir "podcast-audio"
$ScriptFile = Join-Path $ResultsDir "podcast-script.jsonl"

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

# ============================================================
# Phase 1：Claude Podcast Script Agent
# ============================================================
Write-Log "--- Phase 1: Claude 生成對話腳本 [model: $Model] ---"

$promptTemplate = Get-Content (Join-Path $AgentDir "prompts\article-to-podcast-script.md") -Raw -Encoding UTF8
$prompt = $promptTemplate `
    -replace "\{\{NOTE_ID\}\}", $NoteId `
    -replace "\{\{QUERY\}\}", $Query `
    -replace "\{\{SLUG\}\}", $Slug

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

$OutFile = Join-Path $OutputDir "${Slug}_$Timestamp.mp3"
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

    $kbTitle = if ($NoteId) {
        "Podcast 腳本：note-$($NoteId.Substring(0, [Math]::Min(8, $NoteId.Length)))"
    } else {
        "Podcast 腳本：$Query"
    }

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

$totalSeconds = $phase1Seconds + $phase2Seconds + $phase3Seconds + $phase4Seconds
Write-Log "=== 完成！==="
Write-Log "輸出檔案: $OutFile"
Write-Log "總耗時: ${totalSeconds}s（Phase1: ${phase1Seconds}s, Phase2: ${phase2Seconds}s, Phase3: ${phase3Seconds}s, Phase4-KB: ${phase4Seconds}s）"
