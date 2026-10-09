param(
    [string]$BaseUrl = 'http://localhost:8080'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$indexPath = Join-Path $repoRoot 'frontend\dist\index.html'

if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Frontend build missing: $indexPath. Run npm.cmd run build in frontend."
}

$builtIndex = Get-Content -LiteralPath $indexPath -Raw
$builtScript = [regex]::Match($builtIndex, 'src="(/assets/[^\"]+\.js)"').Groups[1].Value
if (-not $builtScript) {
    throw "Cannot find the JavaScript asset in $indexPath."
}

$servedIndex = (Invoke-WebRequest "$BaseUrl/login" -UseBasicParsing -TimeoutSec 10).Content
$servedScript = [regex]::Match($servedIndex, 'src="(/assets/[^\"]+\.js)"').Groups[1].Value
if ($servedScript -ne $builtScript) {
    throw "Caddy is serving a different frontend build. Expected $builtScript from $indexPath; received $servedScript. Check Caddy's root and reload C:\crm_new\Caddyfile."
}

$health = Invoke-RestMethod "$BaseUrl/api/health" -TimeoutSec 10
if ($health.status -ne 'ok') {
    throw "The public /api/health route did not return status ok."
}

try {
    Invoke-WebRequest "$BaseUrl/api/auth/login" -Method Post -ContentType 'application/json' -Body '{"username":"__deployment_check__","password":"__invalid__"}' -UseBasicParsing -TimeoutSec 10 | Out-Null
    throw 'The login check unexpectedly accepted invalid credentials.'
} catch {
    $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
    if ($status -ne 401) {
        throw "The login endpoint did not reach the application and database (expected HTTP 401 for invalid credentials; received $status). $($_.Exception.Message)"
    }
}

Write-Host "PASS: Caddy serves $builtScript from this checkout."
Write-Host 'PASS: /api/health reaches the backend.'
Write-Host 'PASS: /api/auth/login reaches the backend and rejects invalid credentials.'
