@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 %*
pause
