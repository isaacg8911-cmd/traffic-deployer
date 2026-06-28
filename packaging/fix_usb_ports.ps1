# Traffic Deployer - USB / COM port repair for field laptops (GPS + PicoCount).
# Run via FIX_USB.bat (requests admin). Safe to copy alone to a USB stick.
param(
    [switch]$DiagnoseOnly
)

$ErrorActionPreference = "Continue"
$KitDir = $PSScriptRoot
$LogFile = Join-Path $KitDir ("usb_fix_log_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $line = "[{0:HH:mm:ss}] {1}" -f (Get-Date), $Message
    Write-Host $line -ForegroundColor $Color
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ComPortRows {
    $rows = @()
    try {
        foreach ($p in [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object) {
            $rows += [pscustomobject]@{ Port = $p; Source = "SerialPort API"; Detail = "" }
        }
    } catch {
        Write-Log "SerialPort list failed: $_" "Yellow"
    }
    try {
        Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '\(COM\d+\)' } |
            ForEach-Object {
                $name = $_.Name
                if (-not $name) { return }
                if ($name -match '\((COM\d+)\)') {
                    $portName = $Matches[1]
                    if ($rows.Port -notcontains $portName) {
                        $rows += [pscustomobject]@{
                            Port   = $portName
                            Source = "PnP"
                            Detail = $name
                        }
                    }
                }
            }
    } catch { }
    return $rows | Sort-Object Port -Unique
}

function Show-DeviceReport {
    Write-Log "=== COM ports (plug GPS or PicoCount USB now) ===" "Cyan"
    $com = Get-ComPortRows
    if (-not $com) {
        Write-Log "  (none) - if a device is plugged in, Windows did not create a COM port." "Yellow"
    } else {
        foreach ($c in $com) {
            $detail = ""
            if ($c.Detail) { $detail = " - $($c.Detail)" }
            Write-Log ("  {0}{1}" -f $c.Port, $detail) "Green"
        }
    }

    Write-Log "=== USB problems (present devices only) ===" "Cyan"
    $bad = @()
    try {
        $bad = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Status -eq 'Error' -or
                $_.FriendlyName -like '*Unknown USB*' -or
                $_.FriendlyName -like '*not recognized*' -or
                ($_.Class -eq 'Ports' -and $_.Status -eq 'Error')
            }
    } catch {
        Write-Log "  PnP scan skipped: $_" "Yellow"
    }
    if (-not $bad) {
        Write-Log "  (none flagged)" "Green"
    } else {
        foreach ($d in $bad) {
            Write-Log ("  {0} | {1} | status={2} problem={3}" -f $d.Class, $d.FriendlyName, $d.Status, $d.Problem) "Yellow"
        }
    }
    return $bad
}

function Set-UsbPowerFixes {
    $applied = @()

    $usbSvc = "HKLM:\SYSTEM\CurrentControlSet\Services\USB"
    try {
        if (-not (Test-Path $usbSvc)) { New-Item -Path $usbSvc -Force | Out-Null }
        New-ItemProperty -Path $usbSvc -Name "DisableSelectiveSuspend" -Value 1 -PropertyType DWord -Force | Out-Null
        $applied += "USB DisableSelectiveSuspend=1"
    } catch {
        Write-Log "Registry USB service: $_" "Red"
    }

    $subUsb = "2a737441-1930-4402-8d77-b2bebba308a3"
    $setSuspend = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
    foreach ($switch in @("/SETACVALUEINDEX", "/SETDCVALUEINDEX")) {
        $r = & powercfg $switch SCHEME_CURRENT $subUsb $setSuspend 0 2>&1
        if ($LASTEXITCODE -eq 0) { $applied += "powercfg $switch USB suspend=0" }
        else { Write-Log "powercfg $switch : $r" "Yellow" }
    }
    & powercfg /SETACTIVE SCHEME_CURRENT | Out-Null

    & powercfg /change standby-timeout-ac 0 | Out-Null
    & powercfg /change hibernate-timeout-ac 0 | Out-Null
    $applied += "powercfg AC sleep=never"

    return $applied
}

function Clear-GhostUsbDevices {
    param([switch]$Force)
    $ghosts = @()
    try {
        $ghosts = Get-PnpDevice -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FriendlyName -like '*Unknown USB*' -or
                $_.FriendlyName -like '*Device Descriptor Request Failed*' -or
                $_.FriendlyName -like '*Set Address Failed*'
            } |
            Where-Object { $_.Status -eq 'Error' -or $_.Status -eq 'Unknown' }
    } catch { return 0 }

    if (-not $ghosts) {
        Write-Log "No ghost Unknown USB devices to remove." "Green"
        return 0
    }

    Write-Log ("Found {0} ghost USB device(s):" -f $ghosts.Count) "Yellow"
    foreach ($g in $ghosts) {
        Write-Log ("  - {0}" -f $g.FriendlyName) "Yellow"
    }

    if (-not $Force) {
        $ans = Read-Host "Remove these ghost USB entries? (y/N)"
        if ($ans -notmatch '^[Yy]') {
            Write-Log "Skipped ghost removal." "Gray"
            return 0
        }
    }

    $n = 0
    foreach ($g in $ghosts) {
        try {
            & pnputil /remove-device $g.InstanceId 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { $n++; continue }
        } catch { }
        try {
            Remove-PnpDevice -InstanceId $g.InstanceId -Confirm:$false -ErrorAction Stop
            $n++
        } catch {
            Write-Log "  Could not remove $($g.FriendlyName): $_" "Red"
        }
    }
    Write-Log "Removed $n ghost USB device(s)." "Green"
    return $n
}

Clear-Host
Write-Log "Traffic Deployer USB fix kit" "Cyan"
Write-Log "Log: $LogFile" "Gray"
Write-Log "Computer: $env:COMPUTERNAME" "Gray"

$null = Show-DeviceReport

if ($DiagnoseOnly) {
    Write-Log ""
    Write-Log "Diagnose-only - no changes made." "Cyan"
    Write-Log "Run FIX_USB.bat (full fix) as Administrator to apply repairs." "Cyan"
    Read-Host "Press Enter to close"
    exit 0
}

if (-not (Test-IsAdmin)) {
    Write-Log "Administrator required for USB power fixes." "Yellow"
    $elevate = Join-Path $KitDir "FIX_USB.bat"
    if (Test-Path $elevate) {
        Start-Process -FilePath $elevate -Verb RunAs
    } else {
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`""
        ) -Verb RunAs
    }
    exit 0
}

Write-Log ""
Write-Log "=== Applying USB power fixes (admin) ===" "Cyan"
foreach ($item in Set-UsbPowerFixes) {
    Write-Log "  OK  $item" "Green"
}

Write-Log ""
Clear-GhostUsbDevices | Out-Null

Write-Log ""
Write-Log "=== After reboot ===" "Cyan"
Write-Log "  1. Restart the laptop." "White"
Write-Log "  2. Plug GPS into the LEFT port (the one that failed)." "White"
Write-Log "  3. Run FIX_USB.bat again - COM ports should list the device." "White"
Write-Log "  4. If left port still shows (none), use RIGHT port - likely hardware." "White"
Write-Log "  5. Traffic Deployer: Install tab -> Refresh after USB is stable." "White"

$reboot = Read-Host "`nReboot now? (y/N)"
if ($reboot -match '^[Yy]') {
    Write-Log "Rebooting..." "Cyan"
    Restart-Computer -Force
} else {
    Write-Log "Reboot when convenient, then retest the left USB port." "Yellow"
    Read-Host "Press Enter to close"
}
