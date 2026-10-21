param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [switch]$StartCarla,
    [string]$BatchConfig = 'configs/batches/int_01_pilot.yaml'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$carlaRoot = (Resolve-Path (Join-Path $projectRoot '..\..')).Path
$logs = Join-Path $projectRoot 'outputs\v2\launcher'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Python executable missing: $PythonExe" }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if ($StartCarla) {
    $probe = [Net.Sockets.TcpClient]::new()
    try { $open = $probe.ConnectAsync('127.0.0.1', 2000).Wait(1000) -and $probe.Connected } catch { $open = $false } finally { $probe.Dispose() }
    if ($open) { throw 'Port 2000 is occupied; use the existing dedicated server without -StartCarla' }
    $server = Start-Process -FilePath (Join-Path $carlaRoot 'CarlaUE4.exe') -ArgumentList '-RenderOffScreen','-quality-level=Low','-ResX=640','-ResY=360','-nosound','-unattended' -WindowStyle Hidden -WorkingDirectory $carlaRoot -PassThru
    Write-Output "CARLA launcher PID: $($server.Id)"
    $ready = $false
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $probe = [Net.Sockets.TcpClient]::new()
        try { $ready = $probe.ConnectAsync('127.0.0.1',2000).Wait(1000) -and $probe.Connected } catch { $ready = $false } finally { $probe.Dispose() }
        if ($ready) { break }
        Start-Sleep -Milliseconds 1000
    }
    if (-not $ready) { throw 'CARLA did not open port 2000 within 90 seconds' }
}
$stdout = Join-Path $logs "$stamp.stdout.log"
$stderr = Join-Path $logs "$stamp.stderr.log"
$job = Start-Process -FilePath $PythonExe -ArgumentList '-u','-m','vn_traffic_risk','run-batch','--config',$BatchConfig -WindowStyle Hidden -WorkingDirectory $projectRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Write-Output "Batch PID: $($job.Id)"
Write-Output "stdout: $stdout"
Write-Output "stderr: $stderr"
