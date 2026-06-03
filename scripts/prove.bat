@echo off
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    call ".venv\Scripts\activate.bat"
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

set FAIL=0
set STEP=0

echo.
echo === [1/5] smoke_full ===
".venv\Scripts\python.exe" scripts\smoke_full.py
if errorlevel 1 set FAIL=1

echo.
echo === [2/5] demo_workflow ===
".venv\Scripts\python.exe" scripts\demo_workflow.py
if errorlevel 1 set FAIL=1

echo.
echo === [3/5] quick_preflight ===
".venv\Scripts\python.exe" scripts\quick_preflight.py
if errorlevel 1 set FAIL=1

echo.
echo === [4/5] golden_routes ===
".venv\Scripts\python.exe" scripts\golden_routes.py
if errorlevel 1 set FAIL=1

echo.
echo === [5/6] benchmark_route ===
".venv\Scripts\python.exe" scripts\benchmark_route.py
if errorlevel 1 set FAIL=1

echo.
echo === [6/6] picocount_sandbox (optional hardware) ===
".venv\Scripts\python.exe" scripts\picocount_sandbox.py
if errorlevel 1 (
    echo   WARN picocount_sandbox failed or no COM port — OK if counter unplugged
)

echo.
if %FAIL%==0 (
    echo ========================================
    echo   PROVE PASS — smoke + demo + golden + benchmark
    echo ========================================
) else (
    echo ========================================
    echo   PROVE FAILED — see errors above
    echo ========================================
)
exit /b %FAIL%
