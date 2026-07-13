@echo off
REM Wi-Fi / Tailscale update NOW — no USB, no app UI.
setlocal EnableExtensions EnableDelayedExpansion

echo.
echo Traffic Deployer — WIFI UPDATE NOW
echo ==================================
echo.

echo Finding home PC update server...
del /f /q "%TEMP%\td_home_ok.txt" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$urls=@('http://100.93.14.32:8765','http://192.168.1.30:8765'); foreach($u in $urls){ try { $r=Invoke-WebRequest -Uri ($u.TrimEnd('/')+'/version.json') -UseBasicParsing -TimeoutSec 8; if($r.StatusCode -ge 200){ Set-Content -LiteralPath $env:TEMP\td_home_ok.txt -Value $u.TrimEnd('/') -Encoding ascii; Write-Host ('OK '+$u); exit 0 } } catch { Write-Host ('miss '+$u+' — '+$_.Exception.Message) } }; exit 1"
if errorlevel 1 (
  echo.
  echo FAIL: cannot reach home PC.
  echo Tried Tailscale and home Wi-Fi.
  echo.
  echo On HOME PC keep the update server running.
  echo On LAPTOP: open Edge to http://100.93.14.32:8765/  ^(Tailscale^)
  echo If that page loads, download a FRESH WIFI_UPDATE_NOW.bat from there.
  pause
  exit /b 1
)
set /p HOME=<"%TEMP%\td_home_ok.txt"
echo Home server: %HOME%
echo.

set "INSTALL="
if exist "C:\TrafficDeployer\TrafficDeployer.exe" if exist "C:\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=C:\TrafficDeployer"
if not defined INSTALL if exist "D:\TrafficDeployer\TrafficDeployer.exe" if exist "D:\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=D:\TrafficDeployer"
if not defined INSTALL if exist "%USERPROFILE%\TrafficDeployer\TrafficDeployer.exe" if exist "%USERPROFILE%\TrafficDeployer\tds_data\california.pmtiles" set "INSTALL=%USERPROFILE%\TrafficDeployer"

if not defined INSTALL (
  echo Type your INSTALL folder ^(has OPEN_APP.bat + map^):
  set /p "INSTALL=Install: "
  set "INSTALL=!INSTALL:"=!"
)
if "%INSTALL:~-1%"=="\" set "INSTALL=%INSTALL:~0,-1%"

if not exist "%INSTALL%\TrafficDeployer.exe" (
  echo FAIL: no TrafficDeployer.exe in %INSTALL%
  pause
  exit /b 1
)
if not exist "%INSTALL%\tds_data\california.pmtiles" (
  echo FAIL: no map in %INSTALL%\tds_data — wrong folder?
  pause
  exit /b 1
)

echo Install: %INSTALL%
if exist "%INSTALL%\VERSION.txt" (
  set /p CUR=<"%INSTALL%\VERSION.txt"
  echo Current: v!CUR!
) else (
  set "CUR=unknown"
  echo Current: ^(no VERSION.txt^)
)
echo.

echo Closing app if open...
taskkill /F /IM TrafficDeployer.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Fetching version.json ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $home='%HOME%'.TrimEnd('/'); $v=Invoke-RestMethod -Uri ($home+'/version.json') -TimeoutSec 20; Write-Host ('Latest: v'+$v.version); Write-Host ('URL: '+$v.download_url); $v | ConvertTo-Json -Compress | Set-Content -LiteralPath $env:TEMP\td_ver.json -Encoding utf8; if (-not $v.download_url) { exit 2 }"
if errorlevel 1 (
  echo FAIL: version.json fetch failed from %HOME%
  pause
  exit /b 1
)

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Content $env:TEMP\td_ver.json | ConvertFrom-Json).version"`) do set "LATEST=%%A"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Content $env:TEMP\td_ver.json | ConvertFrom-Json).download_url"`) do set "ZIPURL=%%A"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Content $env:TEMP\td_ver.json | ConvertFrom-Json).sha256"`) do set "SHA=%%A"

