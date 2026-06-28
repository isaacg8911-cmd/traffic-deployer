@echo off
REM Full app check: headless PROVE chain + user-input proofs + audit report
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv — run START.bat first
    exit /b 1
)
".venv\Scripts\python.exe" scripts\app_check.py --tier full
exit /b %ERRORLEVEL%
