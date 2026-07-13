@echo off
REM Start home Wi-Fi update server (run after BUILD_WIFI_UPDATE / PUBLISH).
set "REL=%TD_RELEASES_DIR%"
if "%REL%"=="" set "REL=C:\TDReleases"
if not exist "%REL%\SERVE_RELEASES.bat" (
    echo Run PUBLISH_APP_UPDATE.bat first.
    pause
    exit /b 1
)
start "TD Wi-Fi Updates" "%REL%\SERVE_RELEASES.bat"
