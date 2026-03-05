#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

echo "==================================================="
echo "AI Auto-Dubbing Studio - Linux Setup"
echo "==================================================="

echo -e "\n[1/4] Checking Python installation..."
if ! command -v python3 &> /dev/null
then
    echo "ERROR: python3 could not be found. Please install Python 3.9+."
    exit 1
fi

echo -e "\n[2/4] Creating virtual environment (dub_env)..."
python3 -m venv dub_env

echo -e "\n[3/4] Activating virtual environment and installing requirements..."
source dub_env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "\n[4/4] Checking FFmpeg installation..."
if ! command -v ffmpeg &> /dev/null
then
    echo "WARNING: FFmpeg is not installed!"
    echo "You MUST install FFmpeg for this script to work."
    echo "Run: sudo apt install ffmpeg"
else
    echo "FFmpeg is installed!"
fi

echo -e "\n==================================================="
echo "Setup Complete!"
echo "To start the environment, type: source dub_env/bin/activate"
echo "To launch the UI, type: python src/ui.py"
echo "==================================================="
