@echo off
REM Serve C:\TDReleases on LAN + Tailscale (home PC).
REM Binds each non-loopback IPv4 (not 0.0.0.0) so MindLink OS on 127.0.0.1:8765 can coexist.
setlocal
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
echo   Port  : %PORT%
echo.
echo Leave this window open while the work laptop updates.
echo Laptop on Tailscale uses the 100.x / MagicDNS URL (home Wi-Fi not required).
echo Press Ctrl+C to stop.
echo.

set "SCRIPT="
set "PY="
if exist "%~dp0..\scripts\serve_td_releases.py" (
    set "SCRIPT=%~dp0..\scripts\serve_td_releases.py"
    if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"
)
if not defined SCRIPT if exist "%REL%\serve_td_releases.py" set "SCRIPT=%REL%\serve_td_releases.py"
if not defined PY if exist "C:\MindLink AI\projects\traffic-deployer\.venv\Scripts\python.exe" (
    set "PY=C:\MindLink AI\projects\traffic-deployer\.venv\Scripts\python.exe"
)
if not defined SCRIPT if exist "C:\MindLink AI\projects\traffic-deployer\scripts\serve_td_releases.py" (
    set "SCRIPT=C:\MindLink AI\projects\traffic-deployer\scripts\serve_td_releases.py"
)
if not defined PY set "PY=python"
if not defined SCRIPT (
    echo FAIL: serve_td_releases.py missing. Re-run PUBLISH_APP_UPDATE.bat.
    pause
    exit /b 1
)

"%PY%" "%SCRIPT%"
echo.
pause
