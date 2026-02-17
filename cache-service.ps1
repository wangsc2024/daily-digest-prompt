# ============================================
# Centralized Cache Service
# ============================================
# Usage:
#   cache-service.ps1 -Action Get -Source todoist
#   cache-service.ps1 -Action Set -Source todoist -Data '{"tasks": [...]}'
#   cache-service.ps1 -Action Check -Source todoist

param(
    [Parameter(Mandatory)]
    [ValidateSet("Get", "Set", "Check")]
    [string]$Action,

    [Parameter(Mandatory)]
    [string]$Source,

    [string]$Data
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AgentDir = $PSScriptRoot
$CacheDir = "$AgentDir\cache"
$ConfigFile = "$AgentDir\config\cache-policy.yaml"
$StatsFile = "$AgentDir\state\cache-stats.json"

# 確保目錄存在
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
New-Item -ItemType Directory -Force -Path "$AgentDir\state" | Out-Null

# 讀取 TTL 配置
$policy = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Yaml
$ttl = $policy.sources.$Source.ttl_minutes

# === Action: Check ===
if ($Action -eq "Check") {
    $cacheFile = "$CacheDir\$Source.json"

    if (-not (Test-Path $cacheFile)) {
        return @{ valid = $false; reason = "not_exists"; action = "call_api" } | ConvertTo-Json
    }

    try {
        $cache = Get-Content $cacheFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        # JSON 損壞，刪除並重建
        Remove-Item $cacheFile -Force
        return @{ valid = $false; reason = "corrupted"; action = "call_api" } | ConvertTo-Json
    }

    $cachedAt = [DateTime]::Parse($cache.cached_at)
    $nowUtc = (Get-Date).ToUniversalTime()

    # 健全性檢查：時間戳不得晚於當前時間
    if ($cachedAt -gt $nowUtc) {
        Write-Warning "快取時間戳異常（未來時間: $($cache.cached_at)），視為無效"
        Remove-Item $cacheFile -Force
        return @{ valid = $false; reason = "future_timestamp"; action = "call_api" } | ConvertTo-Json
    }

    $ageMinutes = ($nowUtc - $cachedAt).TotalMinutes

    if ($ageMinutes -le $ttl) {
        return @{ valid = $true; age_minutes = [math]::Round($ageMinutes, 1); ttl_minutes = $ttl; action = "use_cache" } | ConvertTo-Json
    } else {
        return @{ valid = $false; age_minutes = [math]::Round($ageMinutes, 1); ttl_minutes = $ttl; reason = "expired"; action = "call_api" } | ConvertTo-Json
    }
}

# === Action: Get ===
if ($Action -eq "Get") {
    $cacheFile = "$CacheDir\$Source.json"

    if (-not (Test-Path $cacheFile)) {
        Write-Error "快取不存在: $Source"
        exit 1
    }

    $cache = Get-Content $cacheFile -Raw -Encoding UTF8 | ConvertFrom-Json

    # 更新統計：cache hit
    Update-CacheStats -Source $Source -Type "hit"

    return $cache.data | ConvertTo-Json -Depth 10
}

# === Action: Set ===
if ($Action -eq "Set") {
    $cacheFile = "$CacheDir\$Source.json"

    $utcNow = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

    $cacheObj = @{
        cached_at = $utcNow
        ttl_minutes = $ttl
        source = $Source
        data = ($Data | ConvertFrom-Json)
    }

    $cacheObj | ConvertTo-Json -Depth 10 | Set-Content $cacheFile -Encoding UTF8

    # 更新統計：cache write
    Update-CacheStats -Source $Source -Type "write"

    Write-Host "快取已更新: $Source (TTL: $ttl 分鐘)"
}

# === 統計追蹤函數 ===
function Update-CacheStats {
    param([string]$Source, [string]$Type)  # Type: hit, miss, write

    $today = (Get-Date).ToString("yyyy-MM-dd")

    if (Test-Path $StatsFile) {
        $stats = Get-Content $StatsFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        $stats = @{ date = $today; hits = 0; misses = 0; writes = 0; by_source = @{} }
    }

    # 若日期變更，重置統計
    if ($stats.date -ne $today) {
        $stats = @{ date = $today; hits = 0; misses = 0; writes = 0; by_source = @{} }
    }

    # 更新計數
    switch ($Type) {
        "hit" { $stats.hits++ }
        "miss" { $stats.misses++ }
        "write" { $stats.writes++ }
    }

    # 更新 by_source
    if (-not $stats.by_source.$Source) {
        $stats.by_source.$Source = @{ hits = 0; misses = 0; writes = 0 }
    }
    $stats.by_source.$Source.$Type++

    $stats | ConvertTo-Json -Depth 5 | Set-Content $StatsFile -Encoding UTF8
}
