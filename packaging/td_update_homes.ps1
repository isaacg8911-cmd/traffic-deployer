# Shared Tailscale + LAN home-PC discovery for work-laptop update scripts.
$ErrorActionPreference = "Continue"

function Add-TdBase {
    param(
        [System.Collections.Generic.List[string]]$List,
        [string]$Url
    )
    $clean = ([string]$Url).Trim().TrimEnd("/")
    if (-not $clean) { return }
    if (-not ($clean -like "http://*" -or $clean -like "https://*")) {
        $clean = "http://$clean"
        $clean = $clean.TrimEnd("/")
    }
    $key = $clean.ToLowerInvariant()
    foreach ($existing in $List) {
        if ($existing.ToLowerInvariant() -eq $key) { return }
    }
    [void]$List.Add($clean)
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

function Get-TdHomeBases {
    $bases = New-Object "System.Collections.Generic.List[string]"
    $roots = @()
    if ($PSScriptRoot) { $roots += $PSScriptRoot }
    $roots += (Get-Location).Path
    foreach ($root in $roots) {
        $txt = Join-Path $root "wifi_update_home.txt"
        if (Test-Path -LiteralPath $txt) {
            Get-Content -LiteralPath $txt | ForEach-Object { Add-TdBase $bases $_ }
        }
    }
    $ts = Get-TdTailscaleExe
    if ($ts) {
        try {
            $raw = & $ts status --json 2>$null
            $j = $raw | ConvertFrom-Json
            if ($j.Peer) {
                foreach ($prop in $j.Peer.PSObject.Properties) {
                    $p = $prop.Value
                    if (-not $p.Online) { continue }
                    $os = [string]$p.OS
                    if ($os -match "android|ios|ipad") { continue }
                    $dns = ([string]$p.DNSName).TrimEnd(".")
                    if ($dns) { Add-TdBase $bases ("http://{0}:8765" -f $dns) }
                    foreach ($ip in @($p.TailscaleIPs)) {
                        if ([string]$ip -match "^\d+\.\d+\.\d+\.\d+$") {
                            Add-TdBase $bases ("http://{0}:8765" -f $ip)
                        }
                    }
                }
            }
        } catch { }
    }
    Add-TdBase $bases "http://100.93.14.32:8765"
    Add-TdBase $bases "http://192.168.1.30:8765"
    return $bases
}

function Get-TdReachableHome {
    param([int]$TimeoutSec = 8)
    foreach ($base in Get-TdHomeBases) {
        try {
            $r = Invoke-WebRequest -Uri ($base + "/version.json") -UseBasicParsing -TimeoutSec $TimeoutSec
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
                return $base
            }
        } catch { }
    }
    return $null
}

function Register-TdUpdatePoll {
    param([string]$InstallDir)
    if (-not $InstallDir) { return }
    $ps1 = Join-Path $InstallDir "td_update_poll.ps1"
    if (-not (Test-Path -LiteralPath $ps1)) { return }
    $tr = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $ps1 + '"'
    & schtasks.exe /Create /TN "TrafficDeployerTailscaleUpdate" /SC MINUTE /MO 15 /TR $tr /F 2>$null | Out-Null
}
