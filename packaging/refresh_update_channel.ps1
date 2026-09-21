# Refresh tds_data\update_channel.json from the first reachable home PC (Tailscale or LAN).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "td_update_homes.ps1")

$install = $here
if (-not (Test-Path (Join-Path $install "TrafficDeployer.exe"))) {
    $install = (Get-Location).Path
}
$dataDir = Join-Path $install "tds_data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$homeBase = Get-TdReachableHome
if (-not $homeBase) {
    Write-Host "WARN: could not reach home PC update server over Tailscale or LAN."
    Write-Host "On home PC run UPDATE_LAPTOP.bat (or C:\TDReleases\SERVE_RELEASES.bat)."
    exit 1
}

$channel = @{
    version_url  = ($homeBase + "/version.json")
    version_urls = @(Get-TdHomeBases | ForEach-Object { $_ + "/version.json" })
} | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $dataDir "update_channel.json") -Value $channel -Encoding utf8
Write-Host "Channel OK -> tds_data\update_channel.json ($homeBase)"
Register-TdUpdatePoll -InstallDir $install
exit 0
