$ErrorActionPreference='Stop'
$taskProject=Split-Path $PSScriptRoot -Parent
$taskPython=Join-Path $taskProject '.venv\Scripts\python.exe'
$env:PATH=(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin')+';'+$env:PATH
Add-Type -AssemblyName System.Security
Push-Location -LiteralPath $taskProject
try {
  $taskArchive=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Nexo\Backups') -Filter '*.nexobak' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $taskArchive) { throw 'Falta uma copia real do laboratorio.' }
  $taskKeyPath=Join-Path $env:LOCALAPPDATA 'Nexo\Keys\backup.dpapi'
  $taskBefore=(Get-FileHash -LiteralPath $taskKeyPath).Hash
  $taskKey=[System.Security.Cryptography.ProtectedData]::Unprotect([System.IO.File]::ReadAllBytes($taskKeyPath),$null,'CurrentUser')
  # Ephemeral phrase: no actual user's recovery kit is saved with this test secret.
  $taskRandom=New-Object byte[] 32
  $taskRng=[System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $taskRng.GetBytes($taskRandom) } finally { $taskRng.Dispose() }
  $taskPhrase=[Convert]::ToBase64String($taskRandom)
  $taskPayload=@{key=[Convert]::ToBase64String($taskKey);archive=[Convert]::ToBase64String([System.IO.File]::ReadAllBytes($taskArchive.FullName));
    passphrase_b64=[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($taskPhrase))}
  $taskExport=($taskPayload | ConvertTo-Json -Compress) | & $taskPython -m app.portable export
  if ($LASTEXITCODE -ne 0) { throw 'A exportacao temporaria falhou.' }
  $taskExport=$taskExport | ConvertFrom-Json
  $taskPayload.Remove('key')
  $taskPayload.wrapped_key=$taskExport.wrapped_key
  $taskReport=($taskPayload | ConvertTo-Json -Compress) | & docker run --rm -i --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 256m --cpus 1 --tmpfs '/tmp:uid=10001,gid=10001,mode=0700,size=64m' nexo:local python -m evaluation.portable_probe
  if ($LASTEXITCODE -ne 0) { throw 'O restauro Linux isolado falhou.' }
  if ((Get-FileHash -LiteralPath $taskKeyPath).Hash -ne $taskBefore) { throw 'A chave original foi alterada.' }
  $taskResult=$taskReport | ConvertFrom-Json
  $taskResult | Add-Member -NotePropertyName source_dpapi_preserved -NotePropertyValue $true
  $taskResult | Add-Member -NotePropertyName portable_kit_saved -NotePropertyValue $false
  $taskResult | Add-Member -NotePropertyName test_scope -NotePropertyValue 'Linux container on the same physical computer; no original files mounted and no DPAPI in the recipient.'
  $taskResult | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath docs/validacao-portatil-linux.json -Encoding utf8
  Write-Output ('Restauro Linux isolado aprovado: '+$taskResult.counts.incidents+' incidentes; '+$taskResult.counts.timeline+' entradas de historico.')
} finally {
  if (Get-Variable taskKey -ErrorAction SilentlyContinue) { [Array]::Clear($taskKey,0,$taskKey.Length) }
  if (Get-Variable taskRandom -ErrorAction SilentlyContinue) { [Array]::Clear($taskRandom,0,$taskRandom.Length) }
  $taskPayload=$null;$taskPhrase=$null;$taskExport=$null
  Pop-Location
}
