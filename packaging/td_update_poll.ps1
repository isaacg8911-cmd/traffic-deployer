# Silent Tailscale/LAN poller. Skip apply while TrafficDeployer.exe is running.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "td_update_homes.ps1")

if (Get-Process -Name "TrafficDeployer" -ErrorAction SilentlyContinue) {
    exit 0
}

$wifi = Join-Path $here "wifi_update_now.ps1"
if (-not (Test-Path -LiteralPath $wifi)) {
    exit 0
}

$env:TD_UPDATE_SILENT = "1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wifi
exit $LASTEXITCODE
