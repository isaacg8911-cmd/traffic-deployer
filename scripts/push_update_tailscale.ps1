# Home PC: serve AppUpdate on Tailscale and push the work laptop to pull it.
# USB not required. Laptop must be online on the same Tailscale tailnet.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$ReleasesDir = if ($env:TD_RELEASES_DIR) { $env:TD_RELEASES_DIR.Trim() } else { "C:\TDReleases" }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "FAIL: .venv missing - run START.bat first."
    exit 1
}

function Get-TdTailscaleExe {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($path in @(
            "$env:ProgramFiles\Tailscale\tailscale.exe",
            "${env:ProgramFiles(x86)}\Tailscale\tailscale.exe"
        )) {
        if (Test-Path -LiteralPath $path) { return $path }
    }
    return $null
}

function Test-TdPortOpen([string]$Ip, [int]$Port, [int]$TimeoutMs = 1500) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $tcp.BeginConnect($Ip, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if (-not $ok) { return $false }
        $tcp.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $tcp.Close()
    }
}

Write-Host ""
Write-Host "Traffic Deployer - UPDATE LAPTOP OVER TAILSCALE"
Write-Host "==============================================="
Write-Host ""

$ts = Get-TdTailscaleExe
if (-not $ts) {
    Write-Host "FAIL: Tailscale is not installed on this PC."
    exit 1
}

$manifest = Join-Path $ReleasesDir "version.json"
if (-not (Test-Path -LiteralPath $manifest)) {
    Write-Host "FAIL: $manifest missing. Run BUILD_WIFI_UPDATE.bat / PUBLISH_APP_UPDATE.bat first."
    exit 1
}

$peerJson = & $Py -c "import json; from core.update_hosts import windows_peers_online, tailscale_self_dns, tailscale_self_ip4, list_base_urls; print(json.dumps({'peers': windows_peers_online(), 'dns': tailscale_self_dns(), 'ip': tailscale_self_ip4(), 'bases': list_base_urls()}))"
$info = $peerJson | ConvertFrom-Json
$laptop = $null
foreach ($p in @($info.peers)) {
    $name = [string]$p.hostname
    if ($name -match "laptop") { $laptop = $p; break }
}
if (-not $laptop -and $info.peers -and $info.peers.Count -gt 0) {
    $laptop = $info.peers[0]
}
if (-not $laptop) {
    Write-Host "FAIL: no other Windows Tailscale node is online."
    Write-Host "On the work laptop: open Tailscale and wait until it shows Connected."
    exit 1
}

Write-Host ("Laptop : {0}  {1}  ({2})" -f $laptop.hostname, $laptop.ip, $laptop.dns)
Write-Host ("Home   : {0}  {1}" -f $info.dns, $info.ip)
Write-Host ""

# Serve on Tailscale 100.x (127.0.0.1:8765 is MindLink OS — do not steal it).
$listenOk = $false
if ($info.ip) {
    try {
        $r = Invoke-WebRequest -Uri ("http://{0}:8765/version.json" -f $info.ip) -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -ge 200) { $listenOk = $true }
    } catch { }
}
if (-not $listenOk) {
    Write-Host "Starting update server on LAN + Tailscale..."
    $serve = Join-Path $Root "scripts\serve_td_releases.py"
    Start-Process -FilePath $Py -ArgumentList "`"$serve`"" -WorkingDirectory $Root -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(12)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri ("http://{0}:8765/version.json" -f $info.ip) -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -ge 200) { $listenOk = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 400
    }
}
if (-not $listenOk) {
    Write-Host "FAIL: update server did not bind Tailscale IP $($info.ip):8765"
    Write-Host "Is another program using that address, or is Tailscale down?"
    exit 1
}
Write-Host ("Server : http://{0}:8765/version.json" -f $info.ip)

$copied = $false
$adminShare = "\\{0}\C$\TrafficDeployer" -f $laptop.ip
if (Test-TdPortOpen $laptop.ip 445 1200) {
    if (Test-Path -LiteralPath $adminShare) {
        Write-Host "Copying updater into laptop C:\TrafficDeployer via admin share..."
        foreach ($name in @(
                "WIFI_UPDATE_NOW.bat", "wifi_update_now.ps1", "td_update_homes.ps1",
                "td_update_poll.ps1", "refresh_update_channel.ps1"
            )) {
            $src = Join-Path (Join-Path $Root "packaging") $name
            if (Test-Path $src) {
                Copy-Item -Force $src (Join-Path $adminShare $name)
            }
        }
        $copied = $true
    }
}

$sshTried = $false
$sshOk = $false
if (Test-TdPortOpen $laptop.ip 22 1200) {
    $sshTried = $true
    $target = if ($laptop.dns) { $laptop.dns } else { $laptop.hostname }
    Write-Host "Trying Tailscale SSH apply on $target ..."
    try {
        & $ts ssh $target -- powershell -NoProfile -ExecutionPolicy Bypass -File C:\TrafficDeployer\wifi_update_now.ps1
        if ($LASTEXITCODE -eq 0) { $sshOk = $true }
    } catch { }
}

$dropped = $false
$pack = Join-Path $Root "packaging"
$dropFiles = @(
    (Join-Path $pack "WIFI_UPDATE_NOW.bat"),
    (Join-Path $pack "wifi_update_now.ps1"),
    (Join-Path $pack "td_update_homes.ps1")
) | Where-Object { Test-Path $_ }
if ($dropFiles.Count -gt 0) {
    $targetName = [string]$laptop.hostname
    Write-Host "Sending updater to laptop via Tailscale file send..."
    try {
        & $ts file cp @dropFiles "${targetName}:"
        if ($LASTEXITCODE -eq 0) { $dropped = $true }
    } catch {
        Write-Host ("  file send failed: " + $_.Exception.Message)
    }
}

Write-Host ""
Write-Host "========== PUSH STATUS =========="
Write-Host ("Laptop online : {0} ({1})" -f $laptop.hostname, $laptop.ip)
Write-Host ("Server ready  : http://{0}:8765/" -f $info.ip)
Write-Host ("Admin share   : {0}" -f $(if ($copied) { "copied updater" } else { "not open (normal on field laptop)" }))
Write-Host ("SSH apply     : {0}" -f $(if ($sshOk) { "OK" } elseif ($sshTried) { "failed" } else { "not enabled on laptop" }))
Write-Host ("Taildrop      : {0}" -f $(if ($dropped) { "WIFI_UPDATE_NOW.bat sent. Accept on the laptop, then double-click." } else { "not sent" }))
Write-Host "================================="
Write-Host ""
if ($sshOk) {
    Write-Host "Done. Laptop applied the update over Tailscale SSH."
    exit 0
}

Write-Host 'Laptop is on Tailscale but remote execute is closed (no SSH / admin share).'
Write-Host "Server is running. The laptop applies when:"
Write-Host "  1. OPEN_APP.bat  (channel check + in-app update), or"
Write-Host "  2. WIFI_UPDATE_NOW.bat (Taildrop / Downloads), or"
Write-Host "  3. td_update_poll scheduled task (after first successful update)"
Write-Host ""
Write-Host "Leave the update server running until the zip download finishes."
exit 0
