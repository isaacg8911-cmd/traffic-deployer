@echo off
REM USB / COM repair for work laptop (GPS + PicoCount). Copy this folder to USB or run inside TrafficDeployer.
cd /d "%~dp0"

echo.
echo Traffic Deployer - USB fix kit
echo ==============================
echo Fixes common "USB not recognized" / missing COM port issues.
echo Needs Administrator once. Writes a log beside this bat file.
echo.
echo TIP: Plug GPS or PicoCount USB BEFORE running (any port).
echo.

set "PS1=%~dp0fix_usb_ports.ps1"
if not exist "%PS1%" (
    echo ERROR: fix_usb_ports.ps1 missing beside this bat file.
    pause
    exit /b 1
)

REM Diagnose without admin:  FIX_USB.bat diag
if /I "%~1"=="diag" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -DiagnoseOnly
    exit /b %ERRORLEVEL%
)

REM Full fix — script re-launches elevated if needed
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
exit /b %ERRORLEVEL%
