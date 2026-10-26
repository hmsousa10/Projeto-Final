$ErrorActionPreference='Stop'
Push-Location -LiteralPath $PSScriptRoot
$env:PATH=(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin')+';'+$env:PATH
$taskPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
try {
  & .\preparar-laboratorio.ps1
  if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Executa iniciar.cmd para preparar o Python local.' }
  & docker compose -p nexo-lab -f compose.observability.yaml build nexo semantic
  if ($LASTEXITCODE -ne 0) { throw 'Build falhou.' }
  & docker compose -p nexo-load -f compose.load.yaml up -d --force-recreate
  if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar o ensaio isolado.' }
  $taskReady=$false
  for ($taskIndex=0;$taskIndex -lt 60;$taskIndex++) {
    try {
      $taskMarker=Invoke-RestMethod -Uri 'http://127.0.0.1:8010/api/load-test-marker' -TimeoutSec 2
      if ($taskMarker.fixture -eq 'nexo-disposable-load-v1') { $taskReady=$true;break }
    } catch { }
    Start-Sleep -Seconds 1
  }
  if (-not $taskReady) { throw 'A instalacao isolada nao ficou pronta.' }
  & $taskPython -m evaluation.load_test --output docs/validacao-carga-repeticao.json
  if ($LASTEXITCODE -ne 0) { throw 'O teste encontrou falhas. Consulta o JSON antes de repetir.' }
  & $taskPython -m evaluation.check_security --output docs/validacao-seguranca-repeticao.json
  if ($LASTEXITCODE -ne 0) { throw 'Um controlo HTTP falhou.' }
  Write-Output 'Ensaio terminado. Resultados em docs/validacao-*-repeticao.json.'
} finally {
  # Fixed disposable project: never target nexo-lab or a persistent volume.
  & docker compose -p nexo-load -f compose.load.yaml down
  Pop-Location
}
