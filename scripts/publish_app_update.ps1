# Publish AppUpdate zip to C:\TDReleases for home Wi-Fi auto-update.
# Run after BUILD_APP_UPDATE.bat (or use BUILD_WIFI_UPDATE.bat for both).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$ReleasesDir = if ($env:TD_RELEASES_DIR) { $env:TD_RELEASES_DIR.Trim() } else { "C:\TDReleases" }
$Port = if ($env:TD_RELEASES_PORT) { [int]$env:TD_RELEASES_PORT } else { 8765 }

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

$ZipName = "TrafficDeployer-AppUpdate-$AppVersion.zip"
$ZipSrc = Join-Path (Join-Path $Root "dist") $ZipName
if (-not (Test-Path $ZipSrc)) {
    # Legacy unversioned zip from older builds
    $Legacy = Join-Path (Join-Path $Root "dist") "TrafficDeployer-AppUpdate.zip"
    if (Test-Path $Legacy) {
        Write-Host "WARN: versioned zip missing - using legacy TrafficDeployer-AppUpdate.zip"
        $ZipSrc = $Legacy
        $ZipName = "TrafficDeployer-AppUpdate-$AppVersion.zip"
    } else {
        Write-Host "FAIL: $ZipSrc missing - run BUILD_APP_UPDATE.bat first."
        exit 1
    }
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
# Stable download name — each publish overwrites the previous zip (no version pile-up).
$StableZipName = "TrafficDeployer-AppUpdate.zip"
$DownloadUrl = "$BaseUrl/$StableZipName"

New-Item -ItemType Directory -Force -Path $ReleasesDir | Out-Null
Copy-Item -Force $ZipSrc (Join-Path $ReleasesDir $StableZipName)

# Prune older versioned zips in TDReleases — keep only the live overwrite slot.
Get-ChildItem -LiteralPath $ReleasesDir -File -Filter "TrafficDeployer-AppUpdate-*.zip" -ErrorAction SilentlyContinue |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        Write-Host "  removed stale release zip: $($_.Name)"
    }

$sha256 = (Get-FileHash -Path (Join-Path $ReleasesDir $StableZipName) -Algorithm SHA256).Hash.ToLower()

$manifestPath = Join-Path $ReleasesDir "version.json"
$channelPath = Join-Path $ReleasesDir "update_channel.json"
# Write UTF-8 *without* BOM. Windows PowerShell Set-Content -Encoding utf8 adds BOM
# and breaks wifi_update_now.ps1 Invoke-RestMethod on the work laptop.
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
def write_utf8_no_bom(path, text):
    pathlib.Path(path).write_bytes(text.encode('utf-8'))
write_utf8_no_bom(r'$manifestPath', json.dumps(manifest, indent=2) + '\n')
channel = {'version_url': '$BaseUrl/version.json'}
write_utf8_no_bom(r'$channelPath', json.dumps(channel, indent=2) + '\n')
"@ | Out-Null
$bom = [System.IO.File]::ReadAllBytes($manifestPath)[0..2]
if ($bom[0] -eq 0xEF -and $bom[1] -eq 0xBB -and $bom[2] -eq 0xBF) {
    Write-Host "FAIL: version.json has UTF-8 BOM (breaks work-laptop WIFI_UPDATE_NOW)."
    exit 1
}

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

$indexSrc = Join-Path (Join-Path $Root "packaging") "wifi_update_index.html"
if (Test-Path $indexSrc) {
    Copy-Item -Force $indexSrc (Join-Path $ReleasesDir "index.html")
}

# Base URL for OPEN_APP seed (also written into AppUpdate at pack time).
Set-Content -Path (Join-Path $ReleasesDir "wifi_update_home.txt") -Value $BaseUrl -Encoding ascii

Write-Host ""
Write-Host "PUBLISH OK - Wi-Fi auto-update channel ready"
Write-Host "  Folder : $ReleasesDir"
Write-Host "  Version: v$AppVersion"
Write-Host "  LAN IP : $LanIp"
Write-Host "  Setup  : $BaseUrl/"
Write-Host "  Manifest: $manifestPath"
Write-Host "  Zip    : $(Join-Path $ReleasesDir $StableZipName)"
Write-Host "  (overwrites previous - one zip on the update server)"
Write-Host ""
Write-Host "HOME PC - start server (leave running while laptop updates):"
Write-Host "  $ReleasesDir\SERVE_RELEASES.bat"
Write-Host ""
Write-Host "WORK LAPTOP - first time (Wi-Fi only, no USB):"
Write-Host "  1. Open Edge/Chrome to $BaseUrl/"
Write-Host "  2. Download update_channel.json into C:\TrafficDeployer\tds_data\"
Write-Host "  3. OPEN_APP.bat while ONLINE"
Write-Host ""
Write-Host "TEST: on work laptop at home Wi-Fi, open app (online mode)."
Write-Host "  App checks $BaseUrl/version.json and applies if newer."
Write-Host "  Laptop keeps one overwrite slot under tds_data\update_staging (no version pile-up)."
Write-Host ""
exit 0
