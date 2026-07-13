@echo off
REM Apply AppUpdate into an EXISTING install. Never writes into the zip/download folder.
REM
REM Usage (recommended):
REM   APPLY_UPDATE.bat "C:\TrafficDeployer" "C:\TDUpdate\TrafficDeployer"
REM     arg1 = INSTALL folder (has tds_data\ and current TrafficDeployer.exe)
REM     arg2 = UPDATE folder  (unzipped new TrafficDeployer.exe + _internal)
REM
REM Or double-click and answer the two prompts.

setlocal EnableExtensions
set "INSTALL=%~1"
set "SRC=%~2"

echo.
echo Traffic Deployer — APPLY UPDATE
echo ================================
echo This copies NEW files INTO your install folder.
echo Your download/unzip folder is only the SOURCE — it is not modified as the app home.
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

REM Strip quotes / trailing slash
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
    echo.
    echo Enter the UPDATE folder ^(unzipped AppUpdate — has NEW TrafficDeployer.exe^).
    echo Example: C:\TDUpdate\TrafficDeployer
    echo Or: C:\Users\...\Downloads\TrafficDeployer
    set /p "SRC=Update folder: "
)

if "%SRC%"=="" (
    echo FAIL: update folder required.
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

if /I "%INSTALL%"=="%SRC%" (
    echo FAIL: install folder and update folder are the SAME path.
    echo Unzip the update somewhere else ^(e.g. C:\TDUpdate^), then point SOURCE there
    echo and INSTALL at your real app folder ^(e.g. C:\TrafficDeployer^).
    pause
    exit /b 1
)

echo.
echo CLOSE Traffic Deployer if it is open.
echo.
echo INSTALL ^(destination^): %INSTALL%
echo UPDATE  ^(source^):      %SRC%
echo.
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

echo.
echo DONE — updated install:
echo   %INSTALL%
echo Run OPEN_APP.bat there. Title should show the new version ^(e.g. v1.0.12^).
pause
exit /b 0

:fail
echo FAIL during copy. App closed? Paths correct?
pause
exit /b 1
