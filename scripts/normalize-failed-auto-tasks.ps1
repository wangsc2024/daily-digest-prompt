# 一次性：將 state/failed-auto-tasks.json 的 task_key 從 @{key=...} 正規化為純 key，並依 key 合併重複條目
# 使用方式：pwsh -ExecutionPolicy Bypass -File scripts/normalize-failed-auto-tasks.ps1
$ErrorActionPreference = "Stop"
$AgentDir = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path "$AgentDir\state\failed-auto-tasks.json")) {
    Write-Host "state/failed-auto-tasks.json not found, nothing to do."
    exit 0
}
$data = Get-Content "$AgentDir\state\failed-auto-tasks.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$keyAliases = @{
    "logaudit" = "log_audit"; "gitpush" = "git_push"; "techresearch" = "tech_research"
    "aideepresearch" = "ai_deep_research"; "unsloth" = "unsloth_research"; "aigithub" = "ai_github_research"
    "aismartcity" = "ai_smart_city"; "aisysdev" = "ai_sysdev"; "skillaudit" = "skill_audit"
    "qaoptimize" = "qa_optimize"; "systeminsight" = "system_insight"; "selfheal" = "self_heal"
    "githubscout" = "github_scout"; "ai_github" = "ai_github_research"; "ai_deep" = "ai_deep_research"
    "ai_smart" = "ai_smart_city"; "creative_game" = "creative_game_optimize"; "podcastcreate" = "podcast_create"
    "podcast" = "podcast_create"
}
function NormalizeKey([string]$s) {
    $raw = if ($s -match '^@{key=([^;]+)') { $Matches[1].Trim() } else { $s }
    $n = $raw -replace '-', '_'
    if ($keyAliases.ContainsKey($n)) { $keyAliases[$n] } else { $n }
}
$normalized = @()
foreach ($e in $data.entries) {
    $e.task_key = NormalizeKey $e.task_key
    $normalized += $e
}
# 依 task_key 合併：保留 consecutive_count 最大、last_failed_at 最新的一筆
$byKey = @{}
foreach ($e in $normalized) {
    $k = $e.task_key
    if (-not $byKey.ContainsKey($k)) {
        $byKey[$k] = $e
    } else {
        $cur = $byKey[$k]
        $keep = if ([int]$e.consecutive_count -gt [int]$cur.consecutive_count) { $e }
                elseif ($e.last_failed_at -gt $cur.last_failed_at) { $e }
                else { $cur }
        $byKey[$k] = $keep
    }
}
$data.entries = @($byKey.Values)
$data.updated_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
$data | ConvertTo-Json -Depth 5 | Set-Content "$AgentDir\state\failed-auto-tasks.json" -Encoding UTF8
Write-Host "Normalized and deduped failed-auto-tasks.json: $($data.entries.Count) entries."
