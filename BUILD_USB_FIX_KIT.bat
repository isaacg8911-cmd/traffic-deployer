@echo off
REM Zip USB fix kit for work laptop — no full app rebuild needed.
cd /d "%~dp0"
set "OUT=dist\USB-Fix-Kit"
set "ZIP=dist\USB-Fix-Kit.zip"

echo Packing USB fix kit...
if not exist "dist\" mkdir "dist"
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"

copy /Y "packaging\FIX_USB.bat" "%OUT%\"
copy /Y "packaging\fix_usb_ports.ps1" "%OUT%\"
copy /Y "packaging\USB_FIX_README.txt" "%OUT%\"

if exist "%ZIP%" del /f /q "%ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%OUT%\*' -DestinationPath '%CD%\%ZIP%' -Force"
if not exist "%ZIP%" (
    echo WARN: zip failed - copy folder %OUT% to work laptop instead.
    exit /b 1
)

echo.
echo DONE. Copy to work laptop:
echo   %ZIP%
echo Or copy folder: %OUT%
echo.
exit /b 0
