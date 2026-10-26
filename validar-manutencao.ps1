param([switch]$RetomarEnsaioInicial,[switch]$RepetirEnsaioRevertido)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($RetomarEnsaioInicial -and $RepetirEnsaioRevertido) { throw 'Escolhe apenas um modo de reutilizacao explicita.' }
Push-Location -LiteralPath $PSScriptRoot
$env:PATH = (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin')+';'+$env:PATH
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$taskCompose = @('compose','-p','nexo-maintenance-test','-f','compose.maintenance-test.yaml')
$taskStarted = $false
$taskReport = [ordered]@{started_at_utc=[DateTime]::UtcNow.ToString('o');status='failed';project='nexo-maintenance-test'}
$taskOutput = Join-Path $PSScriptRoot ('docs\validacao-manutencao-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)+'.json')

function Exercise-Action([string]$Action,[switch]$ExpectedFailure) {
    $taskArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File', (Join-Path $PSScriptRoot 'manutencao.ps1'),'-Ensaio','-Acao',$Action)
    if ($Action -eq 'Preparar') { $taskArgs += @('-Arquivo',$taskArchive) }
    if ($ExpectedFailure) { $taskArgs += '-SimularFalha' }
    $taskPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $taskLines = @(& powershell @taskArgs 2>&1 | ForEach-Object { $_.ToString() })
        $taskExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $taskPreference }
    $taskLines | Write-Output | Out-Host
    $taskReportLine = @($taskLines | Where-Object { $_ -like 'Registo local: *' })
    if ($taskReportLine.Count -ne 1) { throw 'Nao foi encontrado o diario local.' }
    $taskReportFile = $taskReportLine[0].Substring('Registo local: '.Length)
    $taskResult = Get-Content -LiteralPath $taskReportFile -Raw | ConvertFrom-Json
    if ($ExpectedFailure) {
        if ($taskExit -eq 0 -or $taskResult.status -ne 'failed' -or
            $taskResult.automatic_rollback.phase -ne 'rolled_back' -or $taskResult.rollback_health.status -ne 'ok') {
            throw 'A falha simulada nao provocou uma reversao confirmada.'
        }
    } elseif ($taskExit -ne 0 -or $taskResult.status -ne 'passed') { throw "Falhou a acao $Action" }
    return $taskResult
}

function Read-Rehearsal {
    $taskRead = & $taskPython -m evaluation.maintenance_probe
    if ($LASTEXITCODE -ne 0) { throw 'Falhou a verificacao HTTP do ensaio.' }
    return ($taskRead | ConvertFrom-Json)
}

try {
    # Refuse reuse. Never remove an existing volume to force a fresh experiment.
    $taskExisting = @(& docker @taskCompose ps -a -q)
    if ($LASTEXITCODE -ne 0 -or $taskExisting.Count) { throw 'Ja existe um ensaio de manutencao.' }
    $taskVolumes = @(& docker volume ls --format '{{.Name}}')
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel consultar os volumes.' }
    if ('nexo-maintenance-test_maintenance-data' -in $taskVolumes -and -not ($RetomarEnsaioInicial -or $RepetirEnsaioRevertido)) { throw 'O volume de um ensaio anterior ainda existe. Preserva-o e inspeciona-o antes de repetir.' }
    $taskReport.reused_initial_fixture = [bool]$RetomarEnsaioInicial
    $taskReport.repeated_reverted_fixture = [bool]$RepetirEnsaioRevertido
    $taskReport.source_sha256 = @{}
    foreach ($taskFile in @('app/maintenance.py','app/main.py','manutencao.ps1','validar-manutencao.ps1','compose.maintenance-test.yaml','evaluation/maintenance_probe.py')) {
        $taskReport.source_sha256[$taskFile] = (Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    & docker compose -p nexo-lab -f compose.observability.yaml build nexo
    if ($LASTEXITCODE -ne 0) { throw 'Build falhou.' }
    & .\copia-seguranca.ps1 -Acao Criar
    $taskArchive = (Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Nexo\Backups') -Filter '*.nexobak' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
    $taskReport.archive_sha256 = (Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskReport.archive_file = [IO.Path]::GetFileName($taskArchive)
    $taskStarted = $true
    & docker @taskCompose up -d --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar o ensaio.' }
    $taskReady = $false
    for ($taskAttempt=0;$taskAttempt -lt 45;$taskAttempt++) {
        try {
            if ((Invoke-RestMethod 'http://127.0.0.1:8013/api/health' -TimeoutSec 2).status -eq 'ok') { $taskReady=$true;break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $taskReady) { throw 'O ensaio nao ficou pronto.' }
    if ($RetomarEnsaioInicial -or $RepetirEnsaioRevertido) {
        $taskInitialState = Exercise-Action 'Estado'
        if ($RetomarEnsaioInicial -and $taskInitialState.result.phase -ne 'none') { throw 'A retoma inicial exige uma instalacao sem qualquer preparacao anterior.' }
        if ($RepetirEnsaioRevertido -and $taskInitialState.result.phase -ne 'rolled_back') { throw 'A repeticao exige uma reversao anterior concluida.' }
    }
    $taskReport.before = Read-Rehearsal
    $taskReport.stage = Exercise-Action 'Preparar'
    $taskReport.promotion = Exercise-Action 'Promover'
    $taskReport.promoted_http = Read-Rehearsal
    if ($taskReport.promoted_http.incidents -ne $taskReport.stage.result.candidate.tables.incidents -or
        $taskReport.promoted_http.timeline -ne $taskReport.stage.result.candidate.tables.timeline -or
        $taskReport.promotion.verification.enabled_targets -ne 0) { throw 'Historico ou pausa nao confirmados.' }
    if ($taskReport.before.incidents -eq $taskReport.promoted_http.incidents) { throw 'A base original e a recuperada devem ser distinguiveis.' }
    $taskReport.resume = Exercise-Action 'Retomar'
    if ($taskReport.resume.result.resumed_targets -ne @($taskReport.stage.result.resume_targets).Count) { throw 'Retoma incorreta.' }
    $taskReport.rollback = Exercise-Action 'Reverter'
    $taskReport.rolled_back_http = Read-Rehearsal
    if ($taskReport.rolled_back_http.incidents -ne $taskReport.before.incidents -or
        $taskReport.rolled_back_http.timeline -ne $taskReport.before.timeline) { throw 'O estado anterior nao foi reposto.' }
    $taskReport.second_stage = Exercise-Action 'Preparar'
    $taskReport.simulated_failure = Exercise-Action 'Promover' -ExpectedFailure
    $taskReport.after_failure_http = Read-Rehearsal
    if ($taskReport.after_failure_http.incidents -ne $taskReport.before.incidents -or
        $taskReport.after_failure_http.timeline -ne $taskReport.before.timeline) { throw 'A reversao automatica nao preservou o estado anterior.' }
    $taskReport.status = 'passed'
} catch {
    $taskReport.error = $_.Exception.Message
    throw
} finally {
    $taskReport.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    $taskReport | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $taskOutput -Encoding UTF8
    Write-Output ('Resultado do ensaio: '+$taskOutput)
    if ($taskStarted) {
        & docker @taskCompose down
        Write-Output 'Volume de ensaio conservado com os pontos de retorno; nenhum volume foi eliminado.'
    }
    Pop-Location
}
