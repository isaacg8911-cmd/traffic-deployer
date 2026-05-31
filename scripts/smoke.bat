@echo off
REM ============================================================
REM  Traffic Deployer — full smoke test (no GUI)
REM  Double-click or: scripts\smoke.bat
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    call ".venv\Scripts\activate.bat"
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

python scripts\smoke_full.py
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE%==0 (
    echo ========================================
    echo   SMOKE PASS — ready for field / demo
    echo ========================================
) else (
    echo ========================================
    echo   SMOKE FAILED — fix errors above
    echo ========================================
)
pause
exit /b %EXITCODE%
