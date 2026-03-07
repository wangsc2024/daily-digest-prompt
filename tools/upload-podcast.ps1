# ============================================================
# tools/upload-podcast.ps1
# 上傳 Podcast / 影片檔案至 Cloudflare R2
# ============================================================
# 用法：
#   pwsh -File tools/upload-podcast.ps1 -LocalPath "output/podcasts/xxx.mp3"
#   pwsh -File tools/upload-podcast.ps1 -LocalPath "..." -Title "法華經 第3集" -Topic "法華經" -Slug "法華經-20260305"
# 回傳（stdout JSON）：
#   { "url": "https://...", "key": "xxx.mp3", "size_bytes": 123456, "uploaded_at": "..." }
# ============================================================

param(
    [Parameter(Mandatory)]
    [string]$LocalPath,

    [string]$ConfigPath = "",
    [string]$Title = "",
    [string]$Topic = "",
    [string]$Slug = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

# ─── 路徑解析 ───
$AgentDir = if ((Split-Path -Leaf $PSScriptRoot) -eq "tools") {
    $PSScriptRoot | Split-Path -Parent
} else {
    $PSScriptRoot
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $AgentDir "config\podcast.yaml"
}

# ─── 讀取設定（regex 解析 YAML，無需 Python）───
if (-not (Test-Path $ConfigPath)) {
    Write-Error "[upload-podcast] 找不到設定檔：$ConfigPath"
    exit 1
}
$cfg = Get-Content $ConfigPath -Raw -Encoding UTF8

# enabled 檢查
if ($cfg -notmatch 'enabled:\s*true') {
    Write-Host "[upload-podcast] cloud_upload.enabled = false，跳過上傳" -ForegroundColor Yellow
    @{ url = ""; key = ""; size_bytes = 0; uploaded_at = ""; skipped = $true } | ConvertTo-Json -Compress
    exit 0
}

# 讀取各欄位
$accountIdEnv = if ($cfg -match 'account_id_env:\s*(\S+)') { $Matches[1] } else { "R2_ACCOUNT_ID" }
$apiTokenEnv  = if ($cfg -match 'api_token_env:\s*(\S+)')  { $Matches[1] } else { "R2_API_TOKEN" }
$bucket       = if ($cfg -match 'bucket:\s*(\S+)')         { $Matches[1] } else { "podcasts" }
$publicBase   = if ($cfg -match 'public_base_url:\s*"([^"]+)"') { $Matches[1] } else { "" }
$onFailure    = if ($cfg -match 'on_failure:\s*(\S+)')     { $Matches[1] } else { "warn" }

# ─── 取得環境變數 ───
$accountId = [System.Environment]::GetEnvironmentVariable($accountIdEnv, "User")
if (-not $accountId) { $accountId = [System.Environment]::GetEnvironmentVariable($accountIdEnv) }

$apiToken = [System.Environment]::GetEnvironmentVariable($apiTokenEnv, "User")
if (-not $apiToken) { $apiToken = [System.Environment]::GetEnvironmentVariable($apiTokenEnv) }

if (-not $accountId -or -not $apiToken) {
    $msg = "[upload-podcast] 缺少環境變數 $accountIdEnv 或 $apiTokenEnv"
    if ($onFailure -eq "error") { Write-Error $msg; exit 1 }
    Write-Warning $msg
    @{ url = ""; key = ""; size_bytes = 0; uploaded_at = ""; error = $msg } | ConvertTo-Json -Compress
    exit 0
}

# ─── 檔案驗證 ───
if (-not (Test-Path $LocalPath)) {
    $msg = "[upload-podcast] 檔案不存在：$LocalPath"
    if ($onFailure -eq "error") { Write-Error $msg; exit 1 }
    Write-Warning $msg
    @{ url = ""; key = ""; size_bytes = 0; uploaded_at = ""; error = $msg } | ConvertTo-Json -Compress
    exit 0
}

$file = Get-Item $LocalPath
$key  = $file.Name
$ext  = $file.Extension.TrimStart(".").ToLower()

# Content-Type 對應
$contentType = switch ($ext) {
    "mp3"  { "audio/mpeg" }
    "mp4"  { "video/mp4" }
    "m4a"  { "audio/mp4" }
    "wav"  { "audio/wav" }
    default { "application/octet-stream" }
}

# ─── 建構 API URL（對物件 key 做 URL encode）───
$encodedKey = [System.Uri]::EscapeDataString($key)
$apiUrl = "https://api.cloudflare.com/client/v4/accounts/$accountId/r2/buckets/$bucket/objects/$encodedKey"

Write-Host "[upload-podcast] 上傳中：$key ($([math]::Round($file.Length / 1MB, 2)) MB)" -ForegroundColor Cyan

# ─── 組裝 curl 參數（含可選 metadata，供列表頁顯示標題）───
$curlHeaders = @(
    "-H", "Authorization: Bearer $apiToken",
    "-H", "Content-Type: $contentType"
)
if ($Title) { $curlHeaders += "-H", "x-amz-meta-title: $Title" }
if ($Slug)  { $curlHeaders += "-H", "x-amz-meta-slug: $Slug" }

# ─── 執行 curl 上傳 ───
$httpCode = curl -s -o /dev/null -w "%{http_code}" `
    -X PUT $apiUrl `
    @curlHeaders `
    --data-binary "@$($file.FullName)"

if ($httpCode -notin @("200", "201")) {
    $msg = "[upload-podcast] 上傳失敗，HTTP $httpCode（URL: $apiUrl）"
    if ($onFailure -eq "error") { Write-Error $msg; exit 1 }
    Write-Warning $msg
    @{ url = ""; key = $key; size_bytes = $file.Length; uploaded_at = ""; error = $msg } | ConvertTo-Json -Compress
    exit 0
}

# ─── 產生公開 URL ───
$publicUrl = if ($publicBase) {
    "$publicBase/$key"
} else {
    "https://$accountId.r2.cloudflarestorage.com/$bucket/$encodedKey"
}

Write-Host "[upload-podcast] 上傳成功：$publicUrl" -ForegroundColor Green

# ─── 若有 Title 或 Topic，更新 R2 內 _meta/podcast-titles.json（列表頁標題/主題）───
if ($Title -or $Topic) {
    $metaKey = "_meta/podcast-titles.json"
    $metaUrl = "https://api.cloudflare.com/client/v4/accounts/$accountId/r2/buckets/$bucket/objects/" + [System.Uri]::EscapeDataString($metaKey)
    $metaPublicUrl = if ($publicBase) { "$publicBase/$metaKey" } else { "" }

    $meta = @{}
    if ($metaPublicUrl) {
        try {
            $resp = Invoke-WebRequest -Uri $metaPublicUrl -UseBasicParsing -TimeoutSec 10 -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200 -and $resp.Content) {
                $meta = $resp.Content | ConvertFrom-Json -AsHashtable -ErrorAction SilentlyContinue
                if (-not $meta) { $meta = @{} }
            }
        } catch {
            # 無檔案或網路錯誤，從空開始
        }
    }

    if (-not $meta[$key]) { $meta[$key] = @{} }
    if ($Title) { $meta[$key]["title"] = $Title }
    if ($Topic) { $meta[$key]["topic"] = $Topic }
    if ($Slug)  { $meta[$key]["slug"]  = $Slug }

    $metaJson = $meta | ConvertTo-Json -Compress -Depth 5
    $metaTemp = [System.IO.Path]::GetTempFileName()
    Set-Content -Path $metaTemp -Value $metaJson -Encoding UTF8 -NoNewline

    $putMetaCode = curl -s -o /dev/null -w "%{http_code}" `
        -X PUT $metaUrl `
        -H "Authorization: Bearer $apiToken" `
        -H "Content-Type: application/json; charset=utf-8" `
        --data-binary "@$metaTemp"
    Remove-Item $metaTemp -Force -ErrorAction SilentlyContinue

    if ($putMetaCode -in @("200", "201")) {
        Write-Host "[upload-podcast] 已更新列表標題/主題" -ForegroundColor Cyan
    } else {
        Write-Host "[upload-podcast] 更新 manifest 失敗 HTTP $putMetaCode（非致命）" -ForegroundColor Yellow
    }
}

# ─── 輸出結果 JSON（供呼叫端 ConvertFrom-Json）───
@{
    url         = $publicUrl
    key         = $key
    size_bytes  = $file.Length
    uploaded_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
} | ConvertTo-Json -Compress
