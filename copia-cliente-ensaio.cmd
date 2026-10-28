@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0copia-seguranca.ps1" -Acao Criar -Instancia atlas
if errorlevel 1 echo A copia da Atlas nao foi concluida.
pause
