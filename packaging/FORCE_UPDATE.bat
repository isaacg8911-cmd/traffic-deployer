@echo off
REM ONE-CLICK force upgrade from the AppUpdate zip beside this bat.
REM Prefers versioned zip: TrafficDeployer-AppUpdate-1.0.12.zip
REM Also accepts legacy TrafficDeployer-AppUpdate.zip

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo Traffic Deployer — FORCE UPDATE
echo ===============================
echo Folder now: %CD%
echo.

set "ZIP="
REM Newest versioned zip by filename sort (1.0.12 > 1.0.10)
for /f "delims=" %%F in ('dir /b /o-n "TrafficDeployer-AppUpdate-*.zip" 2^>nul') do (
    if not defined ZIP set "ZIP=%%F"
)
if not defined ZIP if exist "TrafficDeployer-AppUpdate.zip" set "ZIP=TrafficDeployer-AppUpdate.zip"

if not defined ZIP (
    echo FAIL: no AppUpdate zip next to this bat.
    echo Copy from C:\TDReleases\ on the home PC:
    echo   TrafficDeployer-AppUpdate-VERSION.zip
    echo   FORCE_UPDATE.bat
    echo Example: TrafficDeployer-AppUpdate-1.0.12.zip
    pause
    exit /b 1
)

echo Using zip: %ZIP%
echo.

echo Closing TrafficDeployer.exe if running...
taskkill /F /IM TrafficDeployer.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM --- Find real install: must have exe + offline map ---
set "INSTALL="
if exist "C:\TrafficDeployer\TrafficDeployer.exe" if exist "C:\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=C:\TrafficDeployer"
if not defined INSTALL if exist "D:\TrafficDeployer\TrafficDeployer.exe" if exist "D:\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=D:\TrafficDeployer"
if not defined INSTALL if exist "%USERPROFILE%\TrafficDeployer\TrafficDeployer.exe" if exist "%USERPROFILE%\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=%USERPROFILE%\TrafficDeployer"
if not defined INSTALL if exist "%USERPROFILE%\Desktop\TrafficDeployer\TrafficDeployer.exe" if exist "%USERPROFILE%\Desktop\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=%USERPROFILE%\Desktop\TrafficDeployer"

if not defined INSTALL (
    echo Could not auto-find install. Searching this PC for california.pmtiles...
    for /f "delims=" %%P in ('dir /s /b "C:\TrafficDeployer\tds_data\california.pmtiles" 2^>nul') do (
        if not defined INSTALL (
            set "CAND=%%~dpP"
            for %%I in ("!CAND!\..") do set "INSTALL=%%~fI"
        )
    )
)

if not defined INSTALL (
    echo.
    echo Type your INSTALL folder ^(the one with the map, NOT Downloads^).
    echo Example: C:\TrafficDeployer
    set /p "INSTALL=Install folder: "
)

set "INSTALL=%INSTALL:"=%"
if "%INSTALL:~-1%"=="\" set "INSTALL=%INSTALL:~0,-1%"

if not exist "%INSTALL%\TrafficDeployer.exe" (
    echo FAIL: no TrafficDeployer.exe in:
    echo   %INSTALL%
    pause
    exit /b 1
)
if not exist "%INSTALL%\tds_data\california.pmtiles" (
    echo FAIL: no offline map in that folder - wrong place ^(Downloads/unzip?^).
    echo   %INSTALL%
    echo Real install has tds_data\california.pmtiles
    pause
    exit /b 1
)

echo.
echo REAL INSTALL: %INSTALL%
echo SOURCE ZIP  : %~dp0%ZIP%
echo tds_data\ will NOT be deleted.
echo.
pause

set "UNPACK=%~dp0_force_unpack"
if exist "%UNPACK%" rmdir /s /q "%UNPACK%"
mkdir "%UNPACK%" || goto :fail
echo Unzipping ~300 MB — wait...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%~dp0%ZIP%' -DestinationPath '%UNPACK%' -Force"
if errorlevel 1 goto :fail

set "SRC=%UNPACK%\TrafficDeployer"
if not exist "%SRC%\TrafficDeployer.exe" (
    if exist "%UNPACK%\TrafficDeployer\TrafficDeployer\TrafficDeployer.exe" set "SRC=%UNPACK%\TrafficDeployer\TrafficDeployer"
)
if not exist "%SRC%\TrafficDeployer.exe" (
    echo FAIL: zip did not contain TrafficDeployer.exe
    dir /s /b "%UNPACK%\TrafficDeployer.exe" 2>nul
    pause
    exit /b 1
)

echo Copying into install...
copy /y "%SRC%\TrafficDeployer.exe" "%INSTALL%\TrafficDeployer.exe" >nul || goto :fail
if exist "%INSTALL%\_internal\" rmdir /s /q "%INSTALL%\_internal"
xcopy /e /i /y "%SRC%\_internal" "%INSTALL%\_internal\" >nul || goto :fail
if exist "%INSTALL%\web\" rmdir /s /q "%INSTALL%\web"
if exist "%SRC%\web\" xcopy /e /i /y "%SRC%\web" "%INSTALL%\web\" >nul
copy /y "%SRC%\OPEN_APP.bat" "%INSTALL%\OPEN_APP.bat" >nul 2>&1
copy /y "%SRC%\VERSION.txt" "%INSTALL%\VERSION.txt" >nul 2>&1
copy /y "%SRC%\READ_ME_FIRST.txt" "%INSTALL%\READ_ME_FIRST.txt" >nul 2>&1
copy /y "%~dp0FORCE_UPDATE.bat" "%INSTALL%\FORCE_UPDATE.bat" >nul 2>&1

if exist "%INSTALL%\tds_data\.update_state.json" del /f /q "%INSTALL%\tds_data\.update_state.json" >nul 2>&1

echo.
echo ========== PROOF ==========
echo Install: %INSTALL%
echo Source : %ZIP%
if exist "%INSTALL%\VERSION.txt" (
    set /p VER=<"%INSTALL%\VERSION.txt"
    echo VERSION.txt: !VER!
) else (
    echo VERSION.txt: missing
)
echo Window title MUST match VERSION.txt
echo ===========================
echo.

start "" "%INSTALL%\OPEN_APP.bat"
pause
exit /b 0

:fail
echo FAIL — copy/unzip error. App still closed? Disk full?
pause
exit /b 1
