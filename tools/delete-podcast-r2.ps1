# ============================================================
# tools/delete-podcast-r2.ps1
# 從 Cloudflare R2 刪除 Podcast 物件並同步更新 manifest
# ============================================================
# 用法：
#   pwsh -File tools/delete-podcast-r2.ps1 -Key "note-3650fffd-20260305_20260305_072344.mp3"
#   pwsh -File tools/delete-podcast-r2.ps1 -Url "https://podcasts.pdoont.us.kg/note-xxx.mp3"
# ============================================================

param(
    [Parameter(Mandatory, ParameterSetName = "ByKey")]
    [string]$Key,

    [Parameter(Mandatory, ParameterSetName = "ByUrl")]
    [string]$Url
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

# 若由 Url 解析 key
if ($Url) {
    $Key = [System.IO.Path]::GetFileName(([System.Uri]$Url).LocalPath)
    if (-not $Key) {
        Write-Error "[delete-podcast-r2] 無法從 URL 解析 key：$Url"
        exit 1
    }
}

# ─── 路徑解析 ───
$AgentDir = if ((Split-Path -Leaf $PSScriptRoot) -eq "tools") {
    $PSScriptRoot | Split-Path -Parent
} else {
    $PSScriptRoot
}
$ConfigPath = Join-Path $AgentDir "config\podcast.yaml"

# ─── 讀取設定 ───
if (-not (Test-Path $ConfigPath)) {
    Write-Error "[delete-podcast-r2] 找不到設定檔：$ConfigPath"
    exit 1
}
$cfg = Get-Content $ConfigPath -Raw -Encoding UTF8
$accountIdEnv = if ($cfg -match 'account_id_env:\s*(\S+)') { $Matches[1] } else { "R2_ACCOUNT_ID" }
$apiTokenEnv  = if ($cfg -match 'api_token_env:\s*(\S+)')  { $Matches[1] } else { "R2_API_TOKEN" }
$bucket       = if ($cfg -match 'bucket:\s*(\S+)')         { $Matches[1] } else { "podcasts" }
$publicBase   = if ($cfg -match 'public_base_url:\s*"([^"]+)"') { $Matches[1] } else { "" }

# ─── 取得環境變數 ───
$accountId = [System.Environment]::GetEnvironmentVariable($accountIdEnv, "User")
if (-not $accountId) { $accountId = [System.Environment]::GetEnvironmentVariable($accountIdEnv) }
$apiToken = [System.Environment]::GetEnvironmentVariable($apiTokenEnv, "User")
if (-not $apiToken) { $apiToken = [System.Environment]::GetEnvironmentVariable($apiTokenEnv) }

if (-not $accountId -or -not $apiToken) {
    Write-Error "[delete-podcast-r2] 缺少環境變數 $accountIdEnv 或 $apiTokenEnv"
    exit 1
}

# ─── 1. 刪除物件 ───
$encodedKey = [System.Uri]::EscapeDataString($Key)
$apiUrl = "https://api.cloudflare.com/client/v4/accounts/$accountId/r2/buckets/$bucket/objects/$encodedKey"

Write-Host "[delete-podcast-r2] 刪除物件：$Key" -ForegroundColor Cyan
$deleteCode = curl -s -o /dev/null -w "%{http_code}" `
    -X DELETE $apiUrl `
    -H "Authorization: Bearer $apiToken"

if ($deleteCode -notin @("200", "204")) {
    Write-Error "[delete-podcast-r2] 刪除失敗，HTTP $deleteCode"
    exit 1
}
Write-Host "[delete-podcast-r2] 已刪除：$Key" -ForegroundColor Green

# ─── 2. 更新 manifest，移除該 key ───
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
    } catch { }
}

if ($meta.ContainsKey($Key)) {
    $meta.Remove($Key)
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
        Write-Host "[delete-podcast-r2] 已從 manifest 移除" -ForegroundColor Cyan
    } else {
        Write-Host "[delete-podcast-r2] 更新 manifest 失敗 HTTP $putMetaCode（非致命）" -ForegroundColor Yellow
    }
}

Write-Host "[delete-podcast-r2] 完成" -ForegroundColor Green
