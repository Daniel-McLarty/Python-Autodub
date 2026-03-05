@echo off
echo This Source Code Form is subject to the terms of the Mozilla Public
echo License, v. 2.0. If a copy of the MPL was not distributed with this
echo file, You can obtain one at https://mozilla.org/MPL/2.0/.
echo
echo ===================================================
echo AI Auto-Dubbing Studio - Windows Setup
echo ===================================================

echo.
echo [1/4] Checking Python installation...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH.
    pause
    exit /b
)

echo.
echo [2/4] Creating virtual environment (dub_env)...
python -m venv dub_env

echo.
echo [3/4] Activating virtual environment and installing requirements...
call dub_env\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo [4/4] Checking FFmpeg installation...
ffmpeg -version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo WARNING: FFmpeg is not detected in your PATH!
    echo You MUST install FFmpeg for this script to work.
    echo Download it from https://github.com/BtbN/FFmpeg-Builds/releases
    echo and add the 'bin' folder to your Windows Environment Variables.
) ELSE (
    echo FFmpeg is installed!
)

echo.
echo ===================================================
echo Setup Complete!
echo To start the environment, type: dub_env\Scripts\activate
echo To launch the UI, type: python src/ui.py
echo ===================================================
pause
