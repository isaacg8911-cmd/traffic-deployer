@echo off
REM Run on HOME PC after BUILD_WORK_LAPTOP.bat — must pass before USB copy.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run START.bat once on this PC first.
    pause
    exit /b 1
)
echo.
echo Pre-ship gate (mandatory before USB copy)...
".venv\Scripts\python.exe" scripts\pre_ship_gate.py
set RC=%ERRORLEVEL%
echo.
if %RC% NEQ 0 (
    echo FIX the issues above, then run BUILD_WORK_LAPTOP.bat again.
) else (
    echo Copy dist\TrafficDeployer-WorkLaptop.zip to USB ^(or work laptop^).
    echo On work laptop: unzip, open TrafficDeployer folder, double-click OPEN_APP.bat
)
pause
exit /b %RC%
