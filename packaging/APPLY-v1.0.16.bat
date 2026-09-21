@echo off
REM One-click apply v1.0.16. Downloads the installer from the home PC, then runs it.
setlocal
echo.
echo Traffic Deployer APPLY v1.0.16
echo Close Traffic Deployer if it is open.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$urls=@('http://192.168.1.30:8765/APPLY-v1.0.16.ps1','http://100.93.14.32:8765/APPLY-v1.0.16.ps1','http://msi.tailaf9051.ts.net:8765/APPLY-v1.0.16.ps1'); $dest=Join-Path $env:TEMP 'APPLY-v1.0.16.ps1'; $ok=$false; foreach($u in $urls){ try { Invoke-WebRequest -Uri $u -OutFile $dest -UseBasicParsing -TimeoutSec 20; if((Get-Item $dest).Length -gt 500){ Write-Host ('Got '+$u); $ok=$true; break } } catch { Write-Host ('miss '+$u) } }; if(-not $ok){ throw 'Could not download APPLY-v1.0.16.ps1 from home PC' }; Unblock-File -LiteralPath $dest; & $dest"

set RC=%ERRORLEVEL%
echo.
if not %RC%==0 echo FAIL - leave this window up and tell Forge the last error.
pause
exit /b %RC%
