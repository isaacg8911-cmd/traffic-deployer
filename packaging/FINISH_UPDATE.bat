@echo off
REM Finish a stalled Wi-Fi update OR apply from zip / unzipped AppUpdate.
REM
REM Cases:
REM   A) tds_data\update_ready\TrafficDeployer.exe (stalled Wi-Fi)
REM   B) Menu / Browse: TrafficDeployer-AppUpdate-VERSION.zip or folder

setlocal EnableExtensions EnableDelayedExpansion
set "INSTALL=%~1"
set "SRC=%~2"
set "AUTO=%~1"
set "PICKER=%~dp0select_app_update.ps1"
set "PICKOUT=%TEMP%\td_finish_pick.txt"
set "UNPACK="

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

if exist "%INSTALL%\tds_data\update_ready\TrafficDeployer.exe" if exist "%INSTALL%\tds_data\update_ready\.complete" (
    set "SRC=%INSTALL%\tds_data\update_ready"
    echo Found stalled download: tds_data\update_ready
    goto :apply
)

if "%SRC%"=="" (
    if /I "%AUTO%"=="auto" (
        echo FAIL: no tds_data\update_ready — run APPLY_UPDATE or FORCE_UPDATE with a versioned zip.
        pause
        exit /b 1
    )
    if exist "%PICKER%" (
        echo.
        echo No stalled Wi-Fi stage. Pick AppUpdate zip or folder...
        if exist "%PICKOUT%" del /f /q "%PICKOUT%" >nul 2>&1
        powershell -NoProfile -ExecutionPolicy Bypass -File "%PICKER%" -Kind auto -SearchDir "%CD%" -Title "FINISH UPDATE — pick AppUpdate zip or folder" -OutFile "%PICKOUT%"
        if errorlevel 1 (
            echo Cancelled.
            pause
            exit /b 1
        )
        if exist "%PICKOUT%" set /p SRC=<"%PICKOUT%"
    ) else (
        echo.
        echo Enter UPDATE folder or zip ^(e.g. TrafficDeployer-AppUpdate-1.0.12.zip^):
        set /p "SRC=Update source: "
    )
)

if "%SRC%"=="" (
    echo FAIL: no update_ready and no update source given.
    pause
    exit /b 1
)

set "SRC=%SRC:"=%"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"

if /I "%SRC:~-4%"==".zip" (
    if not exist "%SRC%" (
        echo FAIL: zip not found: %SRC%
        pause
        exit /b 1
    )
    set "UNPACK=%TEMP%\td_finish_unpack_%RANDOM%"
    mkdir "!UNPACK!" || goto :fail
    echo Unzipping...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Expand-Archive -LiteralPath '%SRC%' -DestinationPath '!UNPACK!' -Force"
    if errorlevel 1 goto :fail
    set "SRC=!UNPACK!\TrafficDeployer"
    if not exist "!SRC!\TrafficDeployer.exe" (
        for /f "delims=" %%E in ('dir /s /b "!UNPACK!\TrafficDeployer.exe" 2^>nul') do (
            set "SRC=%%~dpE"
            if "!SRC:~-1!"=="\" set "SRC=!SRC:~0,-1!"
            goto :src_ok
        )
    )
)

:src_ok
if not exist "%SRC%\TrafficDeployer.exe" (
    if exist "%SRC%\TrafficDeployer\TrafficDeployer.exe" set "SRC=%SRC%\TrafficDeployer"
)
if not exist "%SRC%\TrafficDeployer.exe" (
    echo FAIL: no TrafficDeployer.exe in:
    echo   %SRC%
    pause
    exit /b 1
)

:apply
echo.
echo INSTALL: %INSTALL%
echo SOURCE : %SRC%
echo tds_data\ is kept.
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
if defined UNPACK if exist "%UNPACK%" rmdir /s /q "%UNPACK%" >nul 2>&1

echo.
echo DONE. Run OPEN_APP.bat — title must match VERSION.txt.
if exist "VERSION.txt" (
    set /p VER=<VERSION.txt
    echo VERSION.txt: !VER!
)
if /I not "%AUTO%"=="auto" pause
exit /b 0

:fail
if defined UNPACK if exist "%UNPACK%" rmdir /s /q "%UNPACK%" >nul 2>&1
echo FAIL during copy. App closed? Paths correct?
pause
exit /b 1
