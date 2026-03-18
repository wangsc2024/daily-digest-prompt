# ============================================================
# 開機啟動排程安裝腳本（需以管理員身份執行）
# 用途：
#   1. 修正 Claude_bot-startup → 改用 startup.ps1（同時啟動 bot + groq-relay）
#   2. 新建 RAG_Skill_startup → 啟動 Qdrant + API Server + Web Frontend
# ============================================================
#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) {
    Write-Host "[*] $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}
function Write-Fail([string]$msg) {
    Write-Host "    [FAIL] $msg" -ForegroundColor Red
}

# ── 觸發條件：開機後延遲 30 秒 ─────────────────────────────
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = "PT30S"   # ISO 8601: 30 秒

# ── 以當前使用者帳號執行，登入後才觸發 ─────────────────────
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal   = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 72) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$ProjectDir = $PSScriptRoot

# ──────────────────────────────────────────────────────────────
# 1. 修正 Claude_bot-startup
# ──────────────────────────────────────────────────────────────
Write-Step "修正 Claude_bot-startup（加入 groq-relay 啟動）..."

$botAction = New-ScheduledTaskAction `
    -Execute "pwsh.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -File `"$ProjectDir\bot\startup.ps1`"" `
    -WorkingDirectory "$ProjectDir\bot"

try {
    $existing = Get-ScheduledTask -TaskName "Claude_bot-startup" -ErrorAction SilentlyContinue
    if ($existing) {
        Set-ScheduledTask -TaskName "\Claude_bot-startup" `
            -Action $botAction `
            -Principal $principal `
            -Settings $settings | Out-Null
        Write-OK "Claude_bot-startup 已更新"
    } else {
        Register-ScheduledTask -TaskName "Claude_bot-startup" `
            -Action $botAction `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description "Bot.js + Groq-Relay 開機啟動（延遲 30s 等待網路）" | Out-Null
        Write-OK "Claude_bot-startup 已新建"
    }
} catch {
    Write-Fail "Claude_bot-startup 失敗：$_"
}

# ──────────────────────────────────────────────────────────────
# 2. 新建 RAG_Skill_startup
# ──────────────────────────────────────────────────────────────
Write-Step "新建 RAG_Skill_startup（Qdrant + API + Web）..."

$ragAction = New-ScheduledTaskAction `
    -Execute "pwsh.exe" `
    -Argument '-NoProfile -WindowStyle Hidden -File "D:\Source\RAG_Skill\scripts\startup-task.ps1"' `
    -WorkingDirectory "D:\Source\RAG_Skill"

try {
    $existing = Get-ScheduledTask -TaskName "RAG_Skill_startup" -ErrorAction SilentlyContinue
    if ($existing) {
        Set-ScheduledTask -TaskName "\RAG_Skill_startup" `
            -Action $ragAction `
            -Principal $principal `
            -Settings $settings | Out-Null
        Write-OK "RAG_Skill_startup 已更新"
    } else {
        Register-ScheduledTask -TaskName "RAG_Skill_startup" `
            -Action $ragAction `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description "RAG 知識庫開機啟動（Qdrant:6333 / API:3000 / Web:5173，延遲 30s）" | Out-Null
        Write-OK "RAG_Skill_startup 已新建"
    }
} catch {
    Write-Fail "RAG_Skill_startup 失敗：$_"
}

# ── 驗證 ────────────────────────────────────────────────────
Write-Host ""
Write-Step "驗證排程狀態..."
foreach ($name in @("Claude_bot-startup", "RAG_Skill_startup")) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        Write-OK "$name — State: $($t.State)"
    } else {
        Write-Fail "$name — 未找到"
    }
}

Write-Host ""
Write-Host "完成！下次開機後 30 秒將自動啟動所有服務。" -ForegroundColor Green
