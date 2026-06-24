# QualiFlow local dev starter (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Checking Docker..."
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running. Start Docker Desktop and retry."
    exit 1
}

Write-Host "Starting Docker services..."
docker compose up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Waiting for API..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -TimeoutSec 2
        if ($r.status -eq "ok") { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Host "API not ready yet. Check: docker compose logs api"
} else {
    Write-Host "API ready at http://127.0.0.1:8000"
}

Write-Host "Starting frontend..."
Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run dev
