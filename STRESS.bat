@echo off
REM Regression stress loop — run after every code change (logs/stress/)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run START.bat once to create .venv
    exit /b 1
)
".venv\Scripts\python.exe" scripts\stress_loop.py %*
exit /b %ERRORLEVEL%
