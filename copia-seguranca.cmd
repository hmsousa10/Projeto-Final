@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0copia-seguranca.ps1" -Acao Criar
if errorlevel 1 echo A copia nao foi concluida.
pause
