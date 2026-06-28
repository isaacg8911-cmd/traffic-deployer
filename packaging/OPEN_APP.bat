@echo off
REM Work laptop entry point — double-click THIS after unzipping (not START.bat).
cd /d "%~dp0"

REM Low-RAM field laptop tuning (Intel N200 / 4 GB class). Auto-detect also works.
set "TDS_WORK_LAPTOP=1"

echo.
echo Traffic Deployer - work laptop
echo ==============================
for /f "tokens=2" %%v in ('findstr /C:"Version" READ_ME_FIRST.txt 2^>nul') do set "TD_VER=%%v"
if defined TD_VER echo Version %TD_VER%
echo.

if not exist "TrafficDeployer.exe" (
    echo ERROR: TrafficDeployer.exe not found.
    echo Unzip the full TrafficDeployer folder, then run OPEN_APP.bat from inside it.
    pause
    exit /b 1
)

if not exist "_internal\" (
    echo ERROR: _internal folder missing — re-extract the zip completely.
    pause
    exit /b 1
)

if not exist "_internal\web\index.html" (
    if not exist "web\index.html" (
        echo ERROR: Map UI missing ^(_internal\web and web\^).
        echo Re-extract TrafficDeployer-WorkLaptop.zip from home PC.
        pause
        exit /b 1
    )
)

if not exist "tds_data\" mkdir "tds_data"
if not exist "tds_data\counter_downloads\" mkdir "tds_data\counter_downloads"

set "MAP=tds_data\california.pmtiles"
if not exist "%MAP%" (
    echo ERROR: Offline map missing ^(tds_data\california.pmtiles^).
    echo Copy a fresh TrafficDeployer-WorkLaptop.zip from home PC and extract again.
    pause
    exit /b 1
)

REM Unblock exe once (full-folder recurse can hang 10+ min on 4 GB laptops).
if not exist ".unblock_done" (
    echo First launch — unblocking app files...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Unblock-File -LiteralPath '%CD%\TrafficDeployer.exe','%CD%\OPEN_APP.bat' -ErrorAction SilentlyContinue" 2>nul
    echo done> ".unblock_done"
)

echo Map file found. Starting app...
echo First map load on this laptop may take 3-5 minutes — wait, do not close.
echo.
start "" "%~dp0TrafficDeployer.exe"
exit /b 0
