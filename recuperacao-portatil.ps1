param(
  [ValidateSet('Exportar','Verificar','Restaurar')][string]$Acao='Exportar',
  [string]$Arquivo,
  [string]$Kit,
  [string]$Destino
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Security
. (Join-Path $PSScriptRoot 'scripts\backup-common.ps1')
$taskRoot=Join-Path $env:LOCALAPPDATA 'Nexo'
$taskPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Read-Phrase([switch]$Confirm) {
  $taskSecure=Read-Host 'Frase-passe do kit (20 a 256 caracteres; entrada oculta)' -AsSecureString
  $taskPointer=[System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecure)
  try { $taskPlain=[System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer) }
  finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer); $taskSecure.Dispose() }
  if ($Confirm) {
    $taskSecure2=Read-Host 'Repete a mesma frase-passe' -AsSecureString
    $taskPointer2=[System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecure2)
    try { $taskPlain2=[System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer2) }
    finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer2); $taskSecure2.Dispose() }
    if (-not [String]::Equals($taskPlain,$taskPlain2,[StringComparison]::Ordinal)) { throw 'As frases-passe nao coincidem.' }
    $taskPlain2=$null
  }
  $taskBytes=[System.Text.Encoding]::UTF8.GetBytes($taskPlain)
  try { return [Convert]::ToBase64String($taskBytes) }
  finally { [Array]::Clear($taskBytes,0,$taskBytes.Length); $taskPlain=$null }
}

function Invoke-Portable([string]$Operation,[hashtable]$Payload,[string]$NewDestination='') {
  $taskArguments=@('-m','app.portable',$Operation)
  if ($NewDestination) { $taskArguments+=@('--destination',$NewDestination) }
  # ASCII JSON envelope preserves UTF-8 accents on Windows PowerShell 5 too.
  $taskJson=$Payload | ConvertTo-Json -Compress
  $taskOutput=$taskJson | & $taskPython @taskArguments
  if ($LASTEXITCODE -ne 0) { throw 'Operacao recusada. Nenhuma base ativa foi substituida.' }
  return ($taskOutput | ConvertFrom-Json)
}

function Read-BoundedFile([string]$Path,[long]$Limit) {
  Assert-PlainPath $Path
  $taskStream=[System.IO.File]::Open($Path,'Open','Read','Read')
  $taskMemory=New-Object System.IO.MemoryStream
  try {
    if ($taskStream.Length -gt $Limit) { throw 'Ficheiro acima do limite.' }
    $taskBuffer=New-Object byte[] 65536
    while (($taskRead=$taskStream.Read($taskBuffer,0,$taskBuffer.Length)) -gt 0) {
      if ($taskMemory.Length+$taskRead -gt $Limit) { throw 'Ficheiro acima do limite.' }
      $taskMemory.Write($taskBuffer,0,$taskRead)
    }
    return ,$taskMemory.ToArray()
  } finally { $taskStream.Dispose();$taskMemory.Dispose() }
}

function Write-NewFile([string]$Path,[byte[]]$Bytes) {
  $taskStream=[System.IO.File]::Open($Path,'CreateNew','Write','None')
  try { $taskStream.Write($Bytes,0,$Bytes.Length); $taskStream.Flush($true) }
  finally { $taskStream.Dispose() }
}

