@echo off
cd /d "%~dp0"
call ".venv\Scripts\activate.bat" 2>nul
python scripts\demo_workflow.py
pause
