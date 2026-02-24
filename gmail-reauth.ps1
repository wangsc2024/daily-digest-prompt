# gmail-reauth.ps1 - Gmail OAuth 重新授權腳本
# 用途：當 Google Cloud OAuth 測試模式的 7 天 Refresh Token 到期時執行
# 執行方式：pwsh -File gmail-reauth.ps1
#
# 背景說明：
#   Google Cloud OAuth 應用程式在「測試中」(Testing) 模式下，
#   Refresh Token 固定 7 天後失效（與使用頻率無關）。
#   此腳本開啟瀏覽器重新授權，更新 key/token.json。

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

$AgentDir = Split-Path -Parent $PSCommandPath
$CredsPath = Join-Path $AgentDir "key\credentials.json"
$TokenPath = Join-Path $AgentDir "key\token.json"

Write-Host "=== Gmail OAuth 重新授權 ===" -ForegroundColor Cyan
Write-Host "憑證路徑：$CredsPath"
Write-Host "Token 路徑：$TokenPath"
Write-Host ""

if (-not (Test-Path $CredsPath)) {
    Write-Host "錯誤：找不到憑證檔案 $CredsPath" -ForegroundColor Red
    Write-Host "請先從 Google Cloud Console 下載 OAuth 2.0 用戶端 ID JSON 並命名為 credentials.json"
    exit 1
}

Write-Host "開啟瀏覽器進行授權，請選擇 Gmail 帳號並按「允許」..." -ForegroundColor Yellow
Write-Host ""

python -c @"
import sys, os
sys.path.insert(0, r'$AgentDir')
from google_auth_oauthlib.flow import InstalledAppFlow
from datetime import date, timedelta

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
flow = InstalledAppFlow.from_client_secrets_file(r'$CredsPath', SCOPES)
creds = flow.run_local_server(port=0, open_browser=True)

with open(r'$TokenPath', 'w', encoding='utf-8') as f:
    f.write(creds.to_json())

expire_hint = date.today() + timedelta(days=7)
print()
print('✅  授權完成！')
print(f'📁  Token 已儲存：$TokenPath')
print(f'⏰  下次授權提醒：{expire_hint}（約 7 天後）')
print()
print('提示：on_stop_alert.py 會自動偵測 token 更新並重置 7 天計時')
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "授權失敗，請檢查上方錯誤訊息" -ForegroundColor Red
    exit 1
}
