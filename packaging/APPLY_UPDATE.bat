@echo off
REM Apply AppUpdate into an EXISTING install. Never writes into the zip/download folder.
REM
REM Usage:
REM   APPLY_UPDATE.bat "C:\TrafficDeployer" "C:\TDUpdate\TrafficDeployer"
REM   APPLY_UPDATE.bat "C:\TrafficDeployer" "D:\TrafficDeployer-AppUpdate-1.0.12.zip"
REM Or double-click — menu / Browse for versioned zip or unzipped folder.

setlocal EnableExtensions EnableDelayedExpansion
set "INSTALL=%~1"
set "SRC=%~2"
set "PICKER=%~dp0select_app_update.ps1"
set "PICKOUT=%TEMP%\td_apply_pick.txt"
set "UNPACK="

echo.
echo Traffic Deployer — APPLY UPDATE
echo ================================
echo Copies NEW files INTO your install. Source zip/folder is not the app home.
echo Looks for: TrafficDeployer-AppUpdate-VERSION.zip  or unzipped TrafficDeployer\
echo.

if "%INSTALL%"=="" (
    echo Enter your INSTALL folder ^(where OPEN_APP.bat already lives^).
    echo Example: C:\TrafficDeployer
    set /p "INSTALL=Install folder: "
)

if "%INSTALL%"=="" (
    echo FAIL: install folder required.
    pause
    exit /b 1
)

set "INSTALL=%INSTALL:"=%"
if "%INSTALL:~-1%"=="\" set "INSTALL=%INSTALL:~0,-1%"

if not exist "%INSTALL%\TrafficDeployer.exe" (
    echo FAIL: no TrafficDeployer.exe in install folder:
    echo   %INSTALL%
    echo That must be your real install ^(not the Downloads unzip^).
    pause
    exit /b 1
)

if not exist "%INSTALL%\tds_data\" (
    echo WARN: no tds_data in install folder — wrong folder?
    echo   %INSTALL%
    echo Continue only if you are sure.
    pause
)

if "%SRC%"=="" (
    if exist "%PICKER%" (
        echo.
        echo Pick the UPDATE source ^(zip or unzipped folder^)...
        if exist "%PICKOUT%" del /f /q "%PICKOUT%" >nul 2>&1
        powershell -NoProfile -ExecutionPolicy Bypass -File "%PICKER%" -Kind auto -SearchDir "%CD%" -Title "APPLY UPDATE — pick AppUpdate zip or folder" -OutFile "%PICKOUT%"
        if errorlevel 1 (
            echo Cancelled.
            pause
            exit /b 1
        )
        if exist "%PICKOUT%" set /p SRC=<"%PICKOUT%"
    ) else (
        echo.
        echo Enter UPDATE folder or zip path.
        echo Example folder: C:\TDUpdate\TrafficDeployer
        echo Example zip:    D:\TrafficDeployer-AppUpdate-1.0.12.zip
        set /p "SRC=Update source: "
    )
)

if "%SRC%"=="" (
    echo FAIL: update source required.
    pause
    exit /b 1
)

set "SRC=%SRC:"=%"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"

REM If user picked a zip — unpack then use inner TrafficDeployer folder
if /I "%SRC:~-4%"==".zip" (
    if not exist "%SRC%" (
        echo FAIL: zip not found:
        echo   %SRC%
        pause
        exit /b 1
    )
    set "UNPACK=%TEMP%\td_apply_unpack_%RANDOM%"
    if exist "!UNPACK!" rmdir /s /q "!UNPACK!"
    mkdir "!UNPACK!" || goto :fail
    echo Unzipping %SRC% ...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Expand-Archive -LiteralPath '%SRC%' -DestinationPath '!UNPACK!' -Force"
    if errorlevel 1 goto :fail
    set "SRC=!UNPACK!\TrafficDeployer"
    if not exist "!SRC!\TrafficDeployer.exe" (
        for /f "delims=" %%E in ('dir /s /b "!UNPACK!\TrafficDeployer.exe" 2^>nul') do (
            set "SRC=%%~dpE"
            if "!SRC:~-1!"=="\" set "SRC=!SRC:~0,-1!"
            goto :src_ready
        )
    )
)

