# Wi-Fi / Tailscale AppUpdate — no USB. Run from WIFI_UPDATE_NOW.bat.
$ErrorActionPreference = "Stop"

$urls = @(
    "http://100.93.14.32:8765",
    "http://192.168.1.30:8765"
)

Write-Host ""
Write-Host "Traffic Deployer - WIFI UPDATE NOW"
Write-Host "=================================="
Write-Host ""

Write-Host "Finding home PC update server..."
$homeBase = $null
foreach ($u in $urls) {
    $base = $u.TrimEnd("/")
    try {
        $r = Invoke-WebRequest -Uri ($base + "/version.json") -UseBasicParsing -TimeoutSec 8
        if ($r.StatusCode -ge 200) {
            $homeBase = $base
            Write-Host "OK $base"
            break
        }
    } catch {
        Write-Host ("miss " + $base + " - " + $_.Exception.Message)
    }
}
if (-not $homeBase) {
    Write-Host ""
    Write-Host "FAIL: cannot reach home PC."
    Write-Host "Tried:"
    $urls | ForEach-Object { Write-Host ("  " + $_) }
    Write-Host ""
    Write-Host "On HOME PC: keep update server running."
    Write-Host "On LAPTOP: open Edge to http://100.93.14.32:8765/"
    exit 1
}

$install = $null
$candidates = @(
    "C:\TrafficDeployer",
    "D:\TrafficDeployer",
    (Join-Path $env:USERPROFILE "TrafficDeployer")
)
foreach ($c in $candidates) {
    if ((Test-Path (Join-Path $c "TrafficDeployer.exe")) -and
        (Test-Path (Join-Path $c "tds_data\california.pmtiles"))) {
        $install = $c
        break
    }
}
if (-not $install) {
    $install = Read-Host "Type install folder (e.g. C:\TrafficDeployer)"
    $install = $install.Trim().Trim('"')
}
if (-not (Test-Path (Join-Path $install "TrafficDeployer.exe"))) {
    Write-Host "FAIL: no TrafficDeployer.exe in $install"
    exit 1
}
if (-not (Test-Path (Join-Path $install "tds_data\california.pmtiles"))) {
    Write-Host "FAIL: no map in $install\tds_data - wrong folder?"
    exit 1
}

Write-Host "Home server: $homeBase"
Write-Host "Install: $install"
$verFile = Join-Path $install "VERSION.txt"
$cur = if (Test-Path $verFile) { (Get-Content $verFile -Raw).Trim() } else { "unknown" }
Write-Host "Current: v$cur"
Write-Host ""

Write-Host "Closing app if open..."
Get-Process -Name "TrafficDeployer" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Write-Host "Fetching version.json ..."
$manifest = Invoke-RestMethod -Uri ($homeBase + "/version.json") -TimeoutSec 20
$latest = [string]$manifest.version
$zipUrl = [string]$manifest.download_url
$sha = [string]$manifest.sha256
if (-not $zipUrl) { throw "version.json missing download_url" }

# Always pull zip from the reachable home base (LAN IP in manifest may be blocked).
$zipName = ($zipUrl -split "/")[-1]
if (-not $zipName) { $zipName = "TrafficDeployer-AppUpdate.zip" }
$zipUrl = $homeBase + "/" + $zipName

Write-Host "Latest : v$latest"
Write-Host "Zip URL: $zipUrl"
Write-Host ""

$dataDir = Join-Path $install "tds_data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if ($cur -eq $latest) {
    Write-Host "Already on v$latest. Writing update channel and launching."
} else {
    $staging = Join-Path $dataDir "wifi_update_now"
    if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    $zipPath = Join-Path $staging "update.zip"
    $unpack = Join-Path $staging "extracted"

    Write-Host "Downloading ~300 MB - keep this window open..."
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 900
    if ($sha) {
        $h = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLower()
        if ($h -ne $sha.ToLower()) { throw "checksum mismatch: $h" }
        Write-Host "Checksum OK"
    }
    Write-Host ("Downloaded " + [math]::Round((Get-Item $zipPath).Length / 1MB) + " MB")

    Write-Host "Unzipping..."
    Expand-Archive -LiteralPath $zipPath -DestinationPath $unpack -Force

    $src = Join-Path $unpack "TrafficDeployer"
    if (-not (Test-Path (Join-Path $src "TrafficDeployer.exe"))) {
        $found = Get-ChildItem -Path $unpack -Filter TrafficDeployer.exe -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $found) { throw "zip missing TrafficDeployer.exe" }
        $src = $found.DirectoryName
    }

    Write-Host "Installing into $install (tds_data kept)..."
    Copy-Item -Force (Join-Path $src "TrafficDeployer.exe") (Join-Path $install "TrafficDeployer.exe")
    $internalDst = Join-Path $install "_internal"
    if (Test-Path $internalDst) { Remove-Item -Recurse -Force $internalDst }
    Copy-Item -Recurse -Force (Join-Path $src "_internal") $internalDst
    $webSrc = Join-Path $src "web"
    $webDst = Join-Path $install "web"
    if (Test-Path $webSrc) {
        if (Test-Path $webDst) { Remove-Item -Recurse -Force $webDst }
        Copy-Item -Recurse -Force $webSrc $webDst
    }
    foreach ($name in @("OPEN_APP.bat", "VERSION.txt", "READ_ME_FIRST.txt", "wifi_update_home.txt")) {
        $p = Join-Path $src $name
        if (Test-Path $p) { Copy-Item -Force $p (Join-Path $install $name) }
    }
    Set-Content -LiteralPath (Join-Path $install "VERSION.txt") -Value $latest -Encoding ascii
    Set-Content -LiteralPath (Join-Path $dataDir ".update_applied") -Value $latest -Encoding ascii
    $state = Join-Path $dataDir ".update_state.json"
    if (Test-Path $state) { Remove-Item -Force $state }
    Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
}

$channel = @{ version_url = ($homeBase + "/version.json") } | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $dataDir "update_channel.json") -Value $channel -Encoding utf8
Write-Host "Channel written."

Write-Host ""
Write-Host "========== PROOF =========="
Write-Host ("VERSION.txt: " + (Get-Content (Join-Path $install "VERSION.txt") -Raw).Trim())
Write-Host "Expected : $latest"
Write-Host "Install  : $install"
Write-Host "==========================="
Write-Host ""
Write-Host "Starting app..."
$open = Join-Path $install "OPEN_APP.bat"
if (Test-Path $open) {
    Start-Process -FilePath $open -WorkingDirectory $install
} else {
    Start-Process -FilePath (Join-Path $install "TrafficDeployer.exe") -WorkingDirectory $install
}
Write-Host "Done. Window title must show v$latest."
