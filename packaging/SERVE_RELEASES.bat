@echo off
REM Serve C:\TDReleases for work-laptop Wi-Fi auto-update (home PC only).
set "REL=%TD_RELEASES_DIR%"
if "%REL%"=="" set "REL=C:\TDReleases"
set "PORT=%TD_RELEASES_PORT%"
if "%PORT%"=="" set "PORT=8765"

if not exist "%REL%\version.json" (
    echo FAIL: %REL%\version.json missing.
    echo Run PUBLISH_APP_UPDATE.bat on this PC first.
    pause
    exit /b 1
)

cd /d "%REL%"
echo.
echo Traffic Deployer update server
echo   Folder: %REL%
echo   URL   : http://YOUR_HOME_PC_IP:%PORT%/version.json
echo.
echo Leave this window open while the work laptop updates.
echo Press Ctrl+C to stop.
echo.
python -m http.server %PORT%
pause
