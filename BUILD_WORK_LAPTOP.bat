@echo off
REM One zip for work laptop: exe + offline map + road graph. Run on HOME PC (Wi-Fi).
cd /d "%~dp0"
echo.
echo Building work-laptop zip (exe + tds_data map/graph)...
echo See WORK_LAPTOP.md for the full handover checklist.
echo.
powershell -ExecutionPolicy Bypass -File scripts\build_work_laptop_zip.ps1
set RC=%ERRORLEVEL%
if %RC%==0 (
    echo.
    echo DONE. Run VERIFY_WORK_LAPTOP.bat if verify did not already pass.
) else (
    echo.
    echo BUILD FAILED or WARNINGS - read messages above. See WORK_LAPTOP.md
)
pause
exit /b %RC%
