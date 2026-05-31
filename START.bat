@echo off
REM ============================================================
REM  Traffic Deployer - one-click LOCAL desktop launcher
REM  Runs entirely on this laptop. Your field files never leave.
REM ============================================================
cd /d "%~dp0"

REM If a venv exists but cannot run (e.g. copied from another PC), rebuild it.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version 1>nul 2>nul
    if errorlevel 1 (
        echo Existing environment is invalid for this PC. Rebuilding...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo First-time setup - building local environment...
    echo This only happens once and needs internet.
    echo.
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

REM Verify dependencies are actually installed (handles partial installs).
python -c "import PySide6, PySide6.QtWebEngineWidgets, pandas, serial, pynmea2, cryptography, osmnx, networkx, pyttsx3" 1>nul 2>nul
if errorlevel 1 (
    echo Installing / repairing dependencies...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
)

REM One-time map download (California basemap + map libraries) if missing.
if not exist "tds_data\california.pmtiles" (
    echo.
    echo Downloading the California map for offline use - one time, needs internet...
    python setup_maps.py
)

REM Verify label fonts (street names offline).
if not exist "web\vendor\fonts\Noto Sans Regular\0-255.pbf" (
    if exist "tds_data\california.pmtiles" (
        echo.
        echo Label fonts missing — refreshing map assets ^(needs internet^)...
        python setup_maps.py
    )
)

echo.
echo Quick preflight...
python scripts\quick_preflight.py
if errorlevel 1 (
    echo.
    echo WARNING: Critical preflight failed. Fix in Setup - Field Readiness, then continue.
    echo.
)

echo.
echo Starting Traffic Deployer...
python main.py
pause
