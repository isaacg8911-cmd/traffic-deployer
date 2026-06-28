@echo off
REM User-input proofs: real Qt app + map simulations (run after UI/map/install changes)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv — run START.bat first
    exit /b 1
)
".venv\Scripts\python.exe" scripts\app_check.py --tier user
exit /b %ERRORLEVEL%
