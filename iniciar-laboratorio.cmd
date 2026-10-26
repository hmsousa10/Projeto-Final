@echo off
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;%PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar-laboratorio.ps1"
if errorlevel 1 exit /b 1
docker compose -p nexo-lab -f compose.observability.yaml up -d --build
if errorlevel 1 (
  echo Verifica se o Docker Desktop esta iniciado.
  pause
  exit /b 1
)
echo Laboratorio disponivel em http://127.0.0.1:8001
echo O primeiro arranque pode demorar alguns segundos a recolher metricas.
pause
