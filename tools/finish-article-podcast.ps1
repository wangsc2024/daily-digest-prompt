# ============================================================
# tools/finish-article-podcast.ps1
# 從 results/article-<slug>/ 一鍵：TTS → concat（podcast-final.mp3）→ 選用 R2 上傳
# 聲線讀取 config/media-pipeline.yaml（與 article-to-podcast.ps1 一致）
# ============================================================
# 用法：
#   pwsh -File tools/finish-article-podcast.ps1 -ResultsDir "results/article-淨土學苑_ep09_..."
#   pwsh -File tools/finish-article-podcast.ps1 -ResultsDir "..." -SkipTts -Upload
#   pwsh -File tools/finish-article-podcast.ps1 -ResultsDir "..." -Upload -UploadTitle "標題" -UploadSlug "key" -UploadTopic "主題"
# ============================================================

param(
    [Parameter(Mandatory)]
    [string]$ResultsDir,

    [switch]$SkipTts,
    [switch]$SkipConcat,
    [switch]$Upload,
    [switch]$Ntfy,

    [string]$UploadTitle = "",
    [string]$UploadTopic = "",
    [string]$UploadSlug = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

$AgentDir = if ((Split-Path -Leaf $PSScriptRoot) -eq "tools") {
    $PSScriptRoot | Split-Path -Parent
} else {
    $PSScriptRoot
}
$ToolsDir = Join-Path $AgentDir "tools"
$cfgPath  = Join-Path $AgentDir "config\media-pipeline.yaml"

if (-not [System.IO.Path]::IsPathRooted($ResultsDir)) {
    $ResultsDir = Join-Path $AgentDir $ResultsDir
}
if (-not (Test-Path -LiteralPath $ResultsDir)) {
    Write-Error "結果目錄不存在：$ResultsDir"
    exit 1
}
$ResultsDir = (Get-Item -LiteralPath $ResultsDir).FullName

$ScriptFile = Join-Path $ResultsDir "podcast-script.jsonl"
$AudioDir   = Join-Path $ResultsDir "podcast-audio"
$FinalMp3   = Join-Path $ResultsDir "podcast-final.mp3"
$MetaFile   = Join-Path $ResultsDir "podcast-meta.json"

function Write-Step($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $ScriptFile)) {
    Write-Error "找不到腳本：$ScriptFile"
    exit 1
}

# ─── Phase 1：TTS ───
if (-not $SkipTts) {
    Write-Step "Phase 1: TTS（generate_podcast_audio.py）"
    New-Item -ItemType Directory -Force -Path $AudioDir | Out-Null
    $ttsArgs = @(
        (Join-Path $ToolsDir "generate_podcast_audio.py"),
        "--input", $ScriptFile,
        "--output", $AudioDir,
        "--abbrev-rules", (Join-Path $AgentDir "config\tts-abbreviation-rules.yaml")
    )
    if (Test-Path $cfgPath) {
        $voiceA = (Get-Content $cfgPath | Select-String "voice_a:") -replace '.*voice_a:\s*"?([^"#\s]+)"?.*', '$1'
        $voiceB = (Get-Content $cfgPath | Select-String "voice_b:") -replace '.*voice_b:\s*"?([^"#\s]+)"?.*', '$1'
        $voiceGuest = (Get-Content $cfgPath | Select-String "voice_guest:") -replace '.*voice_guest:\s*"?([^"#\s]+)"?.*', '$1'
        if ($voiceA) { $ttsArgs += "--voice-a", $voiceA.Trim() }
        if ($voiceB) { $ttsArgs += "--voice-b", $voiceB.Trim() }
        if ($voiceGuest) { $ttsArgs += "--voice-guest", $voiceGuest.Trim() }
    }
    uv run --project $AgentDir python @ttsArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "TTS 失敗"
        exit 1
    }
} else {
    Write-Step "略過 TTS（-SkipTts）"
}

# ─── Phase 2：合併 ───
if (-not $SkipConcat) {
    Write-Step "Phase 2: 合併（concat_audio.py → podcast-final.mp3）"
    $concatArgs = @(
        (Join-Path $ToolsDir "concat_audio.py"),
        "--audio-dir", $AudioDir,
        "--script", $ScriptFile,
        "--output", $FinalMp3,
        "--config", $cfgPath
    )
    uv run --project $AgentDir python @concatArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "音訊合併失敗"
        exit 1
    }
} else {
    Write-Step "略過合併（-SkipConcat）"
}

