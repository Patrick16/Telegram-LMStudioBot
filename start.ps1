# LMStudioBot launcher (PowerShell)
# Mirrors launch.bat: checks Python, creates .venv, installs requirements,
# checks .env and starts the bot with `python -m src.bot.main`.

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Write-Step($text) { Write-Host "`n$text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "[OK] $text" -ForegroundColor Green }
function Exit-WithError($text) {
    Write-Host "[ERROR] $text" -ForegroundColor Red
    Read-Host 'Press Enter to exit' | Out-Null
    exit 1
}

Write-Host '========================================' -ForegroundColor DarkGray
Write-Host ' LMStudioBot - PowerShell Launcher'        -ForegroundColor White
Write-Host '========================================' -ForegroundColor DarkGray

# 1. Python
Write-Step '[1/5] Checking Python installation...'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Exit-WithError 'Python is not installed or not in PATH. Install Python 3.11+ from python.org'
}
$pyVersion = & python --version 2>&1
Write-Ok "$pyVersion found"

# 2. Virtual environment
Write-Step '[2/5] Setting up virtual environment...'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating .venv...'
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Exit-WithError 'Failed to create virtual environment' }
    Write-Ok 'Virtual environment created'
} else {
    Write-Ok 'Virtual environment already exists'
}

# 3. Activate (dot-source the activation script so PATH points to the venv)
Write-Step '[3/5] Activating virtual environment...'
$activate = Join-Path $PSScriptRoot '.venv\Scripts\Activate.ps1'
. $activate
Write-Ok 'Virtual environment activated'

# 4. Dependencies
Write-Step '[4/5] Installing dependencies...'
& python -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Exit-WithError 'Failed to upgrade pip' }
& python -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Exit-WithError 'Failed to install dependencies. Check requirements.txt' }
Write-Ok 'Dependencies installed'

# 5. Configuration
Write-Step '[5/5] Checking configuration...'
if (-not (Test-Path (Join-Path $PSScriptRoot '.env'))) {
    Write-Host ''
    Write-Host '[WARNING] .env file not found!' -ForegroundColor Yellow
    Write-Host 'Create it (copy .env.example) with at least:'
    Write-Host '  TELEGRAM_BOT_TOKEN=your_bot_token_here'
    Write-Host '  TELEGRAM_OWNER_ID=your_telegram_id'
    Write-Host '  LMS_HOST=localhost'
    Write-Host '  LMS_PORT=1234'
    Write-Host '  LOG_LEVEL=INFO'
    Read-Host 'Press Enter to exit' | Out-Null
    exit 1
}
Write-Ok 'Configuration file (.env) found'

# Launch
Write-Host ''
Write-Host '========================================' -ForegroundColor DarkGray
Write-Host ' Launching LMStudioBot...'                 -ForegroundColor White
Write-Host '========================================' -ForegroundColor DarkGray
Write-Host ''

& python -m src.bot.main
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host ''
    Exit-WithError "Bot exited with code $exitCode"
}
