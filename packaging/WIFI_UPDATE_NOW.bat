@echo off
REM Thin launcher — real logic is wifi_update_now.ps1 (avoids cmd %% IP mangling).
setlocal
cd /d "%~dp0"

if not exist "%~dp0wifi_update_now.ps1" (
  echo wifi_update_now.ps1 missing — downloading from home PC...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$urls=@('http://100.93.14.32:8765/wifi_update_now.ps1','http://192.168.1.30:8765/wifi_update_now.ps1'); foreach($u in $urls){ try { Invoke-WebRequest -Uri $u -OutFile '%~dp0wifi_update_now.ps1' -UseBasicParsing -TimeoutSec 15; if(Test-Path '%~dp0wifi_update_now.ps1'){ Write-Host ('Got '+$u); exit 0 } } catch {} }; exit 1"
  if errorlevel 1 (
    echo FAIL: could not download wifi_update_now.ps1
    echo Open Edge to http://100.93.14.32:8765/ and download wifi_update_now.ps1
    echo into the same folder as this bat.
    pause
    exit /b 1
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wifi_update_now.ps1"
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
