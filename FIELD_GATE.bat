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
echo === [2/6] field_sim (desk job cycle, no GPS) ===
".venv\Scripts\python.exe" scripts\test_field_sim.py
if errorlevel 1 set FAIL=1

echo.
echo === [3/6] BUILD ROUTE thread (QThread.start shadow guard) ===
".venv\Scripts\python.exe" scripts\prove_build_route_thread.py
if errorlevel 1 set FAIL=1

if %FAIL% neq 0 (
    echo.
    echo FIELD GATE STOPPED — fix source before AppUpdate build.
    exit /b 1
)

echo.
echo === [4/6] BUILD AppUpdate (PyInstaller + pack) ===
powershell -ExecutionPolicy Bypass -File scripts\build_app_update.ps1
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)

echo.
echo === [5/6] shipment verify (what the zip contains) ===
".venv\Scripts\python.exe" scripts\test_shipment.py
if errorlevel 1 set FAIL=1

echo.
echo === [6/6] handoff stress (map WARN OK if bridge dead on build PC) ===
set TDS_WORK_LAPTOP=1
".venv\Scripts\python.exe" scripts\user_stress_handoff.py
if errorlevel 1 (
    echo   WARN stress reported FAIL — check BUILD ROUTE; map-only WARN is OK on build PC.
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
