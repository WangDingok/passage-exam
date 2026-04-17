# powershell -ExecutionPolicy Bypass -File .\start.ps1

param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5174
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python).Source

function Write-Banner {
    param([string]$Message)
    Write-Host ""
    Write-Host "=========================================="
    Write-Host $Message
    Write-Host "=========================================="
}

function Stop-IfRunning {
    param([System.Diagnostics.Process]$Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Banner "Clearing ports $BackendPort and $FrontendPort..."
npx --yes kill-port $BackendPort $FrontendPort | Out-Host

Write-Banner "Starting backend on port $BackendPort..."
$backend = Start-Process `
    -FilePath $python `
    -ArgumentList "-m", "src.main", "serve", "--host", "127.0.0.1", "--port", $BackendPort `
    -WorkingDirectory $root `
    -PassThru

Write-Banner "Starting frontend on port $FrontendPort..."
$frontend = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev -- --host 127.0.0.1 --port $FrontendPort" `
    -WorkingDirectory (Join-Path $root "frontend") `
    -PassThru

Write-Host ""
Write-Host "Both servers are starting."
Write-Host "Backend PID:  $($backend.Id)"
Write-Host "Frontend PID: $($frontend.Id)"
Write-Host "Backend:  http://127.0.0.1:$BackendPort"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Press Ctrl+C to stop both processes."

try {
    while ($true) {
        if ($backend.HasExited) {
            throw "Backend process exited with code $($backend.ExitCode)."
        }
        if ($frontend.HasExited) {
            throw "Frontend process exited with code $($frontend.ExitCode)."
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Stop-IfRunning -Process $backend
    Stop-IfRunning -Process $frontend
}
