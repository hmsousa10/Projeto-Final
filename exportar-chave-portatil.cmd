@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0recuperacao-portatil.ps1" -Acao Exportar
if errorlevel 1 echo O kit nao foi concluido. A copia original foi preservada.
pause
