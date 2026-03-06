<#
.SYNOPSIS
    Auto-bootstrapping launcher for python-autodub (Tester)
    Optimized for uv compatibility and clean logging.
#>
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

# Resolve directory for ps2exe compatibility
$WorkDir = if ($MyInvocation.MyCommand.Path) { Split-Path $MyInvocation.MyCommand.Path } else { $PWD.Path }
Set-Location $WorkDir

# Configuration
$PYTHON_VERSION = "3.10.19"
$ENV_DIR = "dub_env"
$TARGET_SCRIPT = "src\test_env.py"
$REQUIREMENTS = "requirements.txt"

Write-Host "Initializing AutoDub Tester Launcher..." -ForegroundColor Cyan

# 1. Locate or Install 'uv'
$uvPath = "uv"
if (!(Get-Command "uv" -ErrorAction SilentlyContinue)) {
    $localUv = "$env:USERPROFILE\.local\bin\uv.exe"
    if (Test-Path $localUv) {
        $uvPath = $localUv
    } else {
        Write-Host "uv not found. Installing..." -ForegroundColor Yellow
        Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" | Invoke-Expression
        $uvPath = $localUv
    }
}

# 2. Setup Environment Function (Handles the stderr 'noise' from uv)
function Invoke-UvCommand {
    param([string]$Arguments)
    $OldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    # Use --quiet to keep the console focused on your app's logs
    Start-Process -FilePath $uvPath -ArgumentList "$Arguments --quiet" -Wait -NoNewWindow

    $ErrorActionPreference = $OldPreference
}

# Install Python 3.10
Write-Host "Ensuring Python $PYTHON_VERSION is available..." -ForegroundColor Cyan
Invoke-UvCommand "python install $PYTHON_VERSION"

# Create Virtual Environment
if (!(Test-Path "$ENV_DIR\Scripts\python.exe")) {
    Write-Host "Creating virtual environment '$ENV_DIR'..." -ForegroundColor Cyan
    Invoke-UvCommand "venv $ENV_DIR --python $PYTHON_VERSION"
}

# 3. Sync Dependencies
# Using the directory name directly to prevent path-parsing errors
if (Test-Path $REQUIREMENTS) {
    Write-Host "Syncing dependencies from $REQUIREMENTS..." -ForegroundColor Cyan
    Invoke-UvCommand "pip install -r $REQUIREMENTS --python $ENV_DIR --extra-index-url https://download.pytorch.org/whl/cu121 --index-strategy unsafe-best-match"
}

# 4. Run Target Script
$envPython = "$WorkDir\$ENV_DIR\Scripts\python.exe"
if (Test-Path $TARGET_SCRIPT) {
    Write-Host "`nLaunching $TARGET_SCRIPT..." -ForegroundColor Green
    Write-Host "=================================================="
    & $envPython $TARGET_SCRIPT
    Write-Host "=================================================="
} else {
    Write-Host "ERROR: Could not find $TARGET_SCRIPT" -ForegroundColor Red
}

Write-Host "Tester exited. Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
