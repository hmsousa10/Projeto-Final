$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    $taskHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
    $taskConfig = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/config' -TimeoutSec 2
    if ($taskHealth.version -eq '0.1.0' -and $null -ne $taskConfig.telemetry) {
        Write-Host 'O Nexo já está em execução. Abre http://127.0.0.1:8000 no navegador.'
        exit 0
    }
} catch {
    # A ausência de uma instância ativa é esperada no primeiro arranque.
}
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    py -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente Python. Instala Python 3.12 ou superior.' }
}
& $taskPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha na instalação das dependências.' }
Write-Host "Nexo disponível em http://127.0.0.1:8000 · Ctrl+C para parar."
& $taskPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --limit-concurrency 32 --backlog 64 --timeout-keep-alive 5
