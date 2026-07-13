# Publish AppUpdate zip to C:\TDReleases for home Wi-Fi auto-update.
# Run after BUILD_APP_UPDATE.bat (or use BUILD_WIFI_UPDATE.bat for both).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$ReleasesDir = if ($env:TD_RELEASES_DIR) { $env:TD_RELEASES_DIR.Trim() } else { "C:\TDReleases" }
$Port = if ($env:TD_RELEASES_PORT) { [int]$env:TD_RELEASES_PORT } else { 8765 }
$ZipName = "TrafficDeployer-AppUpdate.zip"
$ZipSrc = Join-Path (Join-Path $Root "dist") $ZipName

if (-not (Test-Path $ZipSrc)) {
    Write-Host "FAIL: $ZipSrc missing - run BUILD_APP_UPDATE.bat first."
    exit 1
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "FAIL: .venv missing - run START.bat first."
    exit 1
}
$AppVersion = & $Py -c "from version import APP_VERSION; print(APP_VERSION)"
$AppVersion = $AppVersion.Trim()
if (-not $AppVersion) {
    Write-Host "FAIL: could not read APP_VERSION from version.py"
    exit 1
}

function Get-LanIp {
    $candidates = @()
    try {
        $candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            Select-Object -ExpandProperty IPAddress
    } catch {
        $candidates = ipconfig | Select-String -Pattern "IPv4 Address[^\:]*:\s*(\d+\.\d+\.\d+\.\d+)" |
            ForEach-Object { $_.Matches[0].Groups[1].Value } |
            Where-Object { $_ -notlike "127.*" -and $_ -notlike "169.254.*" }
    }
    foreach ($ip in $candidates) {
        if ($ip -like "192.168.*") { return $ip }
    }
    foreach ($ip in $candidates) {
        if ($ip -like "10.*") { return $ip }
    }
    foreach ($ip in $candidates) {
        if ($ip -match "^172\.(1[6-9]|2[0-9]|3[0-1])\.") { return $ip }
    }
    if ($candidates.Count -gt 0) { return $candidates[0] }
    return "192.168.1.50"
}

$LanIp = Get-LanIp
$BaseUrl = "http://${LanIp}:${Port}"
$DownloadUrl = "$BaseUrl/$ZipName"

New-Item -ItemType Directory -Force -Path $ReleasesDir | Out-Null
Copy-Item -Force $ZipSrc (Join-Path $ReleasesDir $ZipName)

$sha256 = (Get-FileHash -Path (Join-Path $ReleasesDir $ZipName) -Algorithm SHA256).Hash.ToLower()

$manifestPath = Join-Path $ReleasesDir "version.json"
$channelPath = Join-Path $ReleasesDir "update_channel.json"
& $Py -c @"
import json, pathlib
from datetime import datetime, timezone
manifest = {
    'version': '$AppVersion',
    'download_url': '$DownloadUrl',
    'sha256': '$sha256',
    'notes': 'App update v$AppVersion (map + tds_data stay on laptop)',
    'published': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
}
pathlib.Path(r'$manifestPath').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
channel = {'version_url': '$BaseUrl/version.json'}
pathlib.Path(r'$channelPath').write_text(json.dumps(channel, indent=2) + '\n', encoding='utf-8')
"@ | Out-Null

$exampleSrc = Join-Path (Join-Path $Root "packaging") "update_channel.example.json"
if (Test-Path $exampleSrc) {
    Copy-Item -Force $exampleSrc (Join-Path $ReleasesDir "update_channel.example.json")
}

$serveBat = Join-Path (Join-Path $Root "packaging") "SERVE_RELEASES.bat"
if (Test-Path $serveBat) {
    Copy-Item -Force $serveBat (Join-Path $ReleasesDir "SERVE_RELEASES.bat")
}

$guide = Join-Path (Join-Path $Root "packaging") "WIFI_AUTO_UPDATE.txt"
if (Test-Path $guide) {
    Copy-Item -Force $guide (Join-Path $ReleasesDir "WIFI_AUTO_UPDATE.txt")
}

Write-Host ""
Write-Host "PUBLISH OK - Wi-Fi auto-update channel ready"
Write-Host "  Folder : $ReleasesDir"
Write-Host "  Version: v$AppVersion"
Write-Host "  LAN IP : $LanIp"
Write-Host "  Manifest: $manifestPath"
Write-Host "  Zip    : $(Join-Path $ReleasesDir $ZipName)"
Write-Host ""
Write-Host "HOME PC - start server (leave running while laptop updates):"
Write-Host "  $ReleasesDir\SERVE_RELEASES.bat"
Write-Host ""
Write-Host "WORK LAPTOP - one-time (copy file, keep tds_data\):"
Write-Host "  Copy  $channelPath"
Write-Host "    to  <install>\tds_data\update_channel.json"
Write-Host "  Example install: C:\TrafficDeployer\tds_data\update_channel.json"
Write-Host ""
Write-Host "TEST: on work laptop at home Wi-Fi, open app (online mode)."
Write-Host "  App checks $BaseUrl/version.json and applies if newer."
Write-Host ""
exit 0
