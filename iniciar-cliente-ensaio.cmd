@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\customer_installation.py iniciar --build
pause
