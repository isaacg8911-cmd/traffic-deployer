# Select a Traffic Deployer AppUpdate zip or unzipped folder.
# Used by FORCE_UPDATE / APPLY_UPDATE / FINISH_UPDATE.
#
# Interactive menu + optional Windows browse dialogs.
# Writes the chosen path to -OutFile (required for reliable .bat capture).
#
# Look for: TrafficDeployer-AppUpdate-1.0.12.zip (versioned) or legacy .zip
#        or: unzipped folder containing TrafficDeployer.exe

param(
    [ValidateSet("zip", "folder", "auto")]
    [string]$Kind = "auto",
    [string]$SearchDir = "",
    [string]$Title = "Select Traffic Deployer AppUpdate",
    [Parameter(Mandatory = $true)]
    [string]$OutFile
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms | Out-Null

if (-not $SearchDir) { $SearchDir = (Get-Location).Path }
$SearchDir = [System.IO.Path]::GetFullPath($SearchDir)

function Get-AppUpdateZips([string]$Dir) {
    $list = New-Object System.Collections.Generic.List[object]
    if (-not (Test-Path -LiteralPath $Dir)) { return @() }
    Get-ChildItem -LiteralPath $Dir -File -Filter "TrafficDeployer-AppUpdate-*.zip" -ErrorAction SilentlyContinue |
        ForEach-Object { $list.Add($_) }
    $legacy = Join-Path $Dir "TrafficDeployer-AppUpdate.zip"
    if (Test-Path -LiteralPath $legacy) { $list.Add((Get-Item -LiteralPath $legacy)) }
    return @($list | Sort-Object LastWriteTime -Descending)
}

function Resolve-UpdateRoot([string]$Path) {
    if (-not $Path) { return $null }
    $Path = $Path.Trim().Trim('"')
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        if ($Path -like "*.zip") { return (Resolve-Path -LiteralPath $Path).Path }
        return $null
    }
    if (Test-Path -LiteralPath (Join-Path $Path "TrafficDeployer.exe")) {
        return (Resolve-Path -LiteralPath $Path).Path
    }
    $nested = Join-Path $Path "TrafficDeployer"
    if (Test-Path -LiteralPath (Join-Path $nested "TrafficDeployer.exe")) {
        return (Resolve-Path -LiteralPath $nested).Path
    }
    return $null
}

function Get-UpdateFolders([string]$Dir) {
    $paths = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $Dir)) { return @() }
    $direct = Resolve-UpdateRoot $Dir
    if ($direct -and (Test-Path -LiteralPath $direct -PathType Container)) {
        $paths.Add($direct)
    }
    Get-ChildItem -LiteralPath $Dir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $r = Resolve-UpdateRoot $_.FullName
        if ($r -and (Test-Path -LiteralPath $r -PathType Container) -and -not $paths.Contains($r)) {
            $paths.Add($r)
        }
    }
    return @(
        $paths |
            ForEach-Object { Get-Item -LiteralPath $_ } |
            Sort-Object LastWriteTime -Descending
    )
}

function Browse-Zip {
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = $Title
    $dlg.Filter = "AppUpdate zip|TrafficDeployer-AppUpdate*.zip;TrafficDeployer-AppUpdate.zip|Zip (*.zip)|*.zip|All|*.*"
    $dlg.InitialDirectory = $SearchDir
    $dlg.Multiselect = $false
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        return $dlg.FileName
    }
    return $null
}

function Browse-Folder {
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = "$Title - unzipped folder with TrafficDeployer.exe"
    if (Test-Path -LiteralPath $SearchDir) { $dlg.SelectedPath = $SearchDir }
    $dlg.ShowNewFolderButton = $false
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        return (Resolve-UpdateRoot $dlg.SelectedPath)
    }
    return $null
}

$candidates = New-Object System.Collections.Generic.List[object]
if ($Kind -eq "zip" -or $Kind -eq "auto") {
    foreach ($z in (Get-AppUpdateZips $SearchDir)) {
        $mb = [math]::Round($z.Length / 1MB)
        $when = $z.LastWriteTime.ToString("yyyy-MM-dd HH:mm")
        $candidates.Add([pscustomobject]@{
                Kind  = "zip"
                Path  = $z.FullName
                Label = "$($z.Name)  ($mb MB, $when)"
            })
    }
}
if ($Kind -eq "folder" -or $Kind -eq "auto") {
    foreach ($f in (Get-UpdateFolders $SearchDir)) {
        $ver = ""
        $vf = Join-Path $f.FullName "VERSION.txt"
        if (Test-Path -LiteralPath $vf) {
            $ver = " v" + ((Get-Content -LiteralPath $vf -TotalCount 1 -ErrorAction SilentlyContinue).Trim())
        }
        $candidates.Add([pscustomobject]@{
                Kind  = "folder"
                Path  = $f.FullName
                Label = "FOLDER$ver  $($f.FullName)"
            })
    }
}

Write-Host ""
Write-Host $Title
Write-Host "=============================================="
Write-Host "Search folder: $SearchDir"
Write-Host "Expected zip name: TrafficDeployer-AppUpdate-VERSION.zip"
Write-Host "  example: TrafficDeployer-AppUpdate-1.0.12.zip"
Write-Host ""

if ($candidates.Count -gt 0) {
    Write-Host "Found:"
    for ($i = 0; $i -lt $candidates.Count; $i++) {
        Write-Host ("  [{0}] {1}" -f ($i + 1), $candidates[$i].Label)
    }
} else {
    Write-Host "Nothing matched in this folder yet - use Browse."
}

Write-Host ""
Write-Host "  [B] Browse for zip file..."
Write-Host "  [F] Browse for unzipped folder..."
Write-Host "  [Q] Cancel"
Write-Host ""
Write-Host "Or type a full path / paste here."
$choice = Read-Host "Choice"
if (-not $choice) { exit 1 }
$choice = $choice.Trim().Trim([char]34)

$selected = $null
if ($choice -match "^[Qq]$") {
    exit 1
}
elseif ($choice -match "^[Bb]$") {
    $selected = Browse-Zip
}
elseif ($choice -match "^[Ff]$") {
    $selected = Browse-Folder
}
elseif ($choice -match "^[0-9]+$") {
    $idx = [int]$choice - 1
    if ($idx -lt 0 -or $idx -ge $candidates.Count) {
        Write-Host "FAIL: invalid number."
        exit 1
    }
    $selected = $candidates[$idx].Path
}
else {
    $selected = Resolve-UpdateRoot $choice
    if (-not $selected -and (Test-Path -LiteralPath $choice)) {
        $selected = $choice
    }
}

if (-not $selected) {
    Write-Host "FAIL: nothing selected."
    exit 1
}

$resolved = Resolve-UpdateRoot $selected
if (-not $resolved -and $selected -like "*.zip" -and (Test-Path -LiteralPath $selected)) {
    $resolved = (Resolve-Path -LiteralPath $selected).Path
}
if (-not $resolved) {
    Write-Host "FAIL: not a valid AppUpdate zip or TrafficDeployer folder:"
    Write-Host "  $selected"
    exit 1
}

$dir = Split-Path -Parent $OutFile
if ($dir -and -not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
Set-Content -LiteralPath $OutFile -Value $resolved -Encoding ascii -NoNewline
Write-Host ""
Write-Host "Selected: $resolved"
exit 0
