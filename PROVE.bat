@echo off
REM One-click proof: smoke + demo workflow + field preflight (no GUI)
cd /d "%~dp0"
call scripts\prove.bat
exit /b %ERRORLEVEL%
