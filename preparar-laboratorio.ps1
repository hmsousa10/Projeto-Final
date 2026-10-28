$ErrorActionPreference = 'Stop'
foreach ($taskKeyName in @('lab-control.key', 'monitoring-discovery.key', 'semantic-access.key', 'enterprise-read.key')) {
  $taskKeyPath = Join-Path $PSScriptRoot "data\$taskKeyName"
  New-Item -ItemType Directory -Path (Split-Path $taskKeyPath) -Force | Out-Null
  if (-not (Test-Path -LiteralPath $taskKeyPath)) {
    $taskKeyBytes = New-Object byte[] 32
    $taskRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskRng.GetBytes($taskKeyBytes) } finally { $taskRng.Dispose() }
    [System.IO.File]::WriteAllText($taskKeyPath, [Convert]::ToBase64String($taskKeyBytes))
  }
}
Write-Output 'Chaves locais prontas. Os valores nao sao apresentados nem enviados ao navegador.'
