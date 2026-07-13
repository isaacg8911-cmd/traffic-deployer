@echo off
REM Prove the AppUpdate handoff folder/zip — what the work laptop receives.
REM Run after BUILD_APP_UPDATE.bat (or BUILD_WORK_LAPTOP when that packs the full zip).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo FAIL: Run START.bat once to create .venv
    pause
    exit /b 1
)
echo.
echo VERIFY WORK LAPTOP — shipment package (not dev source smoke)
echo.
".venv\Scripts\python.exe" scripts\test_shipment.py
set RC=%ERRORLEVEL%
if %RC%==0 (
    echo.
    echo VERIFY PASS — safe to copy dist\TrafficDeployer-AppUpdate-VERSION.zip to laptop
    echo ^(e.g. TrafficDeployer-AppUpdate-1.0.12.zip^)
) else (
    echo.
    echo VERIFY FAIL — fix build, re-run BUILD_APP_UPDATE.bat, then this again
)
pause
exit /b %RC%
