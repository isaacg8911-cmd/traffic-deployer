@echo off
REM Thin launcher — real logic is wifi_update_now.ps1 (avoids cmd IP mangling).
setlocal
cd /d "%~dp0"

REM Always refresh ps1 from home when reachable (stale Downloads copies break updates).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a='100'+'.93.14.32'; $b='192.168.1.30'; $out='%~dp0wifi_update_now.ps1'; $urls=@(('http://'+$a+':8765/wifi_update_now.ps1'),('http://'+$b+':8765/wifi_update_now.ps1')); foreach($u in $urls){ try { Invoke-WebRequest -Uri $u -OutFile ($out+'.tmp') -UseBasicParsing -TimeoutSec 12; if(Test-Path ($out+'.tmp')){ Move-Item -Force ($out+'.tmp') $out; Write-Host ('Refreshed '+$u); exit 0 } } catch { } }; if(Test-Path $out){ Write-Host 'Using local wifi_update_now.ps1'; exit 0 }; exit 1"
if errorlevel 1 (
  echo FAIL: wifi_update_now.ps1 missing and home PC unreachable.
  echo Open Edge to http://100.93.14.32:8765/ and download wifi_update_now.ps1
  echo into the same folder as this bat.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wifi_update_now.ps1"
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
