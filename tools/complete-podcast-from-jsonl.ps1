# ============================================================
# tools/complete-podcast-from-jsonl.ps1
# 從已生成的 JSONL 腳本補跑 Phase 2-6：TTS → 合併 → MP3 → 上傳 R2 → ntfy
# ============================================================
# 用法：
#   pwsh -ExecutionPolicy Bypass -File tools/complete-podcast-from-jsonl.ps1 -ScriptFile "podcasts/20260311/script_ep1.jsonl"
#   pwsh -ExecutionPolicy Bypass -File tools/complete-podcast-from-jsonl.ps1 -ScriptFile "..." -Topic "大悲懺"
# ============================================================

param(
    [Parameter(Mandatory)]
    [string]$ScriptFile,   # 已存在的 JSONL 腳本路徑
    [string]$Topic = "",   # Podcast 主題標籤（可選）
    [string]$Title = ""    # Podcast 標題（可選，若留空從腳本第一行推斷）
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ─── 路徑設定 ───
$AgentDir = if ((Split-Path -Leaf $PSScriptRoot) -eq "tools") {
    $PSScriptRoot | Split-Path -Parent
} else {
    $PSScriptRoot
}
$ToolsDir  = Join-Path $AgentDir "tools"
$LogDir    = Join-Path $AgentDir "logs"
$OutputDir = Join-Path $AgentDir "output\podcasts"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$FileTimestamp = Get-Date -Format "yyyyMMddHHmm"

# 解析 ScriptFile 為絕對路徑
if (-not [System.IO.Path]::IsPathRooted($ScriptFile)) {
    $ScriptFile = Join-Path $AgentDir $ScriptFile
}
if (-not (Test-Path $ScriptFile)) {
    Write-Error "找不到 JSONL 腳本檔案：$ScriptFile"
    exit 1
}

foreach ($dir in @($LogDir, (Join-Path $LogDir "structured"), $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$LogFile = Join-Path $LogDir "podcast-complete-$Timestamp.log"

function Write-Log($Message) {
    $ts   = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "=== complete-podcast-from-jsonl 開始 ==="
Write-Log "腳本檔：$ScriptFile"

# ─── 從腳本推斷標題（讀首行 text 欄位）───
if (-not $Title) {
    try {
        $firstTurn = Get-Content $ScriptFile -TotalCount 1 -Encoding UTF8 | ConvertFrom-Json
        $rawText   = $firstTurn.text -replace "大家好.*?。", "" -replace "^[，,\s]+", ""
        $Title     = ($rawText -split "[。！？\!\?]")[0].Trim()
        if ($Title.Length -gt 20) { $Title = $Title.Substring(0, 20) }
        if (-not $Title) { $Title = [System.IO.Path]::GetFileNameWithoutExtension($ScriptFile) }
    } catch {
        $Title = [System.IO.Path]::GetFileNameWithoutExtension($ScriptFile)
    }
}

# ─── 音訊目錄（放在腳本同目錄下）───
$ScriptDir = Split-Path -Parent $ScriptFile
$ScriptBase = [System.IO.Path]::GetFileNameWithoutExtension($ScriptFile)
$AudioDir  = Join-Path $ScriptDir "audio_$ScriptBase"
$safeTitle = $Title -replace '[/\\:*?"<>|\r\n]', '' -replace '\s+', ''
$safeTitle = $safeTitle.Substring(0, [Math]::Min(20, $safeTitle.Length))
$OutFile   = Join-Path $OutputDir "${safeTitle}_${FileTimestamp}.mp3"

foreach ($dir in @($AudioDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$turnCount = (Get-Content $ScriptFile -Encoding UTF8 | Where-Object { $_.Trim() }) | Measure-Object | Select-Object -ExpandProperty Count
Write-Log "腳本共 $turnCount 段對話"

# ============================================================
# Phase 2：TTS 語音合成
# ============================================================
Write-Log "--- Phase 2: TTS 音訊生成 ---"
$cfgPath = Join-Path $AgentDir "config\media-pipeline.yaml"
$ttsArgs = @(
    (Join-Path $ToolsDir "generate_podcast_audio.py"),
    "--input",  $ScriptFile,
    "--output", $AudioDir,
    "--abbrev-rules", (Join-Path $AgentDir "config\tts-abbreviation-rules.yaml")
)
if (Test-Path $cfgPath) {
    $voiceA = (Get-Content $cfgPath | Select-String "voice_a:") -replace '.*voice_a:\s*"?([^"#\s]+)"?.*', '$1'
    $voiceB = (Get-Content $cfgPath | Select-String "voice_b:") -replace '.*voice_b:\s*"?([^"#\s]+)"?.*', '$1'
    if ($voiceA) { $ttsArgs += "--voice-a", $voiceA.Trim() }
    if ($voiceB) { $ttsArgs += "--voice-b", $voiceB.Trim() }
}
$phase2Start = Get-Date
uv run --project $AgentDir python @ttsArgs
$phase2Success = ($LASTEXITCODE -eq 0)
$phase2Seconds = [int]((Get-Date) - $phase2Start).TotalSeconds
Write-Log "Phase 2 完成，耗時 ${phase2Seconds}s，成功: $phase2Success"
if (-not $phase2Success) { Write-Log "[ERROR] TTS 失敗，中止"; exit 1 }

# ============================================================
# Phase 3：音訊合併 → MP3
# ============================================================
Write-Log "--- Phase 3: 音訊合併 + MP3 輸出 ---"
$concatArgs = @(
    (Join-Path $ToolsDir "concat_audio.py"),
    "--audio-dir", $AudioDir,
    "--script",    $ScriptFile,
    "--output",    $OutFile
)
if (Test-Path $cfgPath) { $concatArgs += "--config", $cfgPath }

$phase3Start = Get-Date
uv run --project $AgentDir python @concatArgs
$phase3Success = ($LASTEXITCODE -eq 0)
$phase3Seconds = [int]((Get-Date) - $phase3Start).TotalSeconds
Write-Log "Phase 3 完成，耗時 ${phase3Seconds}s，成功: $phase3Success"
if (-not $phase3Success) { Write-Log "[ERROR] 音訊合併失敗，中止"; exit 1 }

# ============================================================
# Phase 4：上傳至 R2（非致命）
# ============================================================
Write-Log "--- Phase 4: 上傳至 Cloudflare R2 ---"
$publicUrl = ""
$uploadScript = Join-Path $ToolsDir "upload-podcast.ps1"
if (Test-Path $uploadScript) {
    try {
        $uploadTopic = if ($Topic) { $Topic } else { $Title }
        $phase4Start = Get-Date
        $uploadJson  = pwsh -ExecutionPolicy Bypass -File $uploadScript `
            -LocalPath $OutFile -Title $Title -Topic $uploadTopic `
            -Slug "$ScriptBase-$FileTimestamp" 2>&1 |
            Where-Object { $_ -match '^\{' } | Select-Object -Last 1
        $phase4Seconds = [int]((Get-Date) - $phase4Start).TotalSeconds
        if ($uploadJson) {
            $up = $uploadJson | ConvertFrom-Json
            if ($up.url) {
                $publicUrl = $up.url
                $sizeMB = [math]::Round($up.size_bytes / 1MB, 1)
                Write-Log "上傳成功：$publicUrl（${sizeMB} MB），耗時 ${phase4Seconds}s"
            }
        }
    } catch {
        Write-Log "[WARN] 上傳失敗（非致命）: $_"
    }
} else {
    Write-Log "[WARN] 找不到 upload-podcast.ps1，跳過上傳"
}

# ============================================================
# Phase 5：ntfy 完成通知
# ============================================================
Write-Log "--- Phase 5: ntfy 通知 ---"
try {
    $sizeMBDisplay = if (Test-Path $OutFile) { [math]::Round((Get-Item $OutFile).Length / 1MB, 1) } else { "?" }
    $msgLines = @("已完成補跑：$Title（${sizeMBDisplay} MB）")
    if ($publicUrl) { $msgLines += "點此播放 $publicUrl" }

    $ntfyBody = [ordered]@{
        topic    = "wangsc2025"
        title    = "🎙️ Podcast 補跑完成：$Title"
        message  = $msgLines -join "`n"
        tags     = @("headphones", "white_check_mark")
        priority = 3
    }
    if ($publicUrl) { $ntfyBody["click"] = $publicUrl }

    $ntfyTmp = Join-Path $LogDir "ntfy_complete_$Timestamp.json"
    $ntfyBody | ConvertTo-Json -Compress -Depth 3 | Set-Content $ntfyTmp -Encoding UTF8
    curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyTmp" https://ntfy.sh | Out-Null
    Remove-Item $ntfyTmp -Force -ErrorAction SilentlyContinue
    Write-Log "ntfy 通知已發送"
} catch {
    Write-Log "[WARN] ntfy 通知失敗（非致命）: $_"
}

$totalSeconds = $phase2Seconds + $phase3Seconds
Write-Log "=== 完成！==="
Write-Log "輸出：$OutFile"
if ($publicUrl) { Write-Log "公開 URL：$publicUrl" }
Write-Log "總耗時：${totalSeconds}s（TTS: ${phase2Seconds}s, 合併: ${phase3Seconds}s）"

# 輸出 JSON 供呼叫端解析
@{
    status    = "success"
    mp3_path  = $OutFile
    cloud_url = $publicUrl
    title     = $Title
    turns     = $turnCount
} | ConvertTo-Json -Compress
