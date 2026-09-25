param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$url = 'http://127.0.0.1:8000'
function Test-Workspace {
    try {
        $status = Invoke-RestMethod -Uri "$url/api/metadata" -TimeoutSec 2
        return ($status.application -eq 'DownloadVideoProcessor' -and $status.version -eq 2)
    } catch { return $false }
}
if (Test-Workspace) {
    if (-not $NoBrowser) { Start-Process $url }
    Write-Host "Video workspace is ready: $url"
    exit 0
}
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'Port 8000 is occupied. Close the old video server or the application using this port, then try again.' }
$pythonCommand = Get-Command python -ErrorAction Stop
$runtimeDir = Join-Path $projectRoot 'output'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$scriptPath = Join-Path $projectRoot 'scripts\run_similarity.py'
$stdoutPath = Join-Path $runtimeDir 'web-launcher.stdout.log'
$stderrPath = Join-Path $runtimeDir 'web-launcher.stderr.log'
$env:PYTHONIOENCODING = 'utf-8'
$backendProcess = Start-Process -FilePath $pythonCommand.Source -ArgumentList @('-u', ('"' + $scriptPath + '"'), '--server-only', '--no-browser') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (Test-Workspace) {
        Set-Content -LiteralPath (Join-Path $runtimeDir 'web-server.pid') -Value $backendProcess.Id
        if (-not $NoBrowser) { Start-Process $url }
        Write-Host "Video workspace is ready: $url (PID $($backendProcess.Id))"
        exit 0
    }
    $backendProcess.Refresh()
    if ($backendProcess.HasExited) { throw "The backend exited. See $stderrPath for details." }
    Start-Sleep -Milliseconds 300
}
throw "The backend is taking longer to start. See $stderrPath for details, then reopen $url."
