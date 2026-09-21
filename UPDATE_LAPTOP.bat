@echo off
REM Home PC: serve the published AppUpdate on Tailscale and push the work laptop.
cd /d "%~dp0"
if not exist "C:\TDReleases\version.json" (
    echo No published zip yet. Building + publishing first...
    call BUILD_WIFI_UPDATE.bat
    if errorlevel 1 exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\push_update_tailscale.ps1
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
