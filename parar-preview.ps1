$ErrorActionPreference = 'Stop'
$taskPidFile = Join-Path $PSScriptRoot 'data\preview.pid'
if (-not (Test-Path -LiteralPath $taskPidFile)) {
    Write-Host 'Não existe pré-visualização registada. Para um servidor aberto numa janela, usa Ctrl+C nessa janela.'
    exit 0
}
$taskPreviewId = [int](Get-Content -LiteralPath $taskPidFile -Raw).Trim()
$taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $taskPreviewId"
$taskExpectedPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if ($null -ne $taskProcess) {
    if ($taskProcess.ExecutablePath -ne $taskExpectedPython -or $taskProcess.CommandLine -notlike '*-m uvicorn app.main:app --host 127.0.0.1 --port 8000*') {
        throw 'O processo registado já não corresponde ao Nexo. Nenhum processo foi parado.'
    }
    $taskChildren = Get-CimInstance Win32_Process -Filter "ParentProcessId = $taskPreviewId"
    foreach ($taskChild in $taskChildren) {
        if ($taskChild.CommandLine -eq $taskProcess.CommandLine) {
            Stop-Process -Id $taskChild.ProcessId -ErrorAction SilentlyContinue
        }
    }
    Stop-Process -Id $taskPreviewId -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $taskPidFile
Write-Host 'Pré-visualização parada. Podes voltar a iniciar pelo ficheiro iniciar.cmd.'
