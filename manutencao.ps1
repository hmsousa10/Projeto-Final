param(
    [ValidateSet('Estado','Preparar','Promover','Reverter','Retomar','Concluir')][string]$Acao = 'Estado',
    [string]$Arquivo,
    [switch]$Ensaio,
    [switch]$SimularFalha
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($SimularFalha -and (-not $Ensaio -or $Acao -ne 'Promover')) { throw 'A simulacao so existe no ensaio de promocao.' }
. (Join-Path $PSScriptRoot 'scripts\backup-common.ps1')
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$env:PATH = (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin') + ';' + $env:PATH
$taskProject = 'nexo-lab'
$taskComposeFile = 'compose.observability.yaml'
$taskVolume = 'nexo-lab_nexo-data'
$taskPort = 8001
if ($Ensaio) {
    $taskProject = 'nexo-maintenance-test'
    $taskComposeFile = 'compose.maintenance-test.yaml'
    $taskVolume = 'nexo-maintenance-test_maintenance-data'
    $taskPort = 8013
}
$taskCompose = @('compose','-p',$taskProject,'-f',$taskComposeFile)
$taskReports = Join-Path $env:LOCALAPPDATA 'Nexo\Manutencao'
Protect-Directory $taskReports
$taskReportPath = Join-Path $taskReports ((Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N')+'.json')
$taskReport = [ordered]@{ action=$Acao; project=$taskProject; started_at_utc=[DateTime]::UtcNow.ToString('o'); status='failed' }
$taskStopped = $false

function Invoke-Maintenance([string]$Operation,[string]$Payload='') {
    $taskRunArgs = @('run','--rm','-i','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--memory','256m','--cpus','1','--tmpfs','/tmp:uid=10001,gid=10001,mode=0700,size=64m',
        '--mount',"type=volume,source=$taskVolume,target=/app/data",'-e','NEXO_MAINTENANCE=1',
        '-e','DATABASE_PATH=/app/data/nexo.db','-e',"NEXO_MAINTENANCE_POLICY_B64=$taskPolicy64",$taskImage,
        'python','-m','app.maintenance',$Operation)
    $taskResult = $Payload | & docker @taskRunArgs
    if ($LASTEXITCODE -ne 0) { throw "A operacao local $Operation foi recusada. Consulta o estado antes de repetir." }
    return ($taskResult | ConvertFrom-Json)
}

function Start-MaintainedPortal {
    & docker @taskCompose up -d --no-deps --no-build nexo
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar o portal.' }
    for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
        try {
            $taskHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$taskPort/api/health" -TimeoutSec 2
            if ($taskHealth.status -eq 'ok') { return $taskHealth }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw 'O portal nao passou a verificacao de arranque.'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $taskIds = @(& docker @taskCompose ps -a -q nexo)
    if ($LASTEXITCODE -ne 0 -or $taskIds.Count -ne 1) { throw 'Esperado um contentor Nexo existente, ativo ou parado.' }
    $taskContainer = (& docker inspect $taskIds[0] | ConvertFrom-Json)[0]
    if ($LASTEXITCODE -ne 0) { throw 'Falhou a inspecao do contentor.' }
    if ($taskContainer.Config.Labels.'com.docker.compose.project' -ne $taskProject -or
        $taskContainer.Config.Labels.'com.docker.compose.service' -ne 'nexo') { throw 'Instalacao inesperada.' }
    $taskMount = @($taskContainer.Mounts | Where-Object Destination -eq '/app/data')
    if ($taskMount.Count -ne 1 -or $taskMount[0].Type -ne 'volume' -or $taskMount[0].Name -ne $taskVolume) {
        throw 'O volume nao corresponde a instalacao escolhida.'
    }
    if ('DATABASE_PATH=/app/data/nexo.db' -notin $taskContainer.Config.Env) { throw 'Caminho ativo inesperado.' }
    $taskImage = $taskContainer.Image
    $taskAllowed = @($taskContainer.Config.Env | Where-Object { $_.StartsWith('MONITORING_ALLOWED_URLS=') })
    if ($taskAllowed.Count -ne 1) { throw 'Politica de destinos em falta.' }
    $taskAllowed = $taskAllowed[0].Substring('MONITORING_ALLOWED_URLS='.Length)
    $taskPolicy64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($taskAllowed))
    $taskReport.image_id = $taskImage
    $taskReport.before = Invoke-Maintenance 'status'
    switch ($Acao) {
        'Estado' { $taskReport.result = $taskReport.before }
        'Preparar' {
            if (-not $Arquivo) {
                if ($Ensaio) { throw 'Indica uma copia cifrada para o ensaio.' }
                & .\copia-seguranca.ps1 -Acao Criar
                $Arquivo = (Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Nexo\Backups') -Filter '*.nexobak' |
                    Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
            }
            Assert-PlainPath $Arquivo
            $taskInfo = Get-Item -LiteralPath $Arquivo
            if ($taskInfo.Length -gt 33620032) { throw 'Copia acima do limite.' }
            Add-Type -AssemblyName System.Security
            $taskKeyFile = Join-Path $env:LOCALAPPDATA 'Nexo\Keys\backup.dpapi'
            Assert-PlainPath $taskKeyFile
            $taskKeyInfo = Get-Item -LiteralPath $taskKeyFile
            if ($taskKeyInfo.Length -gt 4096) { throw 'Ficheiro DPAPI invalido.' }
            $taskKey = [System.Security.Cryptography.ProtectedData]::Unprotect((Read-BoundedBytes $taskKeyFile 4096),$null,'CurrentUser')
            $taskPayload = @{key=[Convert]::ToBase64String($taskKey);archive=[Convert]::ToBase64String((Read-BoundedBytes $taskInfo.FullName 33620032))} | ConvertTo-Json -Compress
            $taskReport.result = Invoke-Maintenance 'stage' $taskPayload
        }
        { $_ -in 'Promover','Reverter' } {
            if ($Acao -eq 'Promover' -and $taskReport.before.phase -ne 'staged') { throw 'Prepara uma copia antes de promover.' }
            if ($Acao -eq 'Reverter' -and $taskReport.before.phase -notin @('staged','prepared','switching','promoted','committed','rolling_back','rolled_back')) {
                throw 'Nao existe uma manutencao para reverter.'
            }
            & docker @taskCompose stop -t 20 nexo
            if ($LASTEXITCODE -ne 0) { throw 'O portal nao parou; troca recusada.' }
            $taskStopped = $true
            $taskStoppedContainer = (& docker inspect $taskIds[0] | ConvertFrom-Json)[0]
            if ($taskStoppedContainer.State.Running) { throw 'O contentor continua ativo.' }
            if ($Acao -eq 'Promover') { $taskReport.result = Invoke-Maintenance 'promote' }
            else { $taskReport.result = Invoke-Maintenance 'rollback' }
            $taskReport.health = Start-MaintainedPortal
            if ($SimularFalha) { throw 'Falha de verificacao provocada exclusivamente no ensaio.' }
            if ($taskReport.result.phase -notin @('cancelled','rolled_back')) {
                $taskReport.verification = Invoke-Maintenance 'verify'
            } elseif ($taskReport.result.phase -eq 'rolled_back') {
                $taskReport.verification = Invoke-Maintenance 'check'
            }
            $taskStopped = $false
        }
        'Retomar' { $taskReport.result = Invoke-Maintenance 'resume' }
        'Concluir' { $taskReport.result = Invoke-Maintenance 'commit' }
    }
    $taskReport.status = 'passed'
    Write-Output ('Manutencao concluida: '+$Acao)
} catch {
    $taskReport.error = $_.Exception.Message
    if ($taskStopped -and $Acao -eq 'Promover') {
        try {
            & docker @taskCompose stop -t 20 nexo
            if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel parar para reverter.' }
            $taskReport.automatic_rollback = Invoke-Maintenance 'rollback'
            $taskReport.rollback_health = Start-MaintainedPortal
            if ($taskReport.automatic_rollback.phase -eq 'rolled_back') { $taskReport.rollback_check = Invoke-Maintenance 'check' }
            Write-Output 'A promocao falhou; o estado anterior foi reposto e o portal voltou a responder.'
        } catch {
            $taskReport.rollback_error = $_.Exception.Message
            Write-Warning 'A reversao automatica nao ficou confirmada. Conserva os dados e consulta Estado; nao forces um arranque.'
        }
    }
    throw
} finally {
    if (Get-Variable taskKey -ErrorAction SilentlyContinue) { [Array]::Clear($taskKey,0,$taskKey.Length) }
    $taskPayload = $null
    $taskReport.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    $taskReport | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $taskReportPath -Encoding UTF8
    Write-Output ('Registo local: '+$taskReportPath)
    Pop-Location
}
