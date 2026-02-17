#Requires -Version 7.0
# 建立 Todoist 系統審查週期任務

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

# 任務定義（每個目標 3 個時段 = 6 個任務）
$tasks = @(
    # QA System 審查（3 次/日）
    @{
        content = "QA System 7維度審查優化"
        description = "對 d:\Source\qa_system 進行完整的 7 維度系統審查（資訊安全、系統架構、系統品質、系統工作流、技術棧、系統文件、系統完成度），產出報告並自動修正簡單問題（最多 5 項）。"
        labels = @("系統審查", "品質評估")
        priority = 2
        due = @{
            string = "every day at 11:00"
            is_recurring = $true
        }
    },
    @{
        content = "QA System 7維度審查優化"
        description = "對 d:\Source\qa_system 進行完整的 7 維度系統審查（資訊安全、系統架構、系統品質、系統工作流、技術棧、系統文件、系統完成度），產出報告並自動修正簡單問題（最多 5 項）。"
        labels = @("系統審查", "品質評估")
        priority = 2
        due = @{
            string = "every day at 16:00"
            is_recurring = $true
        }
    },
    @{
        content = "QA System 7維度審查優化"
        description = "對 d:\Source\qa_system 進行完整的 7 維度系統審查（資訊安全、系統架構、系統品質、系統工作流、技術棧、系統文件、系統完成度），產出報告並自動修正簡單問題（最多 5 項）。"
        labels = @("系統審查", "品質評估")
        priority = 2
        due = @{
            string = "every day at 22:15"
            is_recurring = $true
        }
    },
    # game 目錄審查（3 次/日）
    @{
        content = "game 目錄遊戲 7維度審查優化"
        description = "智能優先級審查 d:\Source\game 目錄中的遊戲（每次 2 個，依最久未審或分數最低排序），進行 7 維度系統審查，產出報告並自動修正簡單問題（最多 5 項）。**動態掃描**：每次自動偵測新遊戲並加入追蹤。追蹤檔案：context/game-audit-tracker.json"
        labels = @("系統審查", "遊戲優化", "品質評估")
        priority = 2
        due = @{
            string = "every day at 11:30"
            is_recurring = $true
        }
    },
    @{
        content = "game 目錄遊戲 7維度審查優化"
        description = "智能優先級審查 d:\Source\game 目錄中的遊戲（每次 2 個，依最久未審或分數最低排序），進行 7 維度系統審查，產出報告並自動修正簡單問題（最多 5 項）。**動態掃描**：每次自動偵測新遊戲並加入追蹤。追蹤檔案：context/game-audit-tracker.json"
        labels = @("系統審查", "遊戲優化", "品質評估")
        priority = 2
        due = @{
            string = "every day at 16:30"
            is_recurring = $true
        }
    },
    @{
        content = "game 目錄遊戲 7維度審查優化"
        description = "智能優先級審查 d:\Source\game 目錄中的遊戲（每次 2 個，依最久未審或分數最低排序），進行 7 維度系統審查，產出報告並自動修正簡單問題（最多 5 項）。**動態掃描**：每次自動偵測新遊戲並加入追蹤。追蹤檔案：context/game-audit-tracker.json"
        labels = @("系統審查", "遊戲優化", "品質評估")
        priority = 2
        due = @{
            string = "every day at 22:45"
            is_recurring = $true
        }
    }
)

Write-Host "===== 建立 Todoist 系統審查週期任務 ====="

foreach ($task in $tasks) {
    $body = $task | ConvertTo-Json -Depth 5 -Compress
    Write-Host "`n建立任務：$($task.content) @ $($task.due.string)"

    try {
        $response = Invoke-RestMethod -Uri $baseUri -Method Post -Headers $headers -Body $body
        Write-Host "✅ 成功建立任務 ID: $($response.id)"
    } catch {
        Write-Host "❌ 建立失敗：$($_.Exception.Message)" -ForegroundColor Red
        Write-Host "   回應：$($_.ErrorDetails.Message)"
    }
}

Write-Host "`n===== 完成 ====="
Write-Host "請執行以下指令驗證："
Write-Host "  pwsh -File check-token.ps1"