$publicUrl = ""

# ─── Phase 3：R2 ───
if ($Upload) {
    if (-not (Test-Path -LiteralPath $FinalMp3)) {
        Write-Error "找不到 $FinalMp3，無法上傳"
        exit 1
    }
    $upScript = Join-Path $ToolsDir "upload-podcast.ps1"
    if (-not (Test-Path $upScript)) {
        Write-Error "找不到 upload-podcast.ps1"
        exit 1
    }

    $title = $UploadTitle
    $topic = $UploadTopic
    $slug  = $UploadSlug

    if (Test-Path -LiteralPath $MetaFile) {
        $meta = Get-Content $MetaFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $slug -and $meta.slug) { $slug = [string]$meta.slug }
        if (-not $title -and $meta.podcast_title) {
            $title = if ($slug -match '^淨土學苑') {
                "淨土學苑｜$($meta.podcast_title)"
            } else {
                [string]$meta.podcast_title
            }
        }
        if (-not $topic -and $meta.topics -and $meta.topics.Count -gt 0) {
            $topic = [string]$meta.topics[0]
        }
        if (-not $topic -and $meta.podcast_title) { $topic = [string]$meta.podcast_title }
    }

    if (-not $slug) {
        Write-Error "上傳需要 Slug：請在 podcast-meta.json 提供 slug，或使用 -UploadSlug"
        exit 1
    }
    if (-not $title) { $title = (Split-Path -Leaf $ResultsDir) }
    if (-not $topic) { $topic = $title }

    Write-Step "Phase 3: 上傳 R2（slug=$slug）"
    $uploadJson = pwsh -ExecutionPolicy Bypass -File $upScript `
        -LocalPath $FinalMp3 -Title $title -Topic $topic -Slug $slug 2>&1 |
        Where-Object { $_ -match '^\{' } | Select-Object -Last 1
    if ($uploadJson) {
        $up = $uploadJson | ConvertFrom-Json
        if ($up.url) {
            $publicUrl = $up.url
            Write-Host "上傳成功：$publicUrl" -ForegroundColor Green
        } else {
            Write-Warning "上傳回傳無 url：$uploadJson"
        }
    }
}

# ─── 選用 ntfy ───
if ($Ntfy) {
    $ntfyTopic = "wangsc2025"
    $podcastCfg = Join-Path $AgentDir "config\podcast.yaml"
    if (Test-Path $podcastCfg) {
        $raw = Get-Content $podcastCfg -Raw -Encoding UTF8
        if ($raw -match 'topic:\s*["'']?([^"''\r\n]+)') { $ntfyTopic = $Matches[1].Trim() }
    }
    $lines = @("Podcast 收尾完成：$(Split-Path -Leaf $ResultsDir)")
    if (Test-Path $FinalMp3) {
        $mb = [math]::Round((Get-Item $FinalMp3).Length / 1MB, 2)
        $lines += "檔案 ${mb} MB"
    }
    if ($publicUrl) { $lines += "點此播放 $publicUrl" }
    $body = [ordered]@{
        topic    = $ntfyTopic
        title    = "🎙️ Podcast：$(Split-Path -Leaf $ResultsDir)"
        message  = $lines -join "`n"
        tags     = @("headphones", "white_check_mark")
        priority = 3
    }
    if ($publicUrl) { $body["click"] = $publicUrl }
    $tmp = Join-Path $env:TEMP "ntfy_finish_article_$(Get-Date -Format 'yyyyMMddHHmmss').json"
    $body | ConvertTo-Json -Compress -Depth 4 | Set-Content $tmp -Encoding UTF8
    curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$tmp" https://ntfy.sh | Out-Null
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    Write-Step "已送出 ntfy（topic=$ntfyTopic）"
}

Write-Step "完成。輸出：$FinalMp3"
@{
    status    = "success"
    mp3_path  = $FinalMp3
    cloud_url = $publicUrl
} | ConvertTo-Json -Compress
