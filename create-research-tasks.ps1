#Requires -Version 7.0
# 建立 Todoist 專案研究單次任務

$ErrorActionPreference = "Stop"

# 取得 Todoist API Token
$token = [System.Environment]::GetEnvironmentVariable('TODOIST_API_TOKEN', 'User')
if (-not $token) { $token = [System.Environment]::GetEnvironmentVariable('TODOIST_API_TOKEN', 'Machine') }
if (-not $token) { Write-Error "TODOIST_API_TOKEN not found"; exit 1 }

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json; charset=utf-8"
}

$baseUri = "https://api.todoist.com/api/v1/tasks"

# 任務定義（2 個單次研究任務）
$tasks = @(
    @{
        content = "account_management 專案系統設計研究"
        description = "使用 system-audit Skill 對 d:\source\account_management 進行 7 維度完整審查，分析系統設計的優劣點（架構模式、安全設計、程式碼品質、技術選型等），撰寫深度研究報告並寫入知識庫。重點：不僅評分，更要深入分析設計決策的優缺點與改進方向。"
        labels = @("系統審查", "研究", "知識庫")
        priority = 3
        due = @{
            string = "today"
        }
    },
    @{
        content = "atomic_habits_pwa 專案系統設計研究"
        description = "使用 system-audit Skill 對 d:\source\atomic_habits_pwa 進行 7 維度完整審查，分析系統設計的優劣點（PWA 架構、狀態管理、離線策略、效能優化等），撰寫深度研究報告並寫入知識庫。重點：不僅評分，更要深入分析 PWA 設計模式的實作品質與最佳實踐。"
        labels = @("系統審查", "研究", "知識庫")
        priority = 3
        due = @{
            string = "today"
        }
    }
)

Write-Host "===== 建立 Todoist 專案研究單次任務 ====="

foreach ($task in $tasks) {
    $body = $task | ConvertTo-Json -Depth 5 -Compress
    Write-Host "`n建立任務：$($task.content)"

    try {
        $response = Invoke-RestMethod -Uri $baseUri -Method Post -Headers $headers -Body $body
        Write-Host "✅ 成功建立任務 ID: $($response.id)"
    } catch {
        Write-Host "❌ 建立失敗：$($_.Exception.Message)" -ForegroundColor Red
        Write-Host "   回應：$($_.ErrorDetails.Message)"
    }
}

Write-Host "`n===== 完成 ====="
Write-Host "這些任務已加入今日待辦，Todoist Agent 會自動執行。"
Write-Host "執行完成後，研究報告會寫入知識庫（localhost:3000）。"
