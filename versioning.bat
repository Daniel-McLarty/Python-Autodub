@echo off
echo This Source Code Form is subject to the terms of the Mozilla Public
echo License, v. 2.0. If a copy of the MPL was not distributed with this
echo file, You can obtain one at https://mozilla.org/MPL/2.0/.
echo Copyright (C) Daniel McLarty 2026
echo.
echo [1/3] Cleaning up old files...
if exist requirements.txt del requirements.txt

echo [2/3] Freezing current environment to base.txt...
uv pip freeze --python dub_env\Scripts\python.exe > base.txt

echo [3/3] Compiling final requirements.txt (No Hashes)...
uv pip compile base.txt --extra-index-url https://download.pytorch.org/whl/cu121 --index-strategy unsafe-best-match -o requirements.txt
del base.txt

echo.
echo ===================================================
echo Done!
echo Deployment lock saved to: requirements.txt
echo ===================================================
pause