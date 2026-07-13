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
    echo 1. Run C:\TDReleases\SERVE_RELEASES.bat on this PC
    echo 2. Copy C:\TDReleases\update_channel.json to work laptop:
    echo       C:\TrafficDeployer\tds_data\update_channel.json
    echo 3. On laptop (home Wi-Fi, online mode): open Traffic Deployer
)
pause
exit /b %RC%
