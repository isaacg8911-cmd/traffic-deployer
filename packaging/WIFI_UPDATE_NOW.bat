@echo off
REM Thin launcher — real logic is wifi_update_now.ps1 (avoids cmd IP mangling).
setlocal
cd /d "%~dp0"

REM Refresh helper scripts from home when reachable (Tailscale MagicDNS / 100.x / LAN).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$outRoot='%~dp0'; $names=@('td_update_homes.ps1','wifi_update_now.ps1'); $urls=@('http://msi.tailaf9051.ts.net:8765','http://100.93.14.32:8765','http://192.168.1.30:8765'); $ok=0; foreach($u in $urls){ foreach($n in $names){ try { $dest=Join-Path $outRoot $n; Invoke-WebRequest -Uri ($u.TrimEnd('/')+'/'+$n) -OutFile ($dest+'.tmp') -UseBasicParsing -TimeoutSec 10; if(Test-Path ($dest+'.tmp')){ Move-Item -Force ($dest+'.tmp') $dest; $ok=1 } } catch { } } ; if($ok -eq 1){ Write-Host ('Refreshed from '+$u); exit 0 } }; if(Test-Path (Join-Path $outRoot 'wifi_update_now.ps1')){ Write-Host 'Using local wifi_update_now.ps1'; exit 0 }; exit 1"
if errorlevel 1 (
  echo FAIL: wifi_update_now.ps1 missing and home PC unreachable.
  echo Make sure Tailscale is connected, then open:
  echo   http://msi.tailaf9051.ts.net:8765/
  echo   or http://100.93.14.32:8765/
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wifi_update_now.ps1"
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
