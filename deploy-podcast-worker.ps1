# 部署 Podcast 列表 Worker（podcast.pdoont.us.kg）
# 注意：專案根目錄的 npx wrangler deploy 會部署 daily-digest-prompt，不是 podcast-index。
# 必須用 --config 明確指定 workers/podcast-index/wrangler.toml，否則 Wrangler 會用根目錄的 wrangler.jsonc。

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$podcastDir = Join-Path $scriptDir "workers\podcast-index"
$configPath = Join-Path $podcastDir "wrangler.toml"
Set-Location $podcastDir
Write-Host "部署 podcast-index Worker（設定檔: $configPath）" -ForegroundColor Cyan
npx wrangler deploy --config $configPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "完成。請確認 podcast.pdoont.us.kg 在 Cloudflare 上綁定到 Worker podcast-index。" -ForegroundColor Green
