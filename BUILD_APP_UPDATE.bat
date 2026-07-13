@echo off
REM App-only update for work laptop — folder + zip (~300 MB). Map stays on laptop.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo FAIL: Run START.bat once on this PC first (.venv missing).
    pause
    exit /b 1
)

echo.
echo === PRE-BUILD ENGINEER GATE (smoke_full) ===
".venv\Scripts\python.exe" scripts\smoke_full.py
set PRE=%ERRORLEVEL%
if %PRE% neq 0 (
    echo.
    echo PRE-BUILD GATE FAILED — fix source before PyInstaller build.
    pause
    exit /b %PRE%
)

echo.
echo PRE-BUILD GATE PASS — bumping version, then APP UPDATE (no california.pmtiles).
echo Each complete build gets a new APP_VERSION so the laptop title proves progression.
echo Use BUILD_WORK_LAPTOP.bat only for first install or missing map.
echo.
powershell -ExecutionPolicy Bypass -File scripts\build_app_update.ps1
set RC=%ERRORLEVEL%
if %RC%==0 (
    echo.
    echo === POST-BUILD USER VERIFY (shipment + frozen bundle) ===
    ".venv\Scripts\python.exe" scripts\test_shipment.py
    set RC=%ERRORLEVEL%
)
if %RC%==0 (
    echo.
    echo DONE. Copy dist\TrafficDeployer-AppUpdate.zip to USB (or the TrafficDeployer folder).
    echo On work laptop: unzip over existing install — keep tds_data\
    echo Optional: run VERIFY_WORK_LAPTOP.bat or user_stress_handoff.py for deeper UI stress.
) else (
    echo.
    echo BUILD OR VERIFY FAILED - read messages above.
)
pause
exit /b %RC%
