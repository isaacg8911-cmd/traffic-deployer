@echo off
REM ============================================================
REM  Phase A — work-laptop ship gate (home PC)
REM  Proves the FROZEN package the truck receives — not .venv source.
REM
REM  GPS / PicoCount USB still require the physical N200 laptop.
REM ============================================================
cd /d "%~dp0"
set FAIL=0

if not exist ".venv\Scripts\python.exe" (
    echo FAIL: Run START.bat once first (.venv missing).
    exit /b 1
)

echo.
echo === [1/5] smoke_full (source gate before freeze) ===
".venv\Scripts\python.exe" scripts\smoke_full.py
if errorlevel 1 set FAIL=1

echo.
echo === [2/5] field_sim (desk job cycle, no GPS) ===
".venv\Scripts\python.exe" scripts\test_field_sim.py
if errorlevel 1 set FAIL=1

if %FAIL% neq 0 (
    echo.
    echo FIELD GATE STOPPED — fix source before AppUpdate build.
    exit /b 1
)

echo.
echo === [3/5] BUILD AppUpdate (PyInstaller + pack) ===
powershell -ExecutionPolicy Bypass -File scripts\build_app_update.ps1
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)

echo.
echo === [4/5] shipment verify (what the zip contains) ===
".venv\Scripts\python.exe" scripts\test_shipment.py
if errorlevel 1 set FAIL=1

echo.
echo === [5/5] handoff stress (bonus — offscreen map may WARN/FAIL on build PC) ===
set TDS_WORK_LAPTOP=1
".venv\Scripts\python.exe" scripts\user_stress_handoff.py
if errorlevel 1 (
    echo   WARN stress failed — known on build-PC WebEngine; shipment PASS is the ship gate.
)

echo.
if %FAIL%==0 (
    echo ============================================================
    echo   FIELD GATE PASS — safe to copy AppUpdate to work laptop
    echo   Zip: dist\TrafficDeployer-AppUpdate.zip
    echo   Keep tds_data\ on laptop. Launch with OPEN_APP.bat
    echo   Still prove on truck: map feel, GPS, PicoCount
    echo ============================================================
) else (
    echo ============================================================
    echo   FIELD GATE FAIL — do NOT copy to laptop
    echo ============================================================
)
exit /b %FAIL%
