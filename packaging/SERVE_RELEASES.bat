@echo off
REM Serve C:\TDReleases for work-laptop Wi-Fi auto-update (home PC only).
REM Binds to LAN IP (not 0.0.0.0) so MindLink OS on 127.0.0.1:8765 can coexist.
set "REL=%TD_RELEASES_DIR%"
if "%REL%"=="" set "REL=C:\TDReleases"
set "PORT=%TD_RELEASES_PORT%"
if "%PORT%"=="" set "PORT=8765"

if not exist "%REL%\version.json" (
    echo FAIL: %REL%\version.json missing.
    echo Run PUBLISH_APP_UPDATE.bat on this PC first.
    pause
    exit /b 1
)

cd /d "%REL%"
echo.
echo Traffic Deployer update server
echo   Folder: %REL%
echo   Port  : %PORT%
echo.
echo Leave this window open while the work laptop updates.
echo Press Ctrl+C to stop.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%PORT%; $rel='%REL%';" ^
  "$ips=@(); try { $ips=@(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -ExpandProperty IPAddress) } catch {}" ^
  "$hostIp=($ips | Where-Object { $_ -like '192.168.*' } | Select-Object -First 1);" ^
  "if (-not $hostIp) { $hostIp=($ips | Select-Object -First 1) };" ^
  "if (-not $hostIp) { Write-Host 'FAIL: no LAN IP'; exit 1 };" ^
  "Write-Host ('URL: http://{0}:{1}/version.json' -f $hostIp,$port);" ^
  "Set-Location -LiteralPath $rel;" ^
  "& python -c ('from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler; ThreadingHTTPServer((\"{0}\", {1}), SimpleHTTPRequestHandler).serve_forever()' -f $hostIp,$port)"
pause
