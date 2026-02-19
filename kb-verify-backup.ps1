# kb-verify-backup.ps1 - 知識庫備份審查 wrapper（供 HEARTBEAT.md 排程呼叫）
# 若審查失敗（exit 2），透過 ntfy 告警
param(
    [string]$NtfyTopic = "wangsc2025"
)

$result = pwsh -ExecutionPolicy Bypass -File "D:\Source\RAG_Skill\verify-backup-kb.ps1"
$exitCode = $LASTEXITCODE

if ($exitCode -ge 2) {
    # 建立告警通知
    $body = @{
        topic    = $NtfyTopic
        title    = "備份審查失敗"
        message  = "知識庫備份審查偵測到錯誤，請立即檢查備份系統。`n詳情：執行 verify-backup-kb.ps1"
        priority = 4
        tags     = @("warning", "backup")
    } | ConvertTo-Json -Compress

    $tmpFile = [System.IO.Path]::GetTempFileName() + ".json"
    [System.IO.File]::WriteAllText($tmpFile, $body, [System.Text.Encoding]::UTF8)
    curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$tmpFile" https://ntfy.sh | Out-Null
    Remove-Item $tmpFile -ErrorAction SilentlyContinue

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 告警已發送至 ntfy ($NtfyTopic)"
}

exit $exitCode
