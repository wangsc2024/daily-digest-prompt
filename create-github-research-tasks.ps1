#Requires -Version 7.0
# 建立 Todoist GitHub 專案深度研究單次任務

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

# 任務定義（2 個 GitHub 專案深度研究任務）
$tasks = @(
    @{
        content = "Skill_Seekers 專案深度研究與架構洞察"
        description = "深度研究 https://github.com/yusufkaraaslan/Skill_Seekers.git 專案，深度思維其邏輯架構與設計模式，分析其可優化 daily-digest-prompt 專案的設計（如 Skill 索引機制、文件驅動架構等），識別可借鏡的技術與最佳實踐，撰寫完整研究洞察報告並寫入知識庫。重點：架構設計決策分析、可移植技術識別、與本專案的適配性評估。"
        labels = @("研究", "深度思維", "知識庫", "GitHub")
        priority = 3
        due = @{
            string = "today"
        }
    },
    @{
        content = "gemini-cli 專案深度研究與架構洞察"
        description = "深度研究 https://github.com/wangsc2024/gemini-cli.git 專案，深度思維其邏輯架構與設計模式，分析其可優化 daily-digest-prompt 專案的設計（如 CLI 互動模式、Agent 協作機制等），識別可借鏡的技術與最佳實踐，撰寫完整研究洞察報告並寫入知識庫。重點：CLI 設計模式、Agent 編排策略、與本專案的協同可能性。"
        labels = @("研究", "深度思維", "知識庫", "GitHub")
        priority = 3
        due = @{
            string = "today"
        }
    }
)

Write-Host "===== 建立 Todoist GitHub 專案深度研究單次任務 ====="

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
Write-Host "執行完成後，研究洞察報告會寫入知識庫（localhost:3000）。"
