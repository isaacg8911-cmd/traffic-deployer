# App-only update for work laptop: exe + _internal + web. No map (tds_data stays on laptop).
# Home PC: BUILD_APP_UPDATE.bat  ->  dist\TrafficDeployer-AppUpdate\TrafficDeployer (~800 MB, no zip)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "FAIL: Run START.bat once on this PC first (.venv missing)."
    exit 1
}

Write-Host "Building portable exe..."
& (Join-Path $Root "scripts\build_portable.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Staging app-only update folder (no map, no zip)..."
& $Py (Join-Path $Root "scripts\pack_app_update.py")
exit $LASTEXITCODE
