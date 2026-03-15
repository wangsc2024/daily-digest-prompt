# Sync Nebula Strike game from temp to game_web
# Run from: D:\Source\daily-digest-prompt
$srcDir = Join-Path $PSScriptRoot "nebula-strike"
$destDir = "D:\Source\game_web\games\nebula-strike"
$metaPath = "D:\Source\game_web\js\gameMetadata.js"

if (-not (Test-Path $srcDir)) {
    Write-Error "Source not found: $srcDir"
    exit 1
}

# Create dest and copy
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item -Path "$srcDir\*" -Destination $destDir -Recurse -Force
Write-Host "Copied game files to $destDir"

# Add nebula-strike to gameMetadata if not already present
$content = Get-Content $metaPath -Raw -Encoding UTF8
if ($content -match "nebula-strike") {
    Write-Host "nebula-strike already in gameMetadata"
} else {
    $entry = @"

  ,{
    id: 'nebula-strike',
    title: '星雲殲擊',
    subtitle: 'Nebula Strike',
    icon: '🌟',
    description: '創意豎向太空射擊！在星雲隧道中迎戰三種 AI 敵機、Boss 波次、武器升級與連擊計分。支援鍵盤與觸控。',
    tags: ['射擊', '創意', '街機'],
    category: '經典',
    path: 'games/nebula-strike/',
    featured: true,
    difficulty: '中等',
    playtime: '自由遊玩'
  }
"@
    # Insert before the closing ];
    $content = $content -replace '(\r?\n)(  \{)', "$entry`$1  {"
    # Fix: we need to add before the last }; - find "  }" then "];" pattern
    # Simpler: add after digdug entry's closing }
    $content = $content -replace '(\}\s*\];)', "$entry`n  `$1"
    if ($content -eq $LASTMATCH) {
        Write-Warn "Could not find insertion point"
    } else {
        Set-Content -Path $metaPath -Value $content -Encoding UTF8 -NoNewline:$false
        Write-Host "Added nebula-strike to gameMetadata.js"
    }
}

Write-Host "Sync complete."
