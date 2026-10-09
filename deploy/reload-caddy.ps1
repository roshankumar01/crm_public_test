param(
    [string]$CaddyExe
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repoRoot 'Caddyfile'

if (-not $CaddyExe) {
    $running = Get-Process -Name caddy -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($running) { $CaddyExe = $running.Path }
}
if (-not $CaddyExe) {
    $command = Get-Command caddy.exe -ErrorAction SilentlyContinue
    if ($command) { $CaddyExe = $command.Source }
}
if (-not $CaddyExe -and (Test-Path -LiteralPath 'C:\caddy\caddy.exe')) {
    $CaddyExe = 'C:\caddy\caddy.exe'
}
if (-not $CaddyExe -or -not (Test-Path -LiteralPath $CaddyExe)) {
    throw 'Cannot find caddy.exe. Run this script with -CaddyExe C:\path\to\caddy.exe.'
}

& $CaddyExe validate --config $configPath
if ($LASTEXITCODE -ne 0) { throw "Caddyfile validation failed: $configPath" }

& $CaddyExe reload --config $configPath
if ($LASTEXITCODE -ne 0) { throw 'Caddy reload failed. Check that Caddy is running.' }

Write-Host "Caddy reloaded from $configPath using $CaddyExe"
