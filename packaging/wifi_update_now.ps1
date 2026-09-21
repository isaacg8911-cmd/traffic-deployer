# Wi-Fi / Tailscale AppUpdate — no USB. Run from WIFI_UPDATE_NOW.bat.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$homes = Join-Path $here "td_update_homes.ps1"
if (Test-Path -LiteralPath $homes) {
    . $homes
} else {
    function Get-TdHomeBases {
        return @(
            "http://100.93.14.32:8765",
            "http://192.168.1.30:8765"
        )
    }
    function Get-TdReachableHome {
        param([int]$TimeoutSec = 8)
        foreach ($base in Get-TdHomeBases) {
            try {
                $r = Invoke-WebRequest -Uri ($base + "/version.json") -UseBasicParsing -TimeoutSec $TimeoutSec
                if ($r.StatusCode -ge 200) { return $base }
            } catch { }
        }
        return $null
    }
    function Register-TdUpdatePoll { param([string]$InstallDir) }
}

$silent = [string]$env:TD_UPDATE_SILENT -eq "1"

if (-not $silent) {
    Write-Host ""
    Write-Host "Traffic Deployer - WIFI / TAILSCALE UPDATE"
    Write-Host "=========================================="
    Write-Host ""
}

Write-Host "Finding home PC update server (Tailscale then LAN)..."
$homeBase = Get-TdReachableHome
if (-not $homeBase) {
    Write-Host ""
    Write-Host "FAIL: cannot reach home PC."
    Write-Host "Tried:"
    Get-TdHomeBases | ForEach-Object { Write-Host ("  " + $_) }
    Write-Host ""
    Write-Host "On HOME PC: run UPDATE_LAPTOP.bat (leave the server window open)."
    Write-Host "Laptop must be connected to Tailscale (or home Wi-Fi)."
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
    if ($silent) { throw "install folder not found" }
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

if (-not $silent) {
    Write-Host "Closing app if open..."
    Get-Process -Name "TrafficDeployer" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
} elseif (Get-Process -Name "TrafficDeployer" -ErrorAction SilentlyContinue) {
    Write-Host "App is open — skip apply (will retry next poll)."
    exit 0
}

function Read-TdManifest([string]$Url) {
    $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 20
    $text = [string]$resp.Content
    if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
        $text = $text.Substring(1)
    }
    try {
        return ($text | ConvertFrom-Json)
    } catch {
        throw ("version.json is not valid JSON from " + $Url + ": " + $_.Exception.Message)
    }
}

Write-Host "Fetching version.json ..."
$manifest = Read-TdManifest ($homeBase + "/version.json")
if ($manifest -is [string]) {
    throw "version.json did not parse to an object (BOM/encoding?). Re-run PUBLISH_APP_UPDATE.bat on home PC."
}
$latest = [string]$manifest.version
$zipUrl = [string]$manifest.download_url
$sha = [string]$manifest.sha256
if (-not $latest) { throw "version.json missing version" }

$zipName = "TrafficDeployer-AppUpdate.zip"
if ($zipUrl) {
    $fromUrl = ($zipUrl -split "/")[-1]
    if ($fromUrl) { $zipName = $fromUrl }
} else {
    Write-Host "WARN: download_url missing in version.json — using $zipName"
}
$zipUrl = $homeBase + "/" + $zipName

Write-Host "Latest : v$latest"
Write-Host "Zip URL: $zipUrl"
Write-Host ""

$dataDir = Join-Path $install "tds_data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if ($cur -eq $latest) {
    Write-Host "Already on v$latest. Writing update channel."
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
    foreach ($name in @(
            "OPEN_APP.bat", "VERSION.txt", "READ_ME_FIRST.txt", "wifi_update_home.txt",
            "WIFI_UPDATE_NOW.bat", "wifi_update_now.ps1", "td_update_homes.ps1",
            "td_update_poll.ps1", "refresh_update_channel.ps1"
        )) {
        $p = Join-Path $src $name
        if (Test-Path $p) { Copy-Item -Force $p (Join-Path $install $name) }
    }
    Set-Content -LiteralPath (Join-Path $install "VERSION.txt") -Value $latest -Encoding ascii
    Set-Content -LiteralPath (Join-Path $dataDir ".update_applied") -Value $latest -Encoding ascii
    $state = Join-Path $dataDir ".update_state.json"
    if (Test-Path $state) { Remove-Item -Force $state }
    Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
}

$channelUrls = @(Get-TdHomeBases | ForEach-Object { $_ + "/version.json" })
$channel = @{
    version_url  = ($homeBase + "/version.json")
    version_urls = $channelUrls
} | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $dataDir "update_channel.json") -Value $channel -Encoding utf8
Write-Host "Channel written."
Register-TdUpdatePoll -InstallDir $install

Write-Host ""
Write-Host "========== PROOF =========="
Write-Host ("VERSION.txt: " + (Get-Content (Join-Path $install "VERSION.txt") -Raw).Trim())
Write-Host "Expected : $latest"
Write-Host "Install  : $install"
Write-Host "Home     : $homeBase"
Write-Host "==========================="
Write-Host ""

if (-not $silent) {
    Write-Host "Starting app..."
    $open = Join-Path $install "OPEN_APP.bat"
    if (Test-Path $open) {
        Start-Process -FilePath $open -WorkingDirectory $install
    } else {
        Start-Process -FilePath (Join-Path $install "TrafficDeployer.exe") -WorkingDirectory $install
    }
    Write-Host "Done. Window title must show v$latest."
}
