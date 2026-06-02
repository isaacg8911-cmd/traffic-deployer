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
echo.
echo === [1/3] smoke_full ===
".venv\Scripts\python.exe" scripts\smoke_full.py
if errorlevel 1 set FAIL=1

echo.
echo === [2/3] demo_workflow ===
".venv\Scripts\python.exe" scripts\demo_workflow.py
if errorlevel 1 set FAIL=1

echo.
echo === [3/3] quick_preflight ===
".venv\Scripts\python.exe" scripts\quick_preflight.py
if errorlevel 1 set FAIL=1

echo.
if %FAIL%==0 (
    echo ========================================
    echo   PROVE PASS — ready for field / demo
    echo ========================================
) else (
    echo ========================================
    echo   PROVE FAILED — see errors above
    echo ========================================
)
exit /b %FAIL%
