@echo off
REM Launch Traffic Deployer preloaded with the Week 12 sample data.
REM Double-click this file (do not run it from the AI terminal) so the
REM window opens on YOUR desktop.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -c "import PySide6" 2>nul || pip install -r requirements.txt

python _run_test.py
echo.
echo (Window closed. Press any key to exit.)
pause >nul