Push-Location -LiteralPath $PSScriptRoot
try {
  if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Prepara o Python local com iniciar.cmd.' }
  $taskPayload=@{}
  if ($Acao -eq 'Exportar') {
    $taskKeyFile=Join-Path $taskRoot 'Keys\backup.dpapi'
    $taskProtected=Read-BoundedFile $taskKeyFile 4096
    $taskKey=[System.Security.Cryptography.ProtectedData]::Unprotect($taskProtected,$null,'CurrentUser')
    if (-not $Arquivo) {
      $taskBackupFolder=Join-Path $taskRoot 'Backups'
      Assert-PlainPath $taskBackupFolder
      $taskLatest=Get-ChildItem -LiteralPath $taskBackupFolder -Filter '*.nexobak' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
      if (-not $taskLatest) { throw 'Cria primeiro uma copia com copia-seguranca.cmd.' }
      $Arquivo=$taskLatest.FullName
    }
    $taskArchive=Read-BoundedFile $Arquivo 33620032
    Write-Output ('Copia selecionada: '+$Arquivo)
    $taskPayload=@{key=[Convert]::ToBase64String($taskKey);archive=[Convert]::ToBase64String($taskArchive);passphrase_b64=(Read-Phrase -Confirm)}
    $taskExport=Invoke-Portable 'export' $taskPayload
    Protect-Directory $taskRoot
    $taskKits=Join-Path $taskRoot 'Kits'
    Protect-Directory $taskKits
    $taskFinal=Join-Path $taskKits ('kit-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N'))
    $taskPartial=$taskFinal+'.partial'
    $taskResolvedKits=[System.IO.Path]::GetFullPath($taskKits)+[System.IO.Path]::DirectorySeparatorChar
    foreach ($taskCandidate in @($taskFinal,$taskPartial)) {
      Assert-PlainPath $taskCandidate
      if (-not [System.IO.Path]::GetFullPath($taskCandidate).StartsWith($taskResolvedKits,[StringComparison]::OrdinalIgnoreCase)) { throw 'Destino fora da pasta de kits.' }
    }
    [void][System.IO.Directory]::CreateDirectory($taskPartial)
    $taskDataFile=Join-Path $taskPartial 'copia.nexobak'
    $taskPortableFile=Join-Path $taskPartial 'chave.nexokey'
    Write-NewFile $taskDataFile $taskArchive
    Write-NewFile $taskPortableFile ([Convert]::FromBase64String($taskExport.wrapped_key))
    $taskPayload.Remove('key')
    $taskPayload.archive=[Convert]::ToBase64String((Read-BoundedFile $taskDataFile 33620032))
    $taskPayload.wrapped_key=[Convert]::ToBase64String((Read-BoundedFile $taskPortableFile 84))
    $taskVerified=Invoke-Portable 'verify' $taskPayload
    if ($taskVerified.archive_sha256 -ne $taskExport.report.archive_sha256) { throw 'O kit gravado nao coincide com a copia original.' }
    $taskReadme=@'
KIT DE RECUPERACAO NEXO
Ficheiros necessarios: copia.nexobak e chave.nexokey.
A frase-passe nao esta neste kit. Guarda-a separadamente.
Usa o codigo e dependencias compativeis do Nexo, com Python 3.12 ou superior.
No Windows: recuperacao-portatil.ps1 -Acao Verificar -Kit CAMINHO_DO_KIT
Para restaurar: -Acao Restaurar -Kit CAMINHO_DO_KIT -Destino PASTA_NOVA
O destino Windows deve estar em %LOCALAPPDATA%\Nexo\Restauros.
Nunca e substituida automaticamente uma base ativa.
Consulta docs/recuperacao-portatil.md no projeto.
'@
    Write-NewFile (Join-Path $taskPartial 'LE-ME.txt') ([System.Text.Encoding]::UTF8.GetBytes($taskReadme))
    [System.IO.Directory]::Move($taskPartial,$taskFinal)
    Write-Output ('Kit cifrado, gravado e verificado: '+$taskFinal)
    Write-Output 'Transporta os dois ficheiros e guarda a frase-passe num local separado. A chave DPAPI local foi preservada.'
  } else {
    if (-not $Kit) { throw 'Indica -Kit com a pasta dos dois ficheiros.' }
    $Kit=[System.IO.Path]::GetFullPath($Kit)
    Assert-PlainPath $Kit
    $taskArchive=Read-BoundedFile (Join-Path $Kit 'copia.nexobak') 33620032
    $taskWrapped=Read-BoundedFile (Join-Path $Kit 'chave.nexokey') 84
    $taskPayload=@{archive=[Convert]::ToBase64String($taskArchive);wrapped_key=[Convert]::ToBase64String($taskWrapped);passphrase_b64=(Read-Phrase)}
    if ($Acao -eq 'Restaurar') {
      if (-not $Destino) { throw 'Indica -Destino com uma pasta nova.' }
      Protect-Directory $taskRoot
      $taskRestoreRoot=Join-Path $taskRoot 'Restauros'
      Protect-Directory $taskRestoreRoot
      $Destino=[System.IO.Path]::GetFullPath($Destino)
      Assert-PlainPath $Destino
      if (-not $Destino.StartsWith($taskRestoreRoot+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'O destino deve ficar dentro de %LOCALAPPDATA%\Nexo\Restauros.' }
      $taskResult=Invoke-Portable 'restore' $taskPayload $Destino
      Write-Output ('Base recuperada numa pasta nova: '+$taskResult.path)
      Write-Output 'Monitorizacao pausada e sessoes revogadas. A instalacao ativa foi preservada.'
    } else {
      $taskResult=Invoke-Portable 'verify' $taskPayload
      Write-Output ('Kit valido. Incidentes: '+$taskResult.tables.incidents+' | SHA-256: '+$taskResult.archive_sha256)
    }
  }
} finally {
  if (Get-Variable taskKey -ErrorAction SilentlyContinue) { [Array]::Clear($taskKey,0,$taskKey.Length) }
  $taskPayload=$null; $taskArchive=$null; $taskExport=$null
  Pop-Location
}
