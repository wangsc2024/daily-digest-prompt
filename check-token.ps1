$token = [System.Environment]::GetEnvironmentVariable('TODOIST_API_TOKEN', 'User')
if (-not $token) { $token = [System.Environment]::GetEnvironmentVariable('TODOIST_API_TOKEN', 'Machine') }

if ($token) {
    Write-Host "Token found (length: $($token.Length))"
    try {
        $headers = @{ "Authorization" = "Bearer $token" }
        $resp = Invoke-RestMethod -Uri "https://api.todoist.com/api/v1/tasks/filter?query=today" -Headers $headers -ErrorAction Stop
        Write-Host "API OK - today tasks: $($resp.results.Count)"
        foreach ($t in $resp.results | Select-Object -First 3) {
            Write-Host "  - $($t.content) (p$($t.priority))"
        }
    } catch {
        Write-Host "API ERROR: $($_.Exception.Message)"
    }
} else {
    Write-Host "Token NOT FOUND"
}
