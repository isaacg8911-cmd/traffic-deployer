# One zip for work laptop: exe + california map + road graph.
# Home PC: BUILD_WORK_LAPTOP.bat  ->  dist\TrafficDeployer-WorkLaptop.zip
# Gate:    scripts/ship_work_laptop_gate.py  (must pass before USB copy)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "FAIL: Run START.bat once on this PC first (.venv missing)."
    exit 1
}

Write-Host "Preflight (source tree)..."
& $Py (Join-Path $Root "scripts\quick_preflight.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARN: preflight reported critical issues - fix map/fonts before field."
}

Write-Host "Building portable exe..."
& (Join-Path $Root "scripts\build_portable.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Packing work-laptop dist + zip..."
& $Py (Join-Path $Root "scripts\pack_work_laptop_dist.py")
exit $LASTEXITCODE
