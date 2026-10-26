$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
$env:PATH = (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin') + ';' + $env:PATH
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$taskCompose = @('compose', '-p', 'nexo-cycle', '-f', 'compose.observability.yaml', '-f', 'compose.cycle.yaml')
$taskStamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$taskOutput = Join-Path $PSScriptRoot "docs\validacao-operacional-$taskStamp.json"
$taskStarted = $false
try {
    if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Executa iniciar.cmd para preparar o Python.' }
    & .\preparar-laboratorio.ps1
    & docker @taskCompose build nexo semantic
    if ($LASTEXITCODE -ne 0) { throw 'Falha no build; ensaio nao iniciado.' }
    # Do not destroy an already running experiment to make room for this one.
    $taskExisting = & docker @taskCompose ps -a -q
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel consultar o projeto isolado.' }
    if ($taskExisting) { throw 'Ja existe um projeto nexo-cycle. Inspeciona-o antes de repetir.' }
    $taskStarted = $true
    & docker @taskCompose up -d --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar os contentores isolados.' }
    $taskReady = $false
    for ($taskIndex = 0; $taskIndex -lt 90; $taskIndex++) {
        try {
            $taskMarker = Invoke-RestMethod 'http://127.0.0.1:8011/api/cycle-test-marker' -TimeoutSec 2
            if ($taskMarker.fixture -eq 'nexo-disposable-cycle-v1') { $taskReady = $true; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $taskReady) { throw 'O ambiente de ensaio nao ficou pronto.' }
    $taskIds = @(& docker @taskCompose ps -q)
    if ($LASTEXITCODE -ne 0 -or $taskIds.Count -ne 7) { throw 'Esperados sete contentores isolados.' }
    $taskInspect = & docker inspect @taskIds | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel registar o ambiente Docker.' }
    $taskEnvironment = [ordered]@{
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        project = 'nexo-cycle'
        files_sha256 = @{}
        containers = @($taskInspect | ForEach-Object {
            [ordered]@{
                service = $_.Config.Labels.'com.docker.compose.service'
                image_id = $_.Image
                memory_bytes = $_.HostConfig.Memory
                nano_cpus = $_.HostConfig.NanoCpus
                readonly_root = $_.HostConfig.ReadonlyRootfs
                mounts = @($_.Mounts | Select-Object Type,Destination,RW)
                tmpfs = $_.HostConfig.Tmpfs
                networks = @($_.NetworkSettings.Networks.PSObject.Properties.Name)
                ports = $_.HostConfig.PortBindings
            }
        })
    }
    foreach ($taskFile in @('compose.observability.yaml','compose.cycle.yaml','evaluation/cycle_protocol.json')) {
        $taskEnvironment.files_sha256[$taskFile] = (Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $taskEnvironment | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath "$taskOutput.ambiente.json" -Encoding UTF8
    & $taskPython -m evaluation.cycle_test --output $taskOutput
    if ($LASTEXITCODE -ne 0) { throw "O ensaio falhou. Evidencias preservadas em $taskOutput" }
    Write-Output "Ensaio concluido; resultado e historicos: $taskOutput"
} finally {
    if ($taskStarted) {
        # Only the fixed disposable project. No -v, no live project, no filesystem deletion.
        & docker @taskCompose down
    }
    Pop-Location
}
