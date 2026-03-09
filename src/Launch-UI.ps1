<#
.SYNOPSIS
    This Source Code Form is subject to the terms of the Mozilla Public
    License, v. 2.0. If a copy of the MPL was not distributed with this
    file, You can obtain one at https://mozilla.org/MPL/2.0/.
    Copyright (C) Daniel McLarty 2026

    Modernized UV Launcher for python-autodub
#>
$StartTime = [datetime]::Now
$ErrorActionPreference = "Continue"
$ProgressPreference = 'SilentlyContinue'

# Set working directory to the script's location
$WorkDir = if ($MyInvocation.MyCommand.Path) { Split-Path $MyInvocation.MyCommand.Path } else { $PWD.Path }
Set-Location $WorkDir

# Configuration
$TARGET_SCRIPT = "$WorkDir\src\ui.py"
$BIN_FOLDER = "$WorkDir\bin"

Write-Host "--- Python Autodub Launcher ---" -ForegroundColor Cyan

# 1. Locate or install 'uv'
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

# 2. Native execution function (Sanitizes streams and handles exit codes)
function Invoke-NativeCommand {
    param(
        [string]$Executable,
        [string]$Arguments,
        [switch]$SkipErrorCheck
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Executable
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $false

    $proc = [System.Diagnostics.Process]::Start($psi)

    # Stream errors to host to avoid red block formatting in PS
    while (!$proc.StandardError.EndOfStream) {
        $line = $proc.StandardError.ReadLine()
        if ($line) { Write-Host $line }
    }

    $proc.WaitForExit()

    if (-not $SkipErrorCheck -and $proc.ExitCode -ne 0) {
        Write-Host "`n[-] Process failed with exit code $($proc.ExitCode)" -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit $proc.ExitCode
    }
}

# 3. Update UV and Sync Environment
Write-Host "[+] Updating uv..." -ForegroundColor Gray
Invoke-NativeCommand -Executable $uvPath -Arguments "self update" -SkipErrorCheck

Write-Host "[+] Synchronizing dependencies with CUDA 12.1 support..." -ForegroundColor Cyan
# Added --extra cu121 here
Invoke-NativeCommand -Executable $uvPath -Arguments "sync --extra cu121"

# 4. Launch the UI Application
if (Test-Path $TARGET_SCRIPT) {
    if (Test-Path $BIN_FOLDER) {
        $env:PATH = "$BIN_FOLDER;" + $env:PATH
    }

    $TotalSetupTime = [Math]::Round(([datetime]::Now - $StartTime).TotalSeconds, 2)
    Write-Host "[!] Environment ready in $TotalSetupTime seconds." -ForegroundColor Gray
    Write-Host "`n[!] Launching UI with CUDA 12.1 enabled..." -ForegroundColor Green
    Write-Host "--------------------------------------------------"

    # Added --extra cu121 here as well to ensure the runtime environment matches
    Invoke-NativeCommand -Executable $uvPath -Arguments "run --extra cu121 $TARGET_SCRIPT"

    Write-Host "--------------------------------------------------"
} else {
    Write-Host "[X] ERROR: Could not find $TARGET_SCRIPT" -ForegroundColor Red
}

Write-Host "`nApplication exited. Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
