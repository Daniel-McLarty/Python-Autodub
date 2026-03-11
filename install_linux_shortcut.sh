#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

# Get the absolute path of the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Grant execution permissions to your main launcher in src/
chmod +x "$PROJECT_ROOT/src/Launch_UI.sh"

# 2. Create the .desktop file with the user's specific absolute paths
cat <<EOF > "$PROJECT_ROOT/python-autodub.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Python Autodub Studio
Comment=AI-Powered Video Dubbing Pipeline
Exec=$PROJECT_ROOT/src/Launch_UI.sh
Icon=$PROJECT_ROOT/assets/Icon.ico
Terminal=true
Categories=AudioVideo;Audio;Video;
EOF

# 3. Install it to the local user's App Grid (no sudo required)
mkdir -p "$HOME/.local/share/applications"
mv "$PROJECT_ROOT/python-autodub.desktop" "$HOME/.local/share/applications/"
chmod +x "$HOME/.local/share/applications/python-autodub.desktop"

echo "Shortcut successfully added to your application menu!"