@echo off
REM Finish a stalled Wi-Fi update OR apply from an unzipped AppUpdate folder.
REM Run from / point at your INSTALL folder (has tds_data\ + TrafficDeployer.exe).
REM
REM Cases:
REM   A) Wi-Fi already downloaded: tds_data\update_ready\TrafficDeployer.exe exists
REM   B) USB unzip: pass install + update folders (same as APPLY_UPDATE.bat)

setlocal EnableExtensions
set "INSTALL=%~1"
set "SRC=%~2"
set "AUTO=%~1"

if /I "%AUTO%"=="auto" (
    set "INSTALL=%~dp0"
    if "%INSTALL:~-1%"=="\" set "INSTALL=%INSTALL:~0,-1%"
    set "SRC="
    goto :have_install
)

if "%INSTALL%"=="" (
    echo.
    echo Traffic Deployer — FINISH UPDATE
    echo ===============================
    echo Enter your INSTALL folder ^(e.g. C:\TrafficDeployer^).
    set /p "INSTALL=Install folder: "
)

if "%INSTALL%"=="" (
    echo FAIL: install folder required.
    pause
    exit /b 1
)

set "INSTALL=%INSTALL:"=%"
if "%INSTALL:~-1%"=="\" set "INSTALL=%INSTALL:~0,-1%"

:have_install
if not exist "%INSTALL%\TrafficDeployer.exe" (
    echo FAIL: no TrafficDeployer.exe in:
    echo   %INSTALL%
    pause
    exit /b 1
)

tasklist /FI "IMAGENAME eq TrafficDeployer.exe" 2>nul | find /I "TrafficDeployer.exe" >nul
if not errorlevel 1 (
    echo FAIL: TrafficDeployer.exe is still running. Close it in Task Manager, then retry.
    pause
    exit /b 1
)

REM Prefer stalled Wi-Fi stage
if exist "%INSTALL%\tds_data\update_ready\TrafficDeployer.exe" (
    set "SRC=%INSTALL%\tds_data\update_ready"
    echo Found stalled download: tds_data\update_ready
    goto :apply
)

if "%SRC%"=="" (
    if /I not "%AUTO%"=="auto" (
        echo.
        echo No tds_data\update_ready found. Enter unzipped UPDATE folder
        echo ^(e.g. C:\TDUpdate\TrafficDeployer^):
        set /p "SRC=Update folder: "
    )
)

if "%SRC%"=="" (
    echo FAIL: no update_ready and no update folder given.
    echo Unzip TrafficDeployer-AppUpdate.zip, then run:
    echo   APPLY_UPDATE.bat "%INSTALL%" "C:\TDUpdate\TrafficDeployer"
    pause
    exit /b 1
)

set "SRC=%SRC:"=%"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
if not exist "%SRC%\TrafficDeployer.exe" (
    if exist "%SRC%\TrafficDeployer\TrafficDeployer.exe" set "SRC=%SRC%\TrafficDeployer"
)
if not exist "%SRC%\TrafficDeployer.exe" (
    echo FAIL: no TrafficDeployer.exe in update folder:
    echo   %SRC%
    pause
    exit /b 1
)

:apply
echo.
echo INSTALL: %INSTALL%
echo SOURCE : %SRC%
echo Closing gap — copying into install. tds_data\ is kept.
echo.

cd /d "%INSTALL%" || (
    echo FAIL: cannot open install folder.
    pause
    exit /b 1
)

copy /y "%SRC%\TrafficDeployer.exe" "TrafficDeployer.exe" >nul || goto :fail
if exist "_internal\" rmdir /s /q "_internal"
xcopy /e /i /y "%SRC%\_internal" "_internal\" >nul || goto :fail
if exist "web\" rmdir /s /q "web"
if exist "%SRC%\web\" xcopy /e /i /y "%SRC%\web" "web\" >nul
if exist "%SRC%\OPEN_APP.bat" copy /y "%SRC%\OPEN_APP.bat" "OPEN_APP.bat" >nul
if exist "%SRC%\VERSION.txt" copy /y "%SRC%\VERSION.txt" "VERSION.txt" >nul
if exist "%SRC%\READ_ME_FIRST.txt" copy /y "%SRC%\READ_ME_FIRST.txt" "READ_ME_FIRST.txt" >nul
if exist "%SRC%\APP_UPDATE.txt" copy /y "%SRC%\APP_UPDATE.txt" "APP_UPDATE.txt" >nul

echo done> "tds_data\.update_applied" 2>nul
if exist "tds_data\.update_state.json" del /f /q "tds_data\.update_state.json" >nul 2>&1

echo.
echo DONE. Run OPEN_APP.bat — title must show v1.0.12 ^(or newer^).
if /I not "%AUTO%"=="auto" pause
exit /b 0

:fail
echo FAIL during copy. App closed? Paths correct?
pause
exit /b 1
