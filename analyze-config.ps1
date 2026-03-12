# analyze-config.ps1 — 配置膨脹度量工具
# 追蹤 9 個指標，寫入 state/config-metrics.json（保留最近 30 筆）
# 用法：
#   .\analyze-config.ps1              # 顯示當前度量值 + 警示
#   .\analyze-config.ps1 -Trend       # 額外顯示近 7 筆趨勢
#   .\analyze-config.ps1 -Brief       # 僅計算並寫入，不顯示（供 check-health 呼叫）
param(
    [switch]$Trend,
    [switch]$Brief
)

$AgentDir = $PSScriptRoot

$metrics = [ordered]@{
    timestamp           = (Get-Date -Format "o")
    claude_md_lines     = if (Test-Path "$AgentDir\CLAUDE.md") { (Get-Content "$AgentDir\CLAUDE.md" | Measure-Object -Line).Lines } else { 0 }
    skill_index_lines   = if (Test-Path "$AgentDir\skills\SKILL_INDEX.md") { (Get-Content "$AgentDir\skills\SKILL_INDEX.md" | Measure-Object -Line).Lines } else { 0 }
    yaml_total_lines    = ([int](Get-ChildItem "$AgentDir\config\*.yaml" -ErrorAction SilentlyContinue | ForEach-Object { (Get-Content $_ | Measure-Object -Line).Lines } | Measure-Object -Sum).Sum)
    yaml_count          = (Get-ChildItem "$AgentDir\config\*.yaml" -ErrorAction SilentlyContinue | Measure-Object).Count
    skill_count         = (Get-ChildItem "$AgentDir\skills\*\SKILL.md" -ErrorAction SilentlyContinue | Measure-Object).Count
    auto_task_templates = (Get-ChildItem "$AgentDir\templates\auto-tasks\*.md" -ErrorAction SilentlyContinue | Measure-Object).Count
    team_prompt_count   = (Get-ChildItem "$AgentDir\prompts\team\*.md" -ErrorAction SilentlyContinue | Measure-Object).Count
    hook_lines          = ([int](Get-ChildItem "$AgentDir\hooks\*.py" -ErrorAction SilentlyContinue | ForEach-Object { (Get-Content $_ | Measure-Object -Line).Lines } | Measure-Object -Sum).Sum)
}

# 警戒閾值（與 config/benchmark.yaml config_complexity 同步）
$thresholds = @{
    claude_md_lines     = 300    # > 300 行警告
    yaml_total_lines    = 3500   # > 3500 行警告（系統自動生成配置，原 3000 過窄）
    skill_index_lines   = 150    # > 150 行警告
    auto_task_templates = 25     # > 25 個模板警告
}

# 讀取歷史（若有）
$histFile = "$AgentDir\state\config-metrics.json"
$history = if (Test-Path $histFile) {
    try { @(Get-Content $histFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { @() }
} else { @() }

# 寫入歷史（保留最近 30 筆）
$history = @($history) + @($metrics) | Select-Object -Last 30
$history | ConvertTo-Json -Depth 3 | Set-Content $histFile -Encoding UTF8

if (-not $Brief) {
    Write-Host ""
    Write-Host "[配置膨脹度量]" -ForegroundColor Cyan
    Write-Host ("  {0,-26} {1,6}  {2}" -f "指標", "現值", "說明") -ForegroundColor DarkCyan
    Write-Host "  $('─' * 50)" -ForegroundColor DarkGray

    foreach ($key in $thresholds.Keys) {
        $val = $metrics[$key]
        if ($null -eq $val) { $val = 0 }
        $thr = $thresholds[$key]
        $icon = if ($val -gt $thr) { "⚠️" } else { "✅" }
        $color = if ($val -gt $thr) { "Yellow" } else { "Green" }
        Write-Host ("  {0} {1,-24} {2,6}  (警戒 {3})" -f $icon, $key, $val, $thr) -ForegroundColor $color
    }

    # 非警戒指標
    Write-Host ""
    foreach ($key in @("yaml_count", "skill_count", "team_prompt_count", "hook_lines")) {
        $val = $metrics[$key]
        if ($null -eq $val) { $val = 0 }
        Write-Host ("  ℹ️  {0,-24} {1,6}" -f $key, $val) -ForegroundColor Cyan
    }

    if ($Trend -and $history.Count -gt 1) {
        Write-Host ""
        Write-Host "  [近 7 筆趨勢]" -ForegroundColor DarkCyan
        $recent = $history | Select-Object -Last 7
        Write-Host ("  {0,-18} {1,8} {2,8} {3,7} {4,7}" -f "時間", "CLAUDE", "YAML總", "Skills", "Template") -ForegroundColor DarkCyan
        foreach ($m in $recent) {
            $ts = if ($m.timestamp -and $m.timestamp.Length -ge 16) { $m.timestamp.Substring(0, 16) } else { "unknown" }
            Write-Host ("  {0,-18} {1,8} {2,8} {3,7} {4,7}" -f $ts, $m.claude_md_lines, $m.yaml_total_lines, $m.skill_count, $m.auto_task_templates) -ForegroundColor Gray
        }
    }
}

# 返回超出警戒的指標數量（供 check-health.ps1 呼叫時使用）
$violationCount = ($thresholds.Keys | Where-Object { [int]($metrics[$_]) -gt $thresholds[$_] }).Count
if ($Brief) {
    if ($violationCount -eq 0) {
        Write-Output "✅ 所有指標正常（CLAUDE.md $($metrics.claude_md_lines)行 / YAML $($metrics.yaml_total_lines)行 / Templates $($metrics.auto_task_templates)個）"
    } else {
        $violators = @($thresholds.Keys | Where-Object { [int]($metrics[$_]) -gt $thresholds[$_] } | ForEach-Object { "$_=$($metrics[$_])" })
        Write-Output "⚠️  $violationCount 個指標超出警戒：$($violators -join ', ')"
    }
} else {
    return $violationCount
}
