@echo off
REM Work laptop entry — run this from the INSTALL folder (not Downloads).
REM AppUpdate replaces exe + _internal + web; this bat is refreshed each update.
cd /d "%~dp0"

set "TDS_WORK_LAPTOP=1"

set "TD_VER="
if exist "READ_ME_FIRST.txt" (
    for /f "tokens=2" %%v in ('findstr /I /C:"Version " READ_ME_FIRST.txt 2^>nul') do (
        if not defined TD_VER set "TD_VER=%%v"
    )
)
if exist "VERSION.txt" set /p TD_VER=<VERSION.txt

echo.
echo Traffic Deployer — work laptop
echo ==============================
if defined TD_VER (
    echo Bundle label: v%TD_VER%
) else (
    echo Bundle label: ^(see window title after launch^)
)
echo Install folder: %CD%
echo.

if not exist "TrafficDeployer.exe" (
    echo ERROR: TrafficDeployer.exe not found in this folder.
    echo Run OPEN_APP.bat from your install ^(e.g. C:\TrafficDeployer\^),
    echo not from Downloads or the unzip staging folder.
    pause
    exit /b 1
)

if not exist "_internal\" (
    echo ERROR: _internal folder missing.
    echo Re-run APPLY_UPDATE into this install, or re-extract the AppUpdate zip.
    pause
    exit /b 1
)

if not exist "_internal\web\index.html" (
    if not exist "web\index.html" (
        echo ERROR: Map UI missing ^(_internal\web / web^).
        echo Apply a fresh AppUpdate into this install folder.
        pause
        exit /b 1
    )
)

if not exist "tds_data\" mkdir "tds_data"
if not exist "tds_data\counter_downloads\" mkdir "tds_data\counter_downloads"

REM Stalled Wi-Fi download — finish file swap before launching old exe.
if exist "tds_data\update_ready\TrafficDeployer.exe" (
    echo.
    echo Stalled update found in tds_data\update_ready
    echo Finishing install before launch...
    echo.
    if exist "%~dp0FINISH_UPDATE.bat" (
        call "%~dp0FINISH_UPDATE.bat" auto
        if errorlevel 1 (
            echo FINISH_UPDATE failed. Close the app in Task Manager and retry.
            pause
            exit /b 1
        )
        REM Refresh label after apply
        set "TD_VER="
        if exist "VERSION.txt" set /p TD_VER=<VERSION.txt
        if defined TD_VER echo Bundle label now: v%TD_VER%
    ) else (
        echo FINISH_UPDATE.bat missing — copy it from USB / C:\TDReleases then re-run OPEN_APP.bat
        pause
        exit /b 1
    )
)

set "MAP=tds_data\california.pmtiles"
if not exist "%MAP%" (
    echo ERROR: Offline map missing ^(tds_data\california.pmtiles^).
    echo First install needs TrafficDeployer-WorkLaptop.zip from home PC.
    echo App-only updates do not include the map — keep tds_data\.
    pause
    exit /b 1
)

if not exist ".unblock_done" (
    echo First launch — unblocking app files...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Unblock-File -LiteralPath '%CD%\TrafficDeployer.exe','%CD%\OPEN_APP.bat' -ErrorAction SilentlyContinue" 2>nul
    echo done> ".unblock_done"
)

echo Map OK. Starting app...
echo Window title must match the new version ^(proof of update^).
echo First map load may take a few minutes — wait, do not close.
echo.
start "" "%~dp0TrafficDeployer.exe"
exit /b 0
