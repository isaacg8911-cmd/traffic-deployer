@echo off
REM Publish dist\TrafficDeployer-AppUpdate.zip to C:\TDReleases for Wi-Fi auto-update.
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File scripts\publish_app_update.ps1
set RC=%ERRORLEVEL%
if %RC%==0 (
    echo.
    echo Next: run C:\TDReleases\SERVE_RELEASES.bat
    echo Then copy C:\TDReleases\update_channel.json to work laptop tds_data\
)
pause
exit /b %RC%
