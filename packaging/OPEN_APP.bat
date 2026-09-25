@echo off
REM Traffic Deployer — work laptop launcher (Wi-Fi update aware).
REM OK to keep a copy in Downloads: this finds the real install and runs from there.
setlocal EnableExtensions EnableDelayedExpansion

set "TDS_WORK_LAPTOP=1"
REM Home PC update server — Tailscale first, then LAN. refresh_update_channel.ps1 discovers live peers.
set "TD_UPDATE_HOME=http://msi.tailaf9051.ts.net:8765"
set "TD_UPDATE_URL=%TD_UPDATE_HOME%/version.json"

echo.
echo Traffic Deployer - work laptop
echo ==============================
echo.

REM Prefer a real install (exe + offline map). Never treat Downloads alone as install.
set "INSTALL="
if exist "C:\TrafficDeployer\TrafficDeployer.exe" if exist "C:\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=C:\TrafficDeployer"
if not defined INSTALL if exist "D:\TrafficDeployer\TrafficDeployer.exe" if exist "D:\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=D:\TrafficDeployer"
if not defined INSTALL if exist "%USERPROFILE%\TrafficDeployer\TrafficDeployer.exe" if exist "%USERPROFILE%\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=%USERPROFILE%\TrafficDeployer"
if not defined INSTALL if exist "%USERPROFILE%\Desktop\TrafficDeployer\TrafficDeployer.exe" if exist "%USERPROFILE%\Desktop\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=%USERPROFILE%\Desktop\TrafficDeployer"

REM If this bat already lives inside a valid install, use that.
if not defined INSTALL (
  if exist "%~dp0TrafficDeployer.exe" if exist "%~dp0tds_data\california.pmtiles" set "INSTALL=%~dp0"
)

if defined INSTALL (
  rem strip trailing backslash for clean cd
  if "!INSTALL:~-1!"=="\" set "INSTALL=!INSTALL:~0,-1!"
)

if not defined INSTALL (
  echo ERROR: Could not find your Traffic Deployer install.
  echo.
  echo Looking for a folder that has BOTH:
  echo   TrafficDeployer.exe
  echo   tds_data\california.pmtiles
  echo.
  echo Usual location: C:\TrafficDeployer
  echo.
  echo This bat is in: %~dp0
  echo Running from Downloads alone will not work until the full app
  echo is installed ^(TrafficDeployer-WorkLaptop.zip extracted once^).
  echo.
  set /p "INSTALL=Type install folder ^(e.g. C:\TrafficDeployer^): "
  set "INSTALL=!INSTALL:"=!"
)

if not exist "!INSTALL!\TrafficDeployer.exe" (
  echo FAIL: no TrafficDeployer.exe in:
  echo   !INSTALL!
  pause
  exit /b 1
)

cd /d "!INSTALL!"
echo Install folder: %CD%

set "TD_VER="
if exist "VERSION.txt" set /p TD_VER=<VERSION.txt
if not defined TD_VER if exist "READ_ME_FIRST.txt" (
  for /f "tokens=2" %%v in ('findstr /I /C:"Version " READ_ME_FIRST.txt 2^>nul') do (
    if not defined TD_VER set "TD_VER=%%v"
  )
)
if defined TD_VER echo Bundle label: v%TD_VER%
echo.

if not exist "_internal\" (
  echo ERROR: _internal folder missing in install.
  echo Apply an AppUpdate into this folder, or re-extract WorkLaptop zip.
  pause
  exit /b 1
)

if not exist "tds_data\" mkdir "tds_data"
if not exist "tds_data\counter_downloads\" mkdir "tds_data\counter_downloads"

REM Refresh update channel from home PC (Tailscale or LAN). Safe overwrite.
echo Checking Tailscale / Wi-Fi update channel from home PC...
if exist "refresh_update_channel.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "refresh_update_channel.ps1"
) else (
  echo   %TD_UPDATE_HOME%
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$homes=@('http://msi.tailaf9051.ts.net:8765','http://100.93.14.32:8765','http://192.168.1.30:8765'); $dest='tds_data\update_channel.json'; $ok=$false; foreach($homeUrl in $homes){ try { Invoke-WebRequest -Uri ($homeUrl.TrimEnd('/')+'/update_channel.json') -OutFile $dest -UseBasicParsing -TimeoutSec 8; Write-Host ('  Channel OK -> '+$homeUrl); $ok=$true; break } catch {} }; if(-not $ok){ Write-Host '  WARN: could not reach home PC over Tailscale or LAN. On home PC run UPDATE_LAPTOP.bat.' }"
)
echo.

REM Stalled Wi-Fi download — finish file swap before launching old exe.
REM .complete is written last by the app; without it the staged copy is partial.
if exist "tds_data\update_ready\TrafficDeployer.exe" if exist "tds_data\update_ready\.complete" (
  echo Stalled update found — finishing before launch...
  if exist "FINISH_UPDATE.bat" (
    call "FINISH_UPDATE.bat" auto
    if errorlevel 1 (
      echo FINISH_UPDATE failed. Close TrafficDeployer.exe in Task Manager and retry.
      pause
      exit /b 1
    )
    set "TD_VER="
    if exist "VERSION.txt" set /p TD_VER=<VERSION.txt
    if defined TD_VER echo Bundle label now: v%TD_VER%
  ) else (
    echo FINISH_UPDATE.bat missing in install folder.
    echo On laptop browser open %TD_UPDATE_HOME%/ then retry, or copy FINISH_UPDATE.bat into install.
    pause
    exit /b 1
  )
)

if not exist "tds_data\california.pmtiles" (
  echo ERROR: Offline map missing ^(tds_data\california.pmtiles^).
  echo First install needs TrafficDeployer-WorkLaptop.zip — keep tds_data\.
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
echo Stay ONLINE ^(tap I'm online if it says OFFLINE^) for Wi-Fi updates.
echo Window title must show the new version after an update.
echo.
start "" "%CD%\TrafficDeployer.exe"
exit /b 0
