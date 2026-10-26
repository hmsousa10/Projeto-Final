param([string]$Output='docs\validacao-kit-windows.json')
$ErrorActionPreference='Stop'
$taskProject=Split-Path $PSScriptRoot -Parent
. (Join-Path $taskProject 'scripts\backup-common.ps1')
Add-Type -AssemblyName System.Security
$taskOriginal=$env:LOCALAPPDATA
$taskPython=Join-Path $taskProject '.venv\Scripts\python.exe'
$taskFixtureRoot=Join-Path $taskOriginal ('Nexo\Ensaios\portatil-'+[Guid]::NewGuid().ToString('N'))
Protect-Directory $taskFixtureRoot
$taskProfileA=Join-Path $taskFixtureRoot 'perfilA'
$taskProfileB=Join-Path $taskFixtureRoot 'perfilB'
Protect-Directory $taskProfileA
Protect-Directory $taskProfileB
# Synthetic fixture only. No real user's portable passphrase is collected here.
$global:NexoPortableSyntheticPhrase='Frase de ensaio descartavel '+[char]0x00E7+[char]0x03A9+[char]0x6F22+' 2026!'
function Read-Host {
  param([string]$Prompt,[switch]$AsSecureString)
  return (ConvertTo-SecureString -String $global:NexoPortableSyntheticPhrase -AsPlainText -Force)
}
$taskCode=@'
import base64,json,secrets,sys,os
from pathlib import Path
from app.db import initialize
from app.seed import seed
from app.recovery import create
os.environ['DEMO_PASSWORD']='EstudoLocal2026!'
p=Path(sys.argv[1])/'fixture.db'
initialize(p);seed(p)
k=secrets.token_bytes(32)
a,m=create(p,k)
print(json.dumps({'key':base64.b64encode(k).decode(),'archive':base64.b64encode(a).decode()}))
'@
Push-Location -LiteralPath $taskProject
try {
  $taskFixture=(& $taskPython -c $taskCode $taskProfileA) | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0) { throw 'Fixture falhou.' }
  $env:LOCALAPPDATA=$taskProfileA
  Protect-Directory (Join-Path $taskProfileA 'Nexo\Keys')
  Protect-Directory (Join-Path $taskProfileA 'Nexo\Backups')
  $taskProtected=[System.Security.Cryptography.ProtectedData]::Protect([Convert]::FromBase64String($taskFixture.key),$null,'CurrentUser')
  $taskKeyFile=Join-Path $taskProfileA 'Nexo\Keys\backup.dpapi'
  [System.IO.File]::WriteAllBytes($taskKeyFile,$taskProtected)
  $taskArchive=Join-Path $taskProfileA 'Nexo\Backups\fixture.nexobak'
  [System.IO.File]::WriteAllBytes($taskArchive,[Convert]::FromBase64String($taskFixture.archive))
  $taskBefore=(Get-FileHash -LiteralPath $taskKeyFile).Hash
  & .\recuperacao-portatil.ps1 -Acao Exportar -Arquivo $taskArchive | Out-Null
  $taskKit=(Get-ChildItem -LiteralPath (Join-Path $taskProfileA 'Nexo\Kits') -Directory | Where-Object { $_.Name -notlike '*.partial' } | Select-Object -First 1).FullName
  if ((Get-FileHash -LiteralPath $taskKeyFile).Hash -ne $taskBefore) { throw 'A chave local foi alterada.' }
  $env:LOCALAPPDATA=$taskProfileB
  & .\recuperacao-portatil.ps1 -Acao Verificar -Kit $taskKit | Out-Null
  $taskDestination=Join-Path $taskProfileB 'Nexo\Restauros\ensaio'
  & .\recuperacao-portatil.ps1 -Acao Restaurar -Kit $taskKit -Destino $taskDestination | Out-Null
  if (Test-Path -LiteralPath (Join-Path $taskProfileB 'Nexo\Keys\backup.dpapi')) { throw 'O destino nao deve importar a chave local.' }
  $taskDatabase=Join-Path $taskDestination 'nexo.db'
  $taskHash=(Get-FileHash -LiteralPath $taskDatabase).Hash
  $taskExistingRejected=$false
  try { & .\recuperacao-portatil.ps1 -Acao Restaurar -Kit $taskKit -Destino $taskDestination 2>$null | Out-Null }
  catch { $taskExistingRejected=$true }
  if (-not $taskExistingRejected -or (Get-FileHash -LiteralPath $taskDatabase).Hash -ne $taskHash) { throw 'Protecao contra substituicao falhou.' }
  $global:NexoPortableSyntheticPhrase='Frase de teste errada e descartavel 2026!'
  $taskWrongRejected=$false
  try { & .\recuperacao-portatil.ps1 -Acao Verificar -Kit $taskKit 2>$null | Out-Null }
  catch { $taskWrongRejected=$true }
  if (-not $taskWrongRejected) { throw 'Frase errada foi aceite.' }
  @{synthetic_keys_only=$true;unicode_phrase_roundtrip=$true;dpapi_source_preserved=$true;destination_dpapi_file_required=$false;
    export_verify_restore='passed';wrong_phrase_rejected=$taskWrongRejected;existing_destination_preserved=$taskExistingRejected;
    powershell_version=$PSVersionTable.PSVersion.ToString();fixture_path=$taskFixtureRoot} |
    ConvertTo-Json | Set-Content -LiteralPath $Output -Encoding UTF8
  Write-Output 'Ensaio Windows do kit portatil aprovado com dados sinteticos.'
} finally {
  $env:LOCALAPPDATA=$taskOriginal
  $taskFixture=$null
  Remove-Variable -Name NexoPortableSyntheticPhrase -Scope Global -ErrorAction SilentlyContinue
  Pop-Location
}
