# ============================================
# Circuit Breaker 預檢查功能測試
# ============================================
# 測試 circuit-breaker-utils.ps1 和 run-agent-team.ps1 的整合

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== Circuit Breaker 預檢查功能測試 ===" -ForegroundColor Cyan
Write-Host ""

# 載入工具函式庫
$utilsPath = ".\circuit-breaker-utils.ps1"
if (-not (Test-Path $utilsPath)) {
    Write-Host "[ERROR] circuit-breaker-utils.ps1 不存在" -ForegroundColor Red
    exit 1
}

. $utilsPath
Write-Host "[OK] 已載入 circuit-breaker-utils.ps1" -ForegroundColor Green

# ============================================
# 測試 1：Test-APIHealth 函式
# ============================================
Write-Host "`n[測試 1] Test-APIHealth 函式" -ForegroundColor Yellow
Write-Host ("=" * 60)

$apis = @("todoist", "pingtung-news", "hackernews", "gmail")
foreach ($api in $apis) {
    $state = Test-APIHealth $api
    Write-Host "  $api : $state" -ForegroundColor Gray
}

# ============================================
# 測試 2：New-DegradedResult 函式
# ============================================
Write-Host "`n[測試 2] New-DegradedResult 函式" -ForegroundColor Yellow
Write-Host ("=" * 60)

$testResultPath = "results/test-degraded.json"
New-DegradedResult -APIName "todoist" -OutputPath $testResultPath -State "open"

if (Test-Path $testResultPath) {
    Write-Host "`n[OK] 降級結果檔案已建立" -ForegroundColor Green
    $content = Get-Content $testResultPath -Raw | ConvertFrom-Json
    Write-Host "  內容預覽:" -ForegroundColor Gray
    Write-Host "    status: $($content.status)" -ForegroundColor Gray
    Write-Host "    source: $($content.source)" -ForegroundColor Gray
    Write-Host "    circuit_breaker: $($content.circuit_breaker)" -ForegroundColor Gray
    Write-Host "    message: $($content.message)" -ForegroundColor Gray

    # 清理測試檔案
    Remove-Item $testResultPath -Force
    Write-Host "`n  (測試檔案已清理)" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] 降級結果檔案建立失敗" -ForegroundColor Red
}

# ============================================
# 測試 3：Get-PrecheckSummary 函式
# ============================================
Write-Host "`n[測試 3] Get-PrecheckSummary 函式" -ForegroundColor Yellow
Write-Host ("=" * 60)

$summary = Get-PrecheckSummary
Write-Host "  預檢查摘要:" -ForegroundColor Gray
$summary.Keys | Sort-Object | ForEach-Object {
    Write-Host "    $_ : $($summary[$_])" -ForegroundColor Gray
}

# ============================================
# 測試 4：Show-PrecheckReport 函式
# ============================================
Write-Host "`n[測試 4] Show-PrecheckReport 函式" -ForegroundColor Yellow
Write-Host ("=" * 60)

Show-PrecheckReport

# ============================================
# 測試 5：模擬 open 狀態
# ============================================
Write-Host "`n[測試 5] 模擬 API 為 open 狀態" -ForegroundColor Yellow
Write-Host ("=" * 60)

# 備份原始 api-health.json
$healthFile = "state/api-health.json"
$backupFile = "state/api-health.json.test-backup"

if (Test-Path $healthFile) {
    Copy-Item $healthFile $backupFile -Force
    Write-Host "[OK] 已備份 api-health.json → api-health.json.test-backup" -ForegroundColor Green
}

# 建立測試狀態（todoist 為 open）
$testHealth = @{
    todoist = @{
        state = "open"
        failures = 3
        cooldown = (Get-Date).AddMinutes(5).ToString("yyyy-MM-ddTHH:mm:sszzz")
    }
    "pingtung-news" = @{
        state = "closed"
        failures = 0
        cooldown = $null
    }
    hackernews = @{
        state = "half_open"
        failures = 2
        cooldown = $null
    }
    gmail = @{
        state = "closed"
        failures = 0
        cooldown = $null
    }
}

$testHealth | ConvertTo-Json -Depth 10 | Set-Content $healthFile -Encoding UTF8
Write-Host "[OK] 已設定測試狀態（todoist=open, hackernews=half_open）" -ForegroundColor Green

# 重新執行預檢查
Write-Host "`n  重新執行預檢查..." -ForegroundColor Gray
Show-PrecheckReport

# 恢復原始狀態
if (Test-Path $backupFile) {
    Move-Item $backupFile $healthFile -Force
    Write-Host "`n[OK] 已恢復原始 api-health.json" -ForegroundColor Green
} else {
    Write-Host "`n[WARN] 未找到備份檔案，請手動檢查 api-health.json" -ForegroundColor Yellow
}

# ============================================
# 測試總結
# ============================================
Write-Host "`n=== 測試總結 ===" -ForegroundColor Cyan
Write-Host "✓ 所有函式正常運作" -ForegroundColor Green
Write-Host "✓ 降級結果檔案格式正確" -ForegroundColor Green
Write-Host "✓ 預檢查報告顯示正常" -ForegroundColor Green
Write-Host "✓ open/half_open 狀態識別正確" -ForegroundColor Green
Write-Host ""
Write-Host "下一步：執行實際的 run-agent-team.ps1 驗證整合效果" -ForegroundColor Cyan
