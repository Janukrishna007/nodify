$ErrorActionPreference = 'Stop'
$nodifyRoot = $PSScriptRoot
$nodifyBackend = Join-Path $nodifyRoot 'backend'
$nodifyFrontend = Join-Path $nodifyRoot 'frontend'
$nodifyPython = Join-Path $nodifyBackend '.venv\Scripts\python.exe'
$nodifyLogs = Join-Path $nodifyRoot '.logs'
New-Item -ItemType Directory -Path $nodifyLogs -Force | Out-Null

if (-not (Test-Path -LiteralPath $nodifyPython)) {
    py -3 -m venv (Join-Path $nodifyBackend '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment. Install Python 3.10 or newer.' }
    & $nodifyPython -m pip install -r (Join-Path $nodifyBackend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $nodifyFrontend 'node_modules\next\dist\bin\next'))) {
    Push-Location $nodifyFrontend
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    } finally { Pop-Location }
}

function Test-NodifyUrl([string] $url) {
    try { return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}

if (-not (Test-NodifyUrl 'http://127.0.0.1:8000/api/health')) {
    if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) { throw 'Port 8000 is in use by another service.' }
    Start-Process -FilePath $nodifyPython -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $nodifyBackend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $nodifyLogs 'backend.stdout.log') -RedirectStandardError (Join-Path $nodifyLogs 'backend.stderr.log') | Out-Null
}
if (-not (Test-NodifyUrl 'http://127.0.0.1:3000/upload')) {
    if (Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue) { throw 'Port 3000 is in use by another service.' }
    $nodifyNode = (Get-Command node.exe).Source
    Start-Process -FilePath $nodifyNode -ArgumentList 'node_modules/next/dist/bin/next','dev','--webpack','--hostname','127.0.0.1','--port','3000' -WorkingDirectory $nodifyFrontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $nodifyLogs 'frontend.stdout.log') -RedirectStandardError (Join-Path $nodifyLogs 'frontend.stderr.log') | Out-Null
}
Write-Output 'DisasterVision starting: http://127.0.0.1:3000/upload'
Write-Output "Server logs: $nodifyLogs"
