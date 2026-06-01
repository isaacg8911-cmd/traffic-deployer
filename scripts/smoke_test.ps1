# Traffic Deployer — quick smoke test (no GUI map render).
# Full suite: python scripts/smoke_full.py  OR  scripts\smoke.bat
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

Write-Host "[smoke] full headless suite..."
& $Py (Join-Path $Root "scripts\smoke_full.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[smoke] demo workflow..."
& $Py (Join-Path $Root "scripts\demo_workflow.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[smoke] preflight..."
& $Py (Join-Path $Root "scripts\quick_preflight.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[smoke] PASS"
