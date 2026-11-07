$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.env')) {
    $taskPassword = python -c "import secrets; print(secrets.token_urlsafe(24))"
    $taskJwt = python -c "import secrets; print(secrets.token_urlsafe(48))"
    @("BOOTSTRAP_PASSWORD=$taskPassword", "JWT_SECRET=$taskJwt", 'DEPLOYMENT_MODE=demo') | Set-Content -LiteralPath '.env'
    Write-Host 'Generated local credentials in the ignored .env file. Username: admin.'
}
Get-Content -LiteralPath '.env' | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}
python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
Write-Host 'Starting API at http://127.0.0.1:8010. Run frontend separately as documented.'
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