REM If manifest still points at unreachable LAN IP, rewrite to the working HOME base.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$home='%HOME%'.TrimEnd('/'); $j=Get-Content $env:TEMP\td_ver.json -Raw | ConvertFrom-Json; $u=[string]$j.download_url; if($u -and $u -notlike ($home+'*')){ $name=($u -split '/')[-1]; $j.download_url=($home+'/'+$name); $j | ConvertTo-Json -Compress | Set-Content $env:TEMP\td_ver.json -Encoding utf8; Write-Host ('Rewrote download URL to '+$j.download_url) }"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Content $env:TEMP\td_ver.json | ConvertFrom-Json).download_url"`) do set "ZIPURL=%%A"

echo Latest : v%LATEST%
echo Zip URL: %ZIPURL%
echo.

if /I "%CUR%"=="%LATEST%" (
  echo Already on v%LATEST%. Writing update channel and launching.
  goto :seed_and_launch
)

set "STAGING=%INSTALL%\tds_data\wifi_update_now"
if exist "%STAGING%" rmdir /s /q "%STAGING%"
mkdir "%STAGING%" || goto :fail
set "ZIP=%STAGING%\update.zip"
set "UNPACK=%STAGING%\extracted"

echo Downloading ~300 MB — keep this window open (can take several minutes)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $url='%ZIPURL%'; $out='%ZIP%'; $sha='%SHA%'; Write-Host ('GET '+$url); Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 900; if ($sha) { $h=(Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash.ToLower(); if ($h -ne $sha.ToLower()) { throw ('checksum mismatch: '+$h) }; Write-Host 'Checksum OK' }; Write-Host ('Downloaded ' + [math]::Round((Get-Item $out).Length/1MB) + ' MB')"
if errorlevel 1 goto :fail

echo Unzipping...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%UNPACK%' -Force"
if errorlevel 1 goto :fail

set "SRC=%UNPACK%\TrafficDeployer"
if not exist "%SRC%\TrafficDeployer.exe" (
  if exist "%UNPACK%\TrafficDeployer\TrafficDeployer\TrafficDeployer.exe" set "SRC=%UNPACK%\TrafficDeployer\TrafficDeployer"
)
if not exist "%SRC%\TrafficDeployer.exe" (
  for /f "delims=" %%E in ('dir /s /b "%UNPACK%\TrafficDeployer.exe" 2^>nul') do (
    if not defined _FOUND (
      set "SRC=%%~dpE"
      if "!SRC:~-1!"=="\" set "SRC=!SRC:~0,-1!"
      set "_FOUND=1"
    )
  )
)
if not exist "%SRC%\TrafficDeployer.exe" (
  echo FAIL: zip missing TrafficDeployer.exe
  pause
  exit /b 1
)

echo Installing into %INSTALL% (tds_data kept)...
copy /y "%SRC%\TrafficDeployer.exe" "%INSTALL%\TrafficDeployer.exe" >nul || goto :fail
if exist "%INSTALL%\_internal\" rmdir /s /q "%INSTALL%\_internal"
xcopy /e /i /y "%SRC%\_internal" "%INSTALL%\_internal\" >nul || goto :fail
if exist "%INSTALL%\web\" rmdir /s /q "%INSTALL%\web"
if exist "%SRC%\web\" xcopy /e /i /y "%SRC%\web" "%INSTALL%\web\" >nul
if exist "%SRC%\OPEN_APP.bat" copy /y "%SRC%\OPEN_APP.bat" "%INSTALL%\OPEN_APP.bat" >nul
if exist "%SRC%\VERSION.txt" copy /y "%SRC%\VERSION.txt" "%INSTALL%\VERSION.txt" >nul
if exist "%SRC%\READ_ME_FIRST.txt" copy /y "%SRC%\READ_ME_FIRST.txt" "%INSTALL%\READ_ME_FIRST.txt" >nul
if exist "%SRC%\wifi_update_home.txt" copy /y "%SRC%\wifi_update_home.txt" "%INSTALL%\wifi_update_home.txt" >nul
echo %LATEST%> "%INSTALL%\VERSION.txt"
echo %LATEST%> "%INSTALL%\tds_data\.update_applied"
if exist "%INSTALL%\tds_data\.update_state.json" del /f /q "%INSTALL%\tds_data\.update_state.json" >nul 2>&1

echo Cleaning staging...
rmdir /s /q "%STAGING%" >nul 2>&1

:seed_and_launch
if not exist "%INSTALL%\tds_data\" mkdir "%INSTALL%\tds_data"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c=@{version_url=('%HOME%'.TrimEnd('/')+'/version.json')} | ConvertTo-Json; Set-Content -LiteralPath '%INSTALL%\tds_data\update_channel.json' -Value $c -Encoding utf8; Write-Host 'Channel written.'"

echo.
echo ========== PROOF ==========
if exist "%INSTALL%\VERSION.txt" (
  set /p VER=<"%INSTALL%\VERSION.txt"
  echo VERSION.txt: !VER!
) else (
  echo VERSION.txt: missing
)
echo Expected : %LATEST%
echo Install  : %INSTALL%
echo ===========================
echo.
echo Starting app...
start "" "%INSTALL%\OPEN_APP.bat"
echo Done. Window title must show v%LATEST%.
pause
exit /b 0

:fail
echo.
echo WIFI UPDATE FAILED — see messages above.
pause
exit /b 1
