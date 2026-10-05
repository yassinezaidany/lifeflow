<#
.SYNOPSIS
  Start LifeFlow (web server + reminder scheduler) on Windows.

.EXAMPLE
  .\start.ps1                 # development server on http://127.0.0.1:8000
  .\start.ps1 -Prod           # production mode (Waitress, DEBUG off) - HTTP on this machine / local network
  .\start.ps1 -Prod -Port 80 -Listen 0.0.0.0
#>
param(
    [switch]$Prod,
    [int]$Port = 8000,
    [string]$Listen = "127.0.0.1",
    [switch]$NoScheduler,
    [switch]$NoDocker
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Run .\setup.ps1 first." -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force logs | Out-Null
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Port $Port is already in use (LifeFlow already running?). Use -Port to choose another one." -ForegroundColor Red; exit 1
}

if (-not $NoDocker -and (Get-Command docker -ErrorAction SilentlyContinue)) {
    docker compose up -d db | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
        if ((docker inspect -f "{{.State.Health.Status}}" lifeflow-mysql 2>$null) -eq "healthy") { break }
        Start-Sleep 2
    }
}

if ($Prod) {
    $env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
    $env:DEBUG = "False"
    if (-not $env:USE_HTTPS) { $env:USE_HTTPS = "False" }   # plain HTTP on this machine / LAN
    $hosts = @("localhost", "127.0.0.1")
    if ($Listen -eq "0.0.0.0") { $hosts += [System.Net.Dns]::GetHostName(); $hosts += (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "169.*" }).IPAddress }
    $env:ALLOWED_HOSTS = ($hosts | Select-Object -Unique) -join ","
    $env:CSRF_TRUSTED_ORIGINS = (($hosts | Select-Object -Unique) | ForEach-Object { "http://${_}:$Port" }) -join ","
    & $py manage.py migrate --noinput
    & $py manage.py collectstatic --noinput | Out-Null
    if ($LASTEXITCODE) { Write-Host "collectstatic failed - see the error above." -ForegroundColor Red; exit 1 }
}

$scheduler = $null
if (-not $NoScheduler) {
    $scheduler = Start-Process -FilePath $py -ArgumentList "manage.py", "run_scheduler" -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "logs\scheduler.out.log" -RedirectStandardError "logs\scheduler.err.log"
    Write-Host "Reminder scheduler started (PID $($scheduler.Id))"
}

$url = "http://$(if ($Listen -eq '0.0.0.0') { 'localhost' } else { $Listen }):$Port"
Write-Host "LifeFlow -> $url   (Ctrl+C to stop)" -ForegroundColor Green
try {
    if ($Prod) {
        & $py -m waitress --listen "${Listen}:$Port" --threads 8 config.wsgi:application
    } else {
        & $py manage.py runserver "${Listen}:$Port"
    }
} finally {
    if ($scheduler -and -not $scheduler.HasExited) { & taskkill /PID $scheduler.Id /T /F | Out-Null; Write-Host "Scheduler stopped." }
}
