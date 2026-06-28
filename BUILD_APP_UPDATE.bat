@echo off
REM App-only update for work laptop — folder copy, no zip (~800 MB). Map stays on laptop.
cd /d "%~dp0"
echo.
echo Building APP UPDATE folder (no california.pmtiles — map stays on the work laptop).
echo Use BUILD_WORK_LAPTOP.bat only for first install or missing map.
echo.
powershell -ExecutionPolicy Bypass -File scripts\build_app_update.ps1
set RC=%ERRORLEVEL%
if %RC%==0 (
    echo.
    echo DONE. Copy dist\TrafficDeployer-AppUpdate.zip to USB.
    echo On work laptop: unzip TrafficDeployer folder over existing install — keep tds_data\
) else (
    echo.
    echo BUILD FAILED - read messages above.
)
pause
exit /b %RC%
