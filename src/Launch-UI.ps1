<#
.SYNOPSIS
    This Source Code Form is subject to the terms of the Mozilla Public
    License, v. 2.0. If a copy of the MPL was not distributed with this
    file, You can obtain one at https://mozilla.org/MPL/2.0/.
    Copyright (C) Daniel McLarty 2026

    Auto-bootstrapping launcher for python-autodub (UI)
    Fix: Updated 'self-update' to 'self update' and added fault tolerance.
#>
$ErrorActionPreference = "Continue"
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

$WorkDir = if ($MyInvocation.MyCommand.Path) { Split-Path $MyInvocation.MyCommand.Path } else { $PWD.Path }
Set-Location $WorkDir

$PYTHON_VERSION = "3.10.19"
$ENV_DIR = "dub_env"
$TARGET_SCRIPT = "src\ui.py"
$REQUIREMENTS = "requirements.txt"
$HASH_FILE = ".req_hash"

Write-Host "--- AutoDub UI Launcher ---" -ForegroundColor Cyan

# 1. Locate or Install 'uv'
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

# 2. Setup Environment Function
function Invoke-UvCommand {
    param(
        [string[]]$Arguments,
        [switch]$SkipErrorCheck
    )

    $cmd = if ($uvPath -eq "uv") { "uv" } else { "$uvPath" }

    # 2>&1 merges streams
    # % { "$_" } converts the resulting objects into plain strings,
    # which kills the "At line:49 char:5" PowerShell metadata spam.
    & $cmd @Arguments --color always 2>&1 | ForEach-Object { "$_" }

    if (-not $SkipErrorCheck -and $LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
        Write-Host "`n[-] ACTUAL FAILURE: Process exited with code $LASTEXITCODE" -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit $LASTEXITCODE
    }
}

# 0. Self-Update uv
Write-Host "[+] Checking for uv updates..." -ForegroundColor Gray
Invoke-UvCommand -Arguments @("self", "update") -SkipErrorCheck

# 1. Install Python
Write-Host "[+] Ensuring Python $PYTHON_VERSION..." -ForegroundColor Cyan
Invoke-UvCommand @("python", "install", $PYTHON_VERSION)

# 2. Create Virtual Environment
if (!(Test-Path "$ENV_DIR\Scripts\python.exe")) {
    Write-Host "[+] Creating virtual environment..." -ForegroundColor Cyan
    Invoke-UvCommand @("venv", $ENV_DIR, "--python", $PYTHON_VERSION)
}

# 3. Sync Dependencies (with Hash Check)
if (Test-Path $REQUIREMENTS) {
    # If the environment folder was deleted, force a hash mismatch to trigger a re-sync
    if (!(Test-Path $ENV_DIR)) { Remove-Item $HASH_FILE -ErrorAction SilentlyContinue }

    $currentHash = (Get-FileHash $REQUIREMENTS).Hash
    $oldHash = if (Test-Path $HASH_FILE) { Get-Content $HASH_FILE } else { "" }

    if ($currentHash -ne $oldHash) {
        Write-Host "[+] Syncing dependencies..." -ForegroundColor Cyan
        Invoke-UvCommand @(
            "pip", "install", "-r", $REQUIREMENTS,
            "--python", $ENV_DIR,
            "--extra-index-url", "https://download.pytorch.org/whl/cu121",
            "--index-strategy", "unsafe-best-match"
        )
        $currentHash | Out-File $HASH_FILE -NoNewline
    } else {
        Write-Host "[+] Dependencies up to date." -ForegroundColor Green
    }
}

# 4. Run Target Script
$envPython = "$WorkDir\$ENV_DIR\Scripts\python.exe"
if (Test-Path $TARGET_SCRIPT) {
    Write-Host "`n[!] Launching $TARGET_SCRIPT..." -ForegroundColor Green
    Write-Host "--------------------------------------------------"
    # We use direct execution here (no redirection) so the Python UI's
    # own logs flow to the console normally without modification.
    & $envPython $TARGET_SCRIPT
    Write-Host "--------------------------------------------------"
} else {
    Write-Host "[X] ERROR: Could not find $TARGET_SCRIPT" -ForegroundColor Red
}

Write-Host "`nApplication exited. Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
