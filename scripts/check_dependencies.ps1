$ErrorActionPreference = 'Stop'
# Uses the official pip-audit vulnerability database client; requires network.
python -m pip install pip-audit
if ($LASTEXITCODE -ne 0) { throw 'pip-audit installation failed' }
python -m pip_audit -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Review reported dependency findings before deployment' }
Push-Location frontend
try {
    npm audit --omit=dev
    if ($LASTEXITCODE -ne 0) { throw 'Review frontend dependency findings before deployment' }
} finally { Pop-Location }
