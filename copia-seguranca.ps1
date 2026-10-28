param(
  [ValidateSet('Criar','Verificar','Restaurar')][string]$Acao = 'Criar',
  [string]$Arquivo,
  [string]$Destino,
  [ValidatePattern('^[a-z][a-z0-9-]{0,23}$')][string]$Instancia
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Security
$taskRoot = Join-Path $env:LOCALAPPDATA 'Nexo'
if ($Instancia) { $taskRoot = Join-Path $taskRoot ('Installations\'+$Instancia) }
$taskBackups = Join-Path $taskRoot 'Backups'
$taskKeys = Join-Path $taskRoot 'Keys'
$taskKeyFile = Join-Path $taskKeys 'backup.dpapi'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

. (Join-Path $PSScriptRoot 'scripts\backup-common.ps1')

function Invoke-LocalRecovery([string]$Operation,[string]$Json,[string]$NewDestination='') {
  $taskArguments = @('-m','app.recovery',$Operation)
  if ($Instancia) { $taskArguments += @('--company',$Instancia) }
  if ($NewDestination) { $taskArguments += @('--destination',$NewDestination) }
  $taskOutput = $Json | & $taskPython @taskArguments
  if ($LASTEXITCODE -ne 0) { throw 'A validacao/restauro falhou. Os dados ativos foram preservados.' }
  return ($taskOutput | ConvertFrom-Json)
}

Push-Location -LiteralPath $PSScriptRoot
try {
  if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Executa iniciar.cmd para preparar o Python local.' }
  if ($Instancia) {
    # Validate an existing profile; backup must never provision a replacement.
    $taskProfileJson = & $taskPython -c 'import json,sys; from pathlib import Path; from scripts.customer_installation import prepare; print(json.dumps(prepare(Path(sys.argv[1]),sys.argv[2])[0]))' $PSScriptRoot $Instancia 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Perfil de instalacao em falta ou invalido. Nao foi criada nem alterada qualquer instalacao.' }
    $taskProfile = $taskProfileJson | ConvertFrom-Json
    if ($taskProfile.company_id -ne $Instancia) { throw 'O perfil deve identificar a instalacao selecionada.' }
  }
  if ($Acao -eq 'Criar') {
    $env:PATH = (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin')+';'+$env:PATH
    if ($Instancia) {
      $taskContainerJson = & docker inspect --type container ('nexo-test-'+$Instancia+'-nexo-1')
      if ($LASTEXITCODE -ne 0) { throw 'O contentor da instalacao nao foi encontrado.' }
      $taskContainer = @($taskContainerJson | ConvertFrom-Json)[0]
      if ($taskContainer.Config.Labels.'com.docker.compose.project' -ne ('nexo-test-'+$Instancia) -or $taskContainer.Config.Labels.'com.docker.compose.service' -ne 'nexo') {
        throw 'O contentor nao pertence ao projeto de ensaio selecionado.'
      }
      if ($taskContainer.Config.Env -notcontains 'DEMO_MODE=0' -or $taskContainer.Config.Env -notcontains ('ENTERPRISE_COMPANY_ID='+$Instancia) -or $taskContainer.Config.Env -notcontains 'DATABASE_PATH=/app/data/nexo.db') {
        throw 'O contentor nao tem a identidade e a base esperadas.'
      }
      $taskDataMount = @($taskContainer.Mounts | Where-Object { $_.Type -eq 'volume' -and $_.Destination -eq '/app/data' -and $_.Name -eq ('nexo-test-'+$Instancia+'_customer-data') })
      if ($taskDataMount.Count -ne 1) { throw 'O volume nao corresponde a instalacao selecionada.' }
      $taskContainerId = $taskContainer.Id
    }
  }
  Protect-Directory $taskRoot
  Protect-Directory $taskBackups
  Protect-Directory $taskKeys
  Assert-PlainPath $taskKeyFile
  if (-not (Test-Path -LiteralPath $taskKeyFile)) {
    if ($Acao -ne 'Criar' -or @(Get-ChildItem -LiteralPath $taskBackups -Filter '*.nexobak').Count -gt 0) {
      throw 'Chave DPAPI em falta. Nao sera gerada uma chave para substituir a das copias existentes.'
    }
    $taskKey = New-Object byte[] 32
    $taskRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskRng.GetBytes($taskKey) } finally { $taskRng.Dispose() }
    $taskProtected = [System.Security.Cryptography.ProtectedData]::Protect($taskKey,$null,'CurrentUser')
    $taskStream = [System.IO.File]::Open($taskKeyFile,'CreateNew','Write','None')
    try { $taskStream.Write($taskProtected,0,$taskProtected.Length) } finally { $taskStream.Dispose() }
  } else {
    $taskKey = [System.Security.Cryptography.ProtectedData]::Unprotect([System.IO.File]::ReadAllBytes($taskKeyFile),$null,'CurrentUser')
  }
  $taskPayload = @{ key=[Convert]::ToBase64String($taskKey) }
  if ($Acao -eq 'Criar') {
    $taskJson = $taskPayload | ConvertTo-Json -Compress
    if ($Instancia) {
      $taskOutput = $taskJson | & docker exec -i $taskContainerId python -m app.recovery create --database /app/data/nexo.db --company $Instancia
    } else {
      $taskOutput = $taskJson | & docker compose -p nexo-lab -f compose.observability.yaml exec -T nexo python -m app.recovery create --database /app/data/nexo.db
    }
    if ($LASTEXITCODE -ne 0) { throw 'A copia falhou. Verifica o Docker e a versao da imagem.' }
    $taskResult = $taskOutput | ConvertFrom-Json
    $taskPayload.archive = $taskResult.archive
    $taskVerified = Invoke-LocalRecovery 'verify' ($taskPayload | ConvertTo-Json -Compress)
    $taskBytes = [Convert]::FromBase64String($taskResult.archive)
    $taskPrefix = if ($Instancia) { 'nexo-'+$Instancia } else { 'nexo' }
    $taskName = $taskPrefix+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)+'.nexobak'
    $taskFinal = Join-Path $taskBackups $taskName
    $taskPart = $taskFinal+'.partial'
    $taskStream = [System.IO.File]::Open($taskPart,'CreateNew','Write','None')
    try { $taskStream.Write($taskBytes,0,$taskBytes.Length); $taskStream.Flush($true) } finally { $taskStream.Dispose() }
    if ((Get-FileHash -LiteralPath $taskPart -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskVerified.archive_sha256) {
      throw 'O ficheiro gravado nao coincide com a copia validada. Foi conservado como .partial.'
    }
    [System.IO.File]::Move($taskPart,$taskFinal)
    Write-Output ('Copia cifrada e verificada: '+$taskFinal)
    if ($Instancia) { Write-Output ('Instalacao validada: '+$taskVerified.installation_id) }
    Write-Output ('Incidentes: '+$taskVerified.tables.incidents+' | sessoes incluidas: '+$taskVerified.tables.sessions)
  } else {
    if (-not $Arquivo) { throw 'Indica -Arquivo com o caminho da copia .nexobak.' }
    $Arquivo = [System.IO.Path]::GetFullPath($Arquivo)
    Assert-PlainPath $Arquivo
    $taskInfo = Get-Item -LiteralPath $Arquivo
    if ($taskInfo.Length -gt 33620032) { throw 'Ficheiro acima do limite.' }
    $taskPayload.archive = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($Arquivo))
    if ($Acao -eq 'Restaurar') {
      if (-not $Destino) { throw 'Indica -Destino com uma pasta nova fora do projeto.' }
      $Destino = [System.IO.Path]::GetFullPath($Destino)
      Assert-PlainPath $Destino
      $taskRecoveryRoot = Join-Path $taskRoot 'Restauros'
      Protect-Directory $taskRecoveryRoot
      if (-not $Destino.StartsWith($taskRecoveryRoot+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw ('O destino deve ficar dentro de '+$taskRecoveryRoot+' e ser uma pasta nova.')
      }
      $taskResult = Invoke-LocalRecovery 'restore' ($taskPayload | ConvertTo-Json -Compress) $Destino
      Write-Output ('Restauro isolado: '+$taskResult.path)
      Write-Output 'Sessoes revogadas. Monitorizacao pausada. A instalacao ativa nao foi substituida.'
    } else {
      $taskResult = Invoke-LocalRecovery 'verify' ($taskPayload | ConvertTo-Json -Compress)
      Write-Output ('Copia valida. SHA-256: '+$taskResult.archive_sha256)
      Write-Output ('Incidentes: '+$taskResult.tables.incidents)
    }
  }
} finally {
  if (Get-Variable taskKey -ErrorAction SilentlyContinue) { [Array]::Clear($taskKey,0,$taskKey.Length) }
  $taskPayload=$null; $taskJson=$null; $taskOutput=$null
  Pop-Location
}
