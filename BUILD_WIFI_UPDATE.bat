@echo off
REM Build app update + publish to C:\TDReleases for home Wi-Fi auto-update.
cd /d "%~dp0"

call BUILD_APP_UPDATE.bat
set RC=%ERRORLEVEL%
if %RC% neq 0 exit /b %RC%

echo.
echo === PUBLISH to C:\TDReleases ===
powershell -ExecutionPolicy Bypass -File scripts\publish_app_update.ps1
set RC=%ERRORLEVEL%
if %RC%==0 (
    echo.
    echo === WIFI UPDATE READY ===
echo 1. Run UPDATE_LAPTOP.bat on this PC (serves Tailscale + LAN)
echo 2. On the work laptop (Tailscale connected): OPEN_APP.bat or WIFI_UPDATE_NOW.bat
)
pause
exit /b %RC%
