<#
.SYNOPSIS
    This Source Code Form is subject to the terms of the Mozilla Public
    License, v. 2.0. If a copy of the MPL was not distributed with this
    file, You can obtain one at https://mozilla.org/MPL/2.0/.
    Copyright (C) Daniel McLarty 2026

    Auto-bootstrapping launcher for python-autodub (UI)
    Fix: Updated 'self-update' to 'self update' and added fault tolerance.
#>
$StartTime = [datetime]::Now
$ErrorActionPreference = "Continue"
$ProgressPreference = 'SilentlyContinue'

# Set working directory to the script's location
$WorkDir = if ($MyInvocation.MyCommand.Path) { Split-Path $MyInvocation.MyCommand.Path } else { $PWD.Path }
Set-Location $WorkDir

# Configuration
$PYTHON_VERSION = "3.10.19"
$ENV_DIR = "dub_env"
$TARGET_SCRIPT = "src\ui.py"
$REQUIREMENTS = "requirements.txt"
$HASH_FILE = ".req_hash"
$BIN_FOLDER = "$WorkDir\bin"

Write-Host "--- AutoDub UI Launcher ---" -ForegroundColor Cyan

# 1. Locate or install the 'uv' package manager
$uvPath = "uv"
if (!(Get-Command "uv" -ErrorAction SilentlyContinue)) {
    $localUv = "$env:USERPROFILE\.local\bin\uv.exe"
    if (Test-Path $localUv) {
        $uvPath = $localUv
    } else {
        Write-Host "[!] uv not found. Installing..." -ForegroundColor Yellow
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $uvPath = $localUv
    }
}

# 2. Native execution function to sanitize output streams
function Invoke-NativeCommand {
    param(
        [string]$Executable,
        [string]$Arguments,
        [switch]$SkipErrorCheck
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Executable

    # Enable colors for uv specifically
    if ($Executable -like "*uv*") {
        $psi.Arguments = "$Arguments --color always"
    } else {
        $psi.Arguments = $Arguments
    }

    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $false

    # Start the process
    $proc = [System.Diagnostics.Process]::Start($psi)

    # Read the error stream and write to host as information to avoid PowerShell "ERROR:" prefixes
    while (!$proc.StandardError.EndOfStream) {
        $line = $proc.StandardError.ReadLine()
        if ($line) { Write-Host $line }
    }

    $proc.WaitForExit()

    # Handle non-zero exit codes unless SkipErrorCheck is enabled
    if (-not $SkipErrorCheck -and $proc.ExitCode -ne 0) {
        Write-Host "`n[-] Process failed with exit code $($proc.ExitCode)" -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit $proc.ExitCode
    }
}

# 3. Perform self-updates and environment setup
Write-Host "[+] Checking for uv updates..." -ForegroundColor Gray
Invoke-NativeCommand -Executable $uvPath -Arguments "self update" -SkipErrorCheck

Write-Host "[+] Ensuring Python $PYTHON_VERSION..." -ForegroundColor Cyan
Invoke-NativeCommand -Executable $uvPath -Arguments "python install $PYTHON_VERSION"

if (!(Test-Path "$ENV_DIR\Scripts\python.exe")) {
    Write-Host "[+] Creating virtual environment..." -ForegroundColor Cyan
    Invoke-NativeCommand -Executable $uvPath -Arguments "venv $ENV_DIR --python $PYTHON_VERSION"
}

# 4. Dependency Synchronization with Hash Checking
if (Test-Path $REQUIREMENTS) {
    # If the environment folder is missing, force a re-sync
    if (!(Test-Path $ENV_DIR)) { Remove-Item $HASH_FILE -ErrorAction SilentlyContinue }

    $currentHash = (Get-FileHash $REQUIREMENTS).Hash
    $oldHash = if (Test-Path $HASH_FILE) { Get-Content $HASH_FILE } else { "" }

    if ($currentHash -ne $oldHash) {
        Write-Host "[+] Requirements changed. Syncing dependencies..." -ForegroundColor Cyan
        Invoke-NativeCommand -Executable $uvPath -Arguments "pip install -r $REQUIREMENTS --python $ENV_DIR --extra-index-url https://download.pytorch.org/whl/cu121 --index-strategy unsafe-best-match"
        $currentHash | Out-File $HASH_FILE -NoNewline
    } else {
        Write-Host "[+] Dependencies up to date." -ForegroundColor Green
    }
}

# 5. Launch the UI Application
$envPython = "$WorkDir\$ENV_DIR\Scripts\python.exe"
if (Test-Path $TARGET_SCRIPT) {
    # Add local bin to PATH to ensure bundled binaries (like FFmpeg) take priority
    if (Test-Path $BIN_FOLDER) {
        $env:PATH = "$BIN_FOLDER;" + $env:PATH
    }

    $TotalSetupTime = [Math]::Round(([datetime]::Now - $StartTime).TotalSeconds, 2)
    Write-Host "[!] Setup took $TotalSetupTime seconds." -ForegroundColor Gray
    Write-Host "`n[!] Launching UI..." -ForegroundColor Green
    Write-Host "--------------------------------------------------"

    # Run the application through the sanitized stream handler
    Invoke-NativeCommand -Executable $envPython -Arguments "`"$TARGET_SCRIPT`""

    Write-Host "--------------------------------------------------"
} else {
    Write-Host "[X] ERROR: Could not find $TARGET_SCRIPT" -ForegroundColor Red
}

Write-Host "`nApplication exited. Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
