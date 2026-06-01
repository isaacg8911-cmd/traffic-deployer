# Build a zip for another Windows laptop (no git, no venv, no huge map by default).
param(
    [switch]$IncludeMap,
    [switch]$IncludeRoadGraph
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$Stage = Join-Path $Dist "TrafficDeployer-portable"
$Version = (Select-String -Path (Join-Path $Root "version.py") -Pattern 'APP_VERSION = "([^"]+)"').Matches.Groups[1].Value
$ZipName = "TrafficDeployer-v$Version-portable.zip"
$ZipPath = Join-Path $Dist $ZipName

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage | Out-Null

$Include = @(
    "*.py", "*.bat", "*.md", "*.txt",
    "core", "web", "scripts", "demo_data"
)
$ExcludeDir = @(".venv", ".git", "dist", "__pycache__", "cache")
$ExcludeFile = @("*.pyc", "_diag_py.txt", "pmtiles.exe", "pmtiles", "_pmtiles_dl.zip")

foreach ($item in $Include) {
    $src = Join-Path $Root $item
    if (-not (Test-Path $src)) { continue }
    if (Test-Path $src -PathType Container) {
        Copy-Item $src (Join-Path $Stage (Split-Path $item -Leaf)) -Recurse -Force
    } else {
        Copy-Item $src $Stage -Force
    }
}
Remove-Item (Join-Path $Stage "_diag_py.txt") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Stage "_run_test.py") -Force -ErrorAction SilentlyContinue

# Strip junk from copied trees
Get-ChildItem $Stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Empty tds_data placeholder (shift saves land here; not in zip from .gitignore patterns)
$Tds = Join-Path $Stage "tds_data"
New-Item -ItemType Directory -Path $Tds -Force | Out-Null
Set-Content -Path (Join-Path $Tds "README.txt") -Value "Shift saves and optional map copy go here. See PORTABLE_INSTALL.txt."

if ($IncludeMap) {
    $pm = Join-Path $Root "tds_data\california.pmtiles"
    if (Test-Path $pm) {
        Write-Host "Including california.pmtiles (~1.4 GB)..."
        Copy-Item $pm (Join-Path $Tds "california.pmtiles")
    } else {
        Write-Warning "california.pmtiles not found - zip will download on first START.bat"
    }
}

if ($IncludeRoadGraph) {
    $rg = Join-Path $Root "tds_data\road_graph.graphml"
    if (Test-Path $rg) {
        Copy-Item $rg (Join-Path $Tds "road_graph.graphml")
    }
}

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
New-Item -ItemType Directory -Path $Dist -Force | Out-Null
Compress-Archive -Path $Stage -DestinationPath $ZipPath -CompressionLevel Optimal

$Mb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host ""
Write-Host ("Built: {0} ({1} megabytes)" -f $ZipPath, $Mb)
Write-Host "Unzip on work laptop and run START.bat"
if (-not $IncludeMap) {
    Write-Host "Tip: re-run with -IncludeMap to bundle offline basemap (large zip)."
}
