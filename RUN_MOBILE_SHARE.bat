@echo off
REM ============================================================
REM  Traffic Deployer - MOBILE PUBLIC SHARE mode
REM  Serves the phone PWA over a Cloudflare tunnel so a share
REM  link works on ANY phone (cellular OK) - not just same Wi-Fi.
REM  Crew can only open jobs from a share link (share-only mode).
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No environment yet. Run START.bat once first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

REM Ensure mobile deps are present (FastAPI stack + QR + TLS).
python -c "import fastapi, uvicorn, multipart, segno, httpx" 1>nul 2>nul
if errorlevel 1 (
    echo Installing mobile web dependencies...
    pip install -r mobile_web\requirements.txt
)

echo.
echo Starting PUBLIC share server (Cloudflare tunnel)...
echo Need cloudflared installed: winget install --id Cloudflare.cloudflared
echo.
python scripts\run_mobile_share.py --demo %*
if errorlevel 1 (
    echo.
    echo Public share mode exited with an error.
    pause
)
