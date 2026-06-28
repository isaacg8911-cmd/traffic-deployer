@echo off
REM Check for Traffic Deployer updates (home Wi-Fi only). Does not change field data.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run START.bat once to create the environment.
    exit /b 1
)
echo.
echo Checking for updates...
".venv\Scripts\python.exe" scripts\check_updates.py
set RC=%ERRORLEVEL%
if %RC%==2 (
    echo.
    echo On HOME PC: run BUILD_APP_UPDATE.bat ^(~800 MB folder, no map^).
    echo Copy dist\TrafficDeployer-AppUpdate\TrafficDeployer to this laptop.
    echo Replace exe + _internal + web — keep tds_data\
    echo.
    echo First install or missing map? Use BUILD_WORK_LAPTOP.bat ^(full zip^) instead.
)
exit /b %RC%
