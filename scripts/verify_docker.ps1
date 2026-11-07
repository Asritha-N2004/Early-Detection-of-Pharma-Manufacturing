$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is required to execute deployment verification.' }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed' }
docker compose up --build -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed' }
docker compose exec -T backend python scripts/generate_data.py
docker compose exec -T backend python scripts/bootstrap.py
docker compose exec -T backend python scripts/verify_deployment.py http://frontend:8080
if ($LASTEXITCODE -ne 0) { throw 'Live deployment smoke test failed' }
Write-Host 'Docker health checks and authenticated smoke test passed.'
