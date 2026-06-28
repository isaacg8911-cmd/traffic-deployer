# Build portable Traffic Deployer folder (PyInstaller one-folder).
# Requires: .venv with pip install pyinstaller
# Run from repo root:  powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Create .venv first (START.bat or python -m venv .venv)"
    exit 1
}

& $Py -m pip install -q pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip install pyinstaller failed"
    exit 1
}

$Spec = Join-Path $Root "traffic_deployer.spec"
if (-not (Test-Path $Spec)) {
    Write-Host "Missing traffic_deployer.spec"
    exit 1
}

& $Py -m PyInstaller $Spec --noconfirm
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Out = Join-Path $Root "dist\TrafficDeployer"
Write-Host ""
Write-Host "Built: $Out"
Write-Host "Copy tds_data\ (road graph + basemap) beside the exe for offline field use."
exit 0
