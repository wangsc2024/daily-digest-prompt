# ============================================================
# tools/article-to-video.ps1
# 影片生成工具：知識庫文章 → Remotion MP4
# ============================================================
# 用法：
#   pwsh -ExecutionPolicy Bypass -File tools/article-to-video.ps1 -NoteId "6c25f7f9"
#   pwsh -ExecutionPolicy Bypass -File tools/article-to-video.ps1 -Query "Remotion 影片自動化"
# ============================================================

param(
    [string]$NoteId = "",
    [string]$Query = "",
    [string]$Slug = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ─── 參數驗證 ───
if (-not $NoteId -and -not $Query) {
    Write-Error "請提供 -NoteId <筆記ID> 或 -Query <搜尋關鍵字>"
    exit 1
}

# ─── 路徑設定 ───
$ScriptRoot = $PSScriptRoot
$AgentDir = Split-Path -Parent $ScriptRoot
$ToolsDir = $ScriptRoot
$VideoStudioDir = Join-Path $ToolsDir "video-studio"
$LogDir = Join-Path $AgentDir "logs"
$OutputDir = Join-Path $AgentDir "output\videos"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

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
$ScriptDir = Join-Path $ResultsDir "script"
$AudioDir = Join-Path $ResultsDir "audio"
$StoryboardFile = Join-Path $ResultsDir "storyboard.json"
$RemotionDataFile = Join-Path $VideoStudioDir "src\data\remotion-data.json"

# ─── 建立目錄 ───
foreach ($dir in @($LogDir, (Join-Path $LogDir "structured"), $ResultsDir, $ScriptDir, $AudioDir, $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$LogFile = Join-Path $LogDir "video_$Timestamp.log"

function Write-Log($Message) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "=== Article → Video 開始 ==="
Write-Log "Slug: $Slug"
if ($NoteId) { Write-Log "NoteId: $NoteId" }
if ($Query) { Write-Log "Query: $Query" }

# ============================================================
# Phase 0.5：確認 Remotion 依賴（node_modules）
# ============================================================
$nodeModules = Join-Path $VideoStudioDir "node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Log "--- Remotion 依賴安裝中（首次執行）---"
    Push-Location $VideoStudioDir
    npm install --prefer-offline 2>&1 | Out-Null
    Pop-Location
    Write-Log "npm install 完成"
}

# ============================================================
# Phase 1：Claude Script + Storyboard Agent
# ============================================================
Write-Log "--- Phase 1: Claude 生成逐字稿 + 分鏡稿 ---"

$promptTemplate = Get-Content (Join-Path $AgentDir "prompts\article-to-video-script.md") -Raw -Encoding UTF8
$prompt = $promptTemplate `
    -replace "\{\{NOTE_ID\}\}", $NoteId `
    -replace "\{\{QUERY\}\}", $Query `
    -replace "\{\{SLUG\}\}", $Slug

$stderrFile = Join-Path $LogDir "video-phase1-stderr-$Timestamp.log"
$phase1Start = Get-Date

# 暫時清除 CLAUDECODE 避免嵌套 Session 拒絕
$savedClaudeCode = $env:CLAUDECODE
$env:CLAUDECODE = $null
try {
    $phase1Output = $prompt | claude -p --allowedTools "Read,Write,Bash" 2>$stderrFile
    $phase1Success = ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE)
} catch {
    Write-Log "[ERROR] Phase 1 執行失敗: $_"
    $phase1Success = $false
} finally {
    if ($savedClaudeCode) { $env:CLAUDECODE = $savedClaudeCode }
    else { Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue }
}

$phase1Seconds = [int]((Get-Date) - $phase1Start).TotalSeconds
Write-Log "Phase 1 完成，耗時 ${phase1Seconds}s，成功: $phase1Success"

if ((Test-Path $stderrFile) -and (Get-Item $stderrFile).Length -eq 0) {
    Remove-Item $stderrFile -Force -ErrorAction SilentlyContinue
}

if (-not $phase1Success -or -not (Test-Path $StoryboardFile)) {
    Write-Log "[ERROR] Phase 1 失敗或 storyboard.json 未生成"
    exit 1
}

$scriptCount = (Get-ChildItem $ScriptDir -Filter "*.md" | Measure-Object).Count
Write-Log "腳本生成完成，共 $scriptCount 個章節"

# ============================================================
# Phase 2：TTS 生成
# ============================================================
Write-Log "--- Phase 2: TTS 音訊生成 ---"

$cfgPath = Join-Path $AgentDir "config\media-pipeline.yaml"
$voiceArg = "zh-TW-HsiaoChenNeural"
if (Test-Path $cfgPath) {
    $voiceLine = (Get-Content $cfgPath | Select-String "^\s+voice:\s+").Line
    if ($voiceLine) {
        $v = $voiceLine -replace '.*voice:\s*"?([^"#\s]+)"?.*', '$1'
        if ($v.Trim()) { $voiceArg = $v.Trim() }
    }
}

$phase2Start = Get-Date
uv run --project $AgentDir python (Join-Path $ToolsDir "generate_tts.py") `
    --input $ScriptDir `
    --output $AudioDir `
    --voice $voiceArg `
    --abbrev-rules (Join-Path $AgentDir "config\tts-abbreviation-rules.yaml")

$phase2Success = ($LASTEXITCODE -eq 0)
$phase2Seconds = [int]((Get-Date) - $phase2Start).TotalSeconds
Write-Log "Phase 2 完成，耗時 ${phase2Seconds}s，成功: $phase2Success"

if (-not $phase2Success) {
    Write-Log "[ERROR] Phase 2 TTS 生成失敗"
    exit 1
}

# ============================================================
# Phase 3A：Compose remotion-data.json
# ============================================================
Write-Log "--- Phase 3A: 計算幀數，生成 remotion-data.json ---"

$phase3Start = Get-Date
uv run --project $AgentDir python (Join-Path $ToolsDir "compose_video.py") `
    --storyboard $StoryboardFile `
    --audio-dir $AudioDir `
    --fps 30 `
    --output $RemotionDataFile

if ($LASTEXITCODE -ne 0) {
    Write-Log "[ERROR] Phase 3A compose_video.py 失敗"
    exit 1
}
Write-Log "remotion-data.json 已更新"

# ============================================================
# Phase 3B：Remotion 渲染 MP4
# ============================================================
Write-Log "--- Phase 3B: Remotion 渲染 MP4 ---"

$OutFile = Join-Path $OutputDir "${Slug}_$Timestamp.mp4"
# Remotion 需要相對路徑或絕對路徑（Windows 用正斜線）
$OutFileForwardSlash = $OutFile -replace "\\", "/"

Push-Location $VideoStudioDir
# --concurrency=1：Windows 上避免多 Chrome 實例觸發 EPERM kill 錯誤
# --gl=angle：使用 ANGLE OpenGL 渲染，Windows 相容性更佳
npx remotion render Article "$OutFileForwardSlash" --concurrency=1 --gl=angle 2>&1 | Tee-Object -Variable remotionOutput
$remotionSuccess = ($LASTEXITCODE -eq 0)
Pop-Location

$phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
Write-Log "Phase 3 完成，耗時 ${phase3Seconds}s，成功: $remotionSuccess"

if (-not $remotionSuccess) {
    Write-Log "[ERROR] Remotion 渲染失敗"
    Write-Log ($remotionOutput | Select-Object -Last 10 | Out-String)
    exit 1
}

# ============================================================
# Phase 4：儲存逐字稿至知識庫（非致命）
# ============================================================
Write-Log "--- Phase 4: 儲存逐字稿至知識庫 ---"
$phase4Seconds = 0
try {
    $storyboard  = Get-Content $StoryboardFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $kbTitle     = "影片腳本：$($storyboard.meta.title)"

    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.AppendLine("# $($storyboard.meta.title)")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("> 生成時間：$Timestamp | 輸出：``$OutFile``")
    [void]$sb.AppendLine("")

    $chapterFiles = Get-ChildItem $ScriptDir -Filter "*.md" -ErrorAction SilentlyContinue | Sort-Object Name
    foreach ($f in $chapterFiles) {
        [void]$sb.AppendLine((Get-Content $f.FullName -Raw -Encoding UTF8))
        [void]$sb.AppendLine("")
    }

    $noteBody = @{
        title   = $kbTitle
        content = $sb.ToString()
        source  = "import"
        tags    = @("影片製作", "逐字稿", "Remotion", $Slug)
    } | ConvertTo-Json -Compress -Depth 3

    $phase4Start = Get-Date
    $created = Invoke-RestMethod -Uri "http://localhost:3000/api/notes" -Method POST `
        -ContentType "application/json; charset=utf-8" `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($noteBody)) `
        -TimeoutSec 10
    $phase4Seconds = [int]((Get-Date) - $phase4Start).TotalSeconds
    $kbId = if ($created.id) { $created.id } elseif ($created.noteId) { $created.noteId } else { "unknown" }
    Write-Log "逐字稿已儲存至知識庫，noteId: $kbId，耗時 ${phase4Seconds}s"
} catch {
    Write-Log "[WARN] 儲存知識庫失敗（非致命）: $_"
}

$totalSeconds = $phase1Seconds + $phase2Seconds + $phase3Seconds + $phase4Seconds
Write-Log "=== 完成！==="
Write-Log "輸出影片: $OutFile"
Write-Log "總耗時: ${totalSeconds}s（Phase1: ${phase1Seconds}s, Phase2: ${phase2Seconds}s, Phase3: ${phase3Seconds}s, Phase4-KB: ${phase4Seconds}s）"
