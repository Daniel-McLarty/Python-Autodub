<#
.SYNOPSIS
    Auto-bootstrapping launcher for python-autodub (UI)
    Fixed path parsing for uv sync operations.
#>
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

$WorkDir = if ($MyInvocation.MyCommand.Path) { Split-Path $MyInvocation.MyCommand.Path } else { $PWD.Path }
Set-Location $WorkDir

$PYTHON_VERSION = "3.10.19"
$ENV_DIR = "dub_env"
$TARGET_SCRIPT = "src\ui.py"
$REQUIREMENTS = "requirements.txt"

Write-Host "Initializing AutoDub UI Launcher..." -ForegroundColor Cyan

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

# 2. Setup Environment Function (NoNewWindow keeps it in the same console)
function Invoke-UvCommand {
    param([string]$Arguments)
    $OldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    # We use --quiet to reduce the 'ERROR' noise that uv sends to stderr
    Start-Process -FilePath $uvPath -ArgumentList "$Arguments --quiet" -Wait -NoNewWindow

    $ErrorActionPreference = $OldPreference
}

# Install Python
Write-Host "Ensuring Python $PYTHON_VERSION is available..." -ForegroundColor Cyan
Invoke-UvCommand "python install $PYTHON_VERSION"

# Create Virtual Environment
if (!(Test-Path "$ENV_DIR\Scripts\python.exe")) {
    Write-Host "Creating virtual environment '$ENV_DIR'..." -ForegroundColor Cyan
    Invoke-UvCommand "venv $ENV_DIR --python $PYTHON_VERSION"
}

# 3. Sync Dependencies
# Note: We pass the environment directory directly to --python
if (Test-Path $REQUIREMENTS) {
    Write-Host "Syncing dependencies from $REQUIREMENTS..." -ForegroundColor Cyan
    Invoke-UvCommand "pip install -r $REQUIREMENTS --python $ENV_DIR"
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

Write-Host "Application exited. Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
