<#
.SYNOPSIS
  One-time installation of LifeFlow on Windows.

.DESCRIPTION
  Creates the virtual environment, installs dependencies, writes .env (random SECRET_KEY),
  starts MySQL in Docker, applies migrations, enables Web Push and checks the installation.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\setup.ps1          # standard install
  powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Demo    # + demo accounts (demo / LifeFlow-demo1)
  powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Dev     # + test / QA tools
#>
param(
    [switch]$Demo,
    [switch]$Dev,
    [switch]$NoDocker   # use your own MySQL server (configure DB_* in .env first)
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }

Step "Checking prerequisites"
$python = $null
foreach ($candidate in @("py -3.11", "py -3", "python")) {
    try {
        $version = & cmd /c "$candidate --version" 2>$null
        if ($LASTEXITCODE -eq 0 -and $version -match "Python 3\.(1[1-9]|[2-9]\d)") { $python = $candidate; break }
    } catch {}
}
if (-not $python) { Fail "Python 3.11+ is required (https://www.python.org/downloads/)." }
Write-Host "Python: $version ($python)"
if (-not $NoDocker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker Desktop is required (or run with -NoDocker and your own MySQL)." }
    Write-Host "Docker: $((docker --version) -join ' ')"
}

Step "Creating the virtual environment"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & cmd /c "$python -m venv .venv"; if ($LASTEXITCODE) { Fail "venv creation failed" } }
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE) { Fail "pip install failed" }
if ($Dev) { & $py -m pip install -r requirements-dev.txt --quiet }

Step "Configuration (.env)"
if (-not (Test-Path ".env")) {
    $secret = & $py -c "import secrets; print(secrets.token_urlsafe(50))"
    $content = (Get-Content ".env.example" -Raw -Encoding UTF8).Replace("change-me-to-a-long-random-string", $secret)
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot ".env"), $content, (New-Object Text.UTF8Encoding $false))
    Write-Host ".env created with a random SECRET_KEY"
} else { Write-Host ".env already exists - kept" }

if (-not $NoDocker) {
    Step "Starting MySQL (Docker)"
    docker compose up -d db
    if ($LASTEXITCODE) { Fail "docker compose failed - is Docker Desktop running?" }
    Write-Host -NoNewline "Waiting for MySQL"
    for ($i = 0; $i -lt 60; $i++) {
        $state = docker inspect -f "{{.State.Health.Status}}" lifeflow-mysql 2>$null
        if ($state -eq "healthy") { break }
        Write-Host -NoNewline "."; Start-Sleep 2
    }
    Write-Host ""
    if ($state -ne "healthy") { Fail "MySQL did not become healthy" }
}

Step "Database"
& $py manage.py migrate --noinput
if ($LASTEXITCODE) { Fail "migrations failed - check DB_* in .env" }
& $py manage.py seed_templates
& $py manage.py i18n compile

Step "Web Push keys"
if (-not (Select-String -Path ".env" -Pattern "^VAPID_PRIVATE_KEY=.+" -Quiet)) { & $py manage.py generate_vapid_keys --write } else { Write-Host "already configured" }

if ($Demo) {
    Step "Demo data"
    & $py manage.py seed_demo --reset
}

Step "Installation check"
& $py manage.py doctor

Write-Host "`nLifeFlow is installed." -ForegroundColor Green
Write-Host "  Start it:            .\start.ps1            (development, http://127.0.0.1:8000)"
Write-Host "  Production mode:     .\start.ps1 -Prod"
Write-Host "  Administrator:       .venv\Scripts\python manage.py createsuperuser"
if ($Demo) { Write-Host "  Demo account:        demo / LifeFlow-demo1" }
