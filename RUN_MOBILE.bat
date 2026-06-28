@echo off
REM ============================================================
REM  Traffic Deployer - MOBILE web server (phone field runner)
REM  Serves the lean PWA. Open the printed URL on your phone.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No environment yet. Run START.bat once first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

REM Ensure mobile deps are present (FastAPI stack).
python -c "import fastapi, uvicorn, multipart" 1>nul 2>nul
if errorlevel 1 (
    echo Installing mobile web dependencies...
    pip install -r mobile_web\requirements.txt
)

echo.
echo Starting mobile web server...
python scripts\run_mobile.py
if errorlevel 1 (
    echo.
    echo Mobile server exited with an error.
    pause
)
