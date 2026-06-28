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
python -c "import PySide6, PySide6.QtWebEngineWidgets, pandas, xlrd, openpyxl, xlsxwriter, serial, pynmea2, cryptography, osmnx, networkx" 1>nul 2>nul
if errorlevel 1 (
    echo Installing / repairing dependencies...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
)

REM One-time map download (California basemap + map libraries) if missing or incomplete.
set "PMTILES=tds_data\california.pmtiles"
set "NEED_MAP=1"
if exist "%PMTILES%" (
    for %%A in ("%PMTILES%") do if %%~zA GTR 104857600 set "NEED_MAP=0"
)
if "%NEED_MAP%"=="1" (
    if exist "%PMTILES%" (
        echo.
        echo California map file looks incomplete - re-downloading ^(needs internet^)...
        del "%PMTILES%"
    ) else (
        echo.
        echo Downloading the California map for offline use - one time, needs internet...
    )
    python setup_maps.py
    if errorlevel 1 (
        echo.
        echo MAP DOWNLOAD FAILED. Work Wi-Fi often blocks map hosts.
        echo Run:  .venv\Scripts\python.exe scripts\diagnose_network.py
        echo Or copy the whole tds_data folder from your home PC, then run START.bat again.
        echo.
        pause
        exit /b 1
    )
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
echo Quick network check ^(road download on work Wi-Fi^)...
python scripts\diagnose_network.py
if errorlevel 1 (
    echo.
    echo Tip: copy tds_data from home if downloads are blocked here.
    echo.
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
if errorlevel 1 (
    echo.
    echo App exited with an error.
    pause
)
