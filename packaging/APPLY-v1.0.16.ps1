# One-shot apply of AppUpdate 1.0.16. No other scripts required.
$ErrorActionPreference = "Stop"
$Expected = "1.0.16"
$ZipName = "TrafficDeployer-AppUpdate.zip"
$Bases = @(
    "http://192.168.1.30:8765",
    "http://100.93.14.32:8765",
    "http://msi.tailaf9051.ts.net:8765"
)

Write-Host ""
Write-Host "Traffic Deployer - APPLY v$Expected"
Write-Host "================================="
Write-Host ""

Write-Host "Closing TrafficDeployer.exe..."
Get-Process -Name "TrafficDeployer" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4

$install = $null
foreach ($c in @(
        "C:\TrafficDeployer",
        "D:\TrafficDeployer",
        (Join-Path $env:USERPROFILE "TrafficDeployer"),
        (Join-Path $env:USERPROFILE "Desktop\TrafficDeployer")
    )) {
    if ((Test-Path (Join-Path $c "TrafficDeployer.exe")) -and
        (Test-Path (Join-Path $c "tds_data\california.pmtiles"))) {
        $install = $c
        break
    }
}
if (-not $install) {
    $install = (Read-Host "Type install folder (must contain tds_data\california.pmtiles)").Trim().Trim('"')
}
if (-not (Test-Path (Join-Path $install "TrafficDeployer.exe"))) {
    throw "No TrafficDeployer.exe in $install"
}
if (-not (Test-Path (Join-Path $install "tds_data\california.pmtiles"))) {
    throw "No offline map in $install\tds_data - wrong folder"
}

Write-Host "Install: $install"
$verNow = "unknown"
$vf = Join-Path $install "VERSION.txt"
if (Test-Path $vf) { $verNow = (Get-Content $vf -Raw).Trim() }
Write-Host "Current VERSION.txt: $verNow"

$homeBase = $null
foreach ($b in $Bases) {
    try {
        $r = Invoke-WebRequest -Uri ($b + "/version.json") -UseBasicParsing -TimeoutSec 8
        $man = $r.Content | ConvertFrom-Json
        if ([string]$man.version -eq $Expected) { $homeBase = $b; break }
        Write-Host ("  $b is v" + $man.version + " (want $Expected)")
    } catch {
        Write-Host "  miss $b"
    }
}
if (-not $homeBase) { throw "Cannot reach home PC serving v$Expected. Is UPDATE_LAPTOP server running?" }
Write-Host "Home: $homeBase"

$stage = Join-Path $env:TEMP "td_apply_$Expected"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$zipPath = Join-Path $stage "update.zip"
$unpack = Join-Path $stage "extracted"
$zipUrl = "$homeBase/$ZipName"

Write-Host "Downloading ~300 MB from $zipUrl"
Write-Host "Keep this window open..."
$wc = New-Object System.Net.WebClient
try {
    $wc.DownloadFile($zipUrl, $zipPath)
} finally {
    $wc.Dispose()
}
$mb = [math]::Round((Get-Item $zipPath).Length / 1MB)
Write-Host "Downloaded $mb MB"
if ($mb -lt 100) { throw "Zip too small ($mb MB) - not the AppUpdate. Got a web page instead?" }

Write-Host "Unzipping..."
Expand-Archive -LiteralPath $zipPath -DestinationPath $unpack -Force
$src = Join-Path $unpack "TrafficDeployer"
if (-not (Test-Path (Join-Path $src "TrafficDeployer.exe"))) {
    $found = Get-ChildItem -Path $unpack -Filter TrafficDeployer.exe -Recurse | Select-Object -First 1
    if (-not $found) { throw "Zip missing TrafficDeployer.exe" }
    $src = $found.DirectoryName
}

Write-Host "Installing into $install (keeping tds_data)..."
Copy-Item -Force (Join-Path $src "TrafficDeployer.exe") (Join-Path $install "TrafficDeployer.exe")
$internal = Join-Path $install "_internal"
if (Test-Path $internal) { Remove-Item -Recurse -Force $internal }
Copy-Item -Recurse -Force (Join-Path $src "_internal") $internal
$webSrc = Join-Path $src "web"
if (Test-Path $webSrc) {
    $webDst = Join-Path $install "web"
    if (Test-Path $webDst) { Remove-Item -Recurse -Force $webDst }
    Copy-Item -Recurse -Force $webSrc $webDst
}
foreach ($name in @("OPEN_APP.bat", "VERSION.txt", "READ_ME_FIRST.txt")) {
    $p = Join-Path $src $name
    if (Test-Path $p) { Copy-Item -Force $p (Join-Path $install $name) }
}
Set-Content -LiteralPath (Join-Path $install "VERSION.txt") -Value $Expected -Encoding ascii
$dataDir = Join-Path $install "tds_data"
Set-Content -LiteralPath (Join-Path $dataDir ".update_applied") -Value $Expected -Encoding ascii
$st = Join-Path $dataDir ".update_state.json"
if (Test-Path $st) { Remove-Item -Force $st }
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue

$got = (Get-Content (Join-Path $install "VERSION.txt") -Raw).Trim()
Write-Host ""
Write-Host "========== PROOF =========="
Write-Host "VERSION.txt : $got"
Write-Host "Expected    : $Expected"
Write-Host "Install     : $install"
Write-Host "==========================="
if ($got -ne $Expected) { throw "VERSION.txt is $got not $Expected - did not apply." }

Write-Host "Starting app..."
$open = Join-Path $install "OPEN_APP.bat"
if (Test-Path $open) {
    Start-Process -FilePath $open -WorkingDirectory $install
} else {
    Start-Process -FilePath (Join-Path $install "TrafficDeployer.exe") -WorkingDirectory $install
}
Write-Host "Done. Window title MUST say v$Expected."