:src_ready
if not exist "%SRC%\TrafficDeployer.exe" (
    if exist "%SRC%\TrafficDeployer\TrafficDeployer.exe" set "SRC=%SRC%\TrafficDeployer"
)

if not exist "%SRC%\TrafficDeployer.exe" (
    echo FAIL: no TrafficDeployer.exe in update source:
    echo   %SRC%
    echo Expected unzipped AppUpdate or TrafficDeployer-AppUpdate-VERSION.zip
    pause
    exit /b 1
)

if /I "%INSTALL%"=="%SRC%" (
    echo FAIL: install folder and update folder are the SAME path.
    echo Unzip / pick the update somewhere else, INSTALL stays at your real app folder.
    pause
    exit /b 1
)

echo.
echo CLOSE Traffic Deployer if it is open.
echo.
echo INSTALL ^(destination^): %INSTALL%
echo UPDATE  ^(source^):      %SRC%
if defined UNPACK echo ^(from zip unpack^)
echo.
if exist "%SRC%\VERSION.txt" (
    set /p UVER=<"%SRC%\VERSION.txt"
    echo Update VERSION.txt: !UVER!
)
echo tds_data\ will NOT be deleted.
pause

tasklist /FI "IMAGENAME eq TrafficDeployer.exe" 2>nul | find /I "TrafficDeployer.exe" >nul
if not errorlevel 1 (
    echo FAIL: TrafficDeployer.exe is still running. Close it, then run again.
    pause
    exit /b 1
)

cd /d "%INSTALL%" || (
    echo FAIL: cannot open install folder.
    pause
    exit /b 1
)

echo Copying exe...
copy /y "%SRC%\TrafficDeployer.exe" "TrafficDeployer.exe" >nul || goto :fail

echo Replacing _internal...
if exist "_internal\" rmdir /s /q "_internal"
xcopy /e /i /y "%SRC%\_internal" "_internal\" >nul || goto :fail

echo Replacing web...
if exist "web\" rmdir /s /q "web"
if exist "%SRC%\web\" xcopy /e /i /y "%SRC%\web" "web\" >nul

if exist "%SRC%\OPEN_APP.bat" copy /y "%SRC%\OPEN_APP.bat" "OPEN_APP.bat" >nul
if exist "%SRC%\APP_UPDATE.txt" copy /y "%SRC%\APP_UPDATE.txt" "APP_UPDATE.txt" >nul
if exist "%SRC%\READ_ME_FIRST.txt" copy /y "%SRC%\READ_ME_FIRST.txt" "READ_ME_FIRST.txt" >nul
if exist "%SRC%\VERSION.txt" copy /y "%SRC%\VERSION.txt" "VERSION.txt" >nul
if exist "%~dp0select_app_update.ps1" copy /y "%~dp0select_app_update.ps1" "select_app_update.ps1" >nul 2>&1
if exist "%~dp0FORCE_UPDATE.bat" copy /y "%~dp0FORCE_UPDATE.bat" "FORCE_UPDATE.bat" >nul 2>&1
if exist "%~dp0FINISH_UPDATE.bat" copy /y "%~dp0FINISH_UPDATE.bat" "FINISH_UPDATE.bat" >nul 2>&1

if defined UNPACK if exist "%UNPACK%" rmdir /s /q "%UNPACK%" >nul 2>&1

echo.
echo DONE — updated install:
echo   %INSTALL%
if exist "VERSION.txt" (
    set /p VER=<VERSION.txt
    echo VERSION.txt: !VER!
)
echo Run OPEN_APP.bat there. Title must match VERSION.txt.
pause
exit /b 0

:fail
if defined UNPACK if exist "%UNPACK%" rmdir /s /q "%UNPACK%" >nul 2>&1
echo FAIL during copy. App closed? Paths correct?
pause
exit /b 1
