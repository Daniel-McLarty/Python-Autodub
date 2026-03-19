@echo off
echo This Source Code Form is subject to the terms of the Mozilla Public
echo License, v. 2.0. If a copy of the MPL was not distributed with this
echo file, You can obtain one at https://mozilla.org/MPL/2.0/.
echo Copyright (C) Daniel McLarty 2026
echo.
echo ===================================================
echo AI Auto-Dubbing Studio - Windows Setup
echo ===================================================

echo.
echo [1/3] Checking Python installation...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH.
    pause
    exit /b
)

echo.
echo [2/3] Creating virtual environment (dub_env)...
python -m venv dub_env

echo.
echo [3/3] Activating virtual environment and installing requirements...
call dub_env\Scripts\activate
python -m pip install --upgrade pip

pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121

echo.
echo ===================================================
echo Setup Complete!
echo To start the environment, type: dub_env\Scripts\activate
echo To launch the UI, type: python src/ui.py
echo ===================================================
pause
