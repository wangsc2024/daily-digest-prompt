$token = $env:TODOIST_API_TOKEN
if (-not $token) {
    Write-Host "ERROR: TODOIST_API_TOKEN not found"
    exit 1
}

$headers = @{
    "Authorization" = "Bearer $token"
}

try {
    $response = Invoke-RestMethod -Uri "https://api.todoist.com/api/v1/tasks?filter=today" -Headers $headers -Method Get
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
