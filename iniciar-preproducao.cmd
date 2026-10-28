@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\preproduction.py iniciar --build
pause
