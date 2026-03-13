<#
.SYNOPSIS
    This Source Code Form is subject to the terms of the Mozilla Public
    License, v. 2.0. If a copy of the MPL was not distributed with this
    file, You can obtain one at https://mozilla.org/MPL/2.0/.
    Copyright (C) Daniel McLarty 2026

    Modernized UV Launcher for python-autodub with MSVC Auto-Install
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

# 1. MSVC Build Tools Detection & Installation
function Test-MSVCBuildTools {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $false }

    $tools = & $vswhere -latest -products * -version "[17.0,18.0)" -requires Microsoft.VisualStudio.Workload.VCTools -property installationPath

    # Check if we actually got a path string back
    if ($null -ne $tools -and $tools.Trim() -ne "") {
        $shortPath = Split-Path $tools -Leaf
        Write-Host "[+] Found MSVC environment in: $shortPath" -ForegroundColor Gray
        return $true
    }

    return $false
}

function Install-MSVCBuildTools {
    Write-Host "[*] Microsoft Visual C++ Build Tools not found." -ForegroundColor Yellow
    Write-Host "[*] Downloading official installer (this may take a while)..." -ForegroundColor Cyan

    $installerUrl = "https://aka.ms/vs/17/release/vs_buildtools.exe"
    $installerPath = "$env:TEMP\vs_buildtools.exe"

    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

    Write-Host "[*] Installing MSVC Build Tools. Please wait..." -ForegroundColor Cyan
    Write-Host "[!] A Windows User Account Control (UAC) prompt will appear. Please click 'Yes'." -ForegroundColor Yellow

    # Run the installer passively (shows progress bar, requires no clicks) with UAC elevation
    $arguments = "--passive --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru -Verb RunAs

    if ($process.ExitCode -eq 0 -or $process.ExitCode -eq 3010) {
        Write-Host "[+] MSVC Build Tools installed successfully!" -ForegroundColor Green
        if ($process.ExitCode -eq 3010) {
            Write-Host "[!] A system reboot is recommended by the installer, but we will try to proceed." -ForegroundColor Yellow
        }
    } else {
        Write-Host "[-] Installation failed with exit code $($process.ExitCode)." -ForegroundColor Red
        Write-Host "[-] Please install manually: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit $process.ExitCode
    }

    Remove-Item $installerPath -ErrorAction SilentlyContinue
}

Write-Host "[+] Checking C++ Build Environment..." -ForegroundColor Gray
if (-not (Test-MSVCBuildTools)) {
    Install-MSVCBuildTools
} else {
    Write-Host "[+] MSVC Build Tools are already installed." -ForegroundColor Green
}

# 2. Locate or install 'uv'
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

# 3. Native execution function (Sanitizes streams and handles exit codes)
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

# 4. Update UV and Sync Environment
Write-Host "[+] Updating uv..." -ForegroundColor Gray
Invoke-NativeCommand -Executable $uvPath -Arguments "self update" -SkipErrorCheck

Write-Host "[+] Synchronizing dependencies with CUDA 12.8 support..." -ForegroundColor Cyan
Invoke-NativeCommand -Executable $uvPath -Arguments "sync --extra cu128"

# 5. Launch the UI Application
if (Test-Path $TARGET_SCRIPT) {
    if (Test-Path $BIN_FOLDER) {
        $env:PATH = "$BIN_FOLDER;" + $env:PATH
    }

    $TotalSetupTime = [Math]::Round(([datetime]::Now - $StartTime).TotalSeconds, 2)
    Write-Host "[!] Environment ready in $TotalSetupTime seconds." -ForegroundColor Gray
    Write-Host "`n[!] Launching UI with CUDA 12.8 enabled..." -ForegroundColor Green
    Write-Host "`n[!] Note: The first launch may take a moment as the application initializes and compiles necessary components." -ForegroundColor Yellow
    Write-Host "--------------------------------------------------"

    Invoke-NativeCommand -Executable $uvPath -Arguments "run --extra cu128 $TARGET_SCRIPT"

    Write-Host "--------------------------------------------------"
} else {
    Write-Host "[X] ERROR: Could not find $TARGET_SCRIPT" -ForegroundColor Red
}

Write-Host "`nApplication exited. Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
