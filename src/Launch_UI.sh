#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

# Modernized UV Launcher for python-autodub with Distro-Agnostic C++ Check

START_TIME=$(date +%s)

# Colors for terminal output
CYAN='\033[0;36m'
GRAY='\033[0;90m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}--- Python Autodub Launcher ---${NC}"

# Set directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# IMPORTANT: We must cd into the project root so 'uv' finds pyproject.toml
cd "$PROJECT_ROOT" || exit 1

# Configuration
TARGET_SCRIPT="$SCRIPT_DIR/ui.py"
BIN_FOLDER="$PROJECT_ROOT/bin"

# 1. C++ Build Tools Detection
echo -e "${GRAY}[+] Checking C++ Build Environment...${NC}"
if ! command -v gcc >/dev/null 2>&1 && ! command -v clang >/dev/null 2>&1; then
    echo -e "${YELLOW}[*] A C++ compiler (gcc or clang) was not found.${NC}"
    echo -e "${RED}[-] Please install your system's build tools manually using your package manager:${NC}"
    echo -e "${GRAY}    Debian/Ubuntu : sudo apt install build-essential${NC}"
    echo -e "${GRAY}    Fedora/RHEL   : sudo dnf groupinstall \"C Development Tools and Libraries\"${NC}"
    echo -e "${GRAY}    Arch Linux    : sudo pacman -S base-devel${NC}"
    echo ""
    read -r -p "Press Enter to exit..."
    exit 1
else
    COMPILER=$(command -v gcc >/dev/null 2>&1 && echo "gcc" || echo "clang")
    echo -e "${GREEN}[+] C++ Build Tools ($COMPILER) are already installed.${NC}"
fi

# 2. Locate or install 'uv'
UV_PATH="uv"
if ! command -v uv >/dev/null 2>&1; then
    if [ -f "$HOME/.local/bin/uv" ]; then
        UV_PATH="$HOME/.local/bin/uv"
    else
        echo -e "${YELLOW}[!] uv not found. Installing into user-space...${NC}"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        UV_PATH="$HOME/.local/bin/uv"
    fi
fi

# 3. Update UV and Sync Environment
echo -e "${GRAY}[+] Updating uv...${NC}"
"$UV_PATH" self update || true

echo -e "${CYAN}[+] Synchronizing dependencies with CUDA 12.1 support...${NC}"
if ! "$UV_PATH" sync --extra cu128; then
    echo -e "\n${RED}[-] Process failed during sync.${NC}"
    read -r -p "Press Enter to exit..."
    exit 1
fi

# 4. Launch the UI Application
if [ -f "$TARGET_SCRIPT" ]; then
    if [ -d "$BIN_FOLDER" ]; then
        export PATH="$BIN_FOLDER:$PATH"
    fi

    END_TIME=$(date +%s)
    TOTAL_TIME=$((END_TIME - START_TIME))

    echo -e "${GRAY}[!] Environment ready in ${TOTAL_TIME} seconds.${NC}"
    echo -e "\n${GREEN}[!] Launching UI with CUDA 12.1 enabled...${NC}"
    echo "--------------------------------------------------"

    if ! "$UV_PATH" run --extra cu128 "$TARGET_SCRIPT"; then
        echo -e "\n${RED}[-] Application crashed or exited with an error.${NC}"
        read -r -p "Press Enter to exit..."
        exit 1
    fi

    echo "--------------------------------------------------"
else
    echo -e "${RED}[X] ERROR: Could not find $TARGET_SCRIPT${NC}"
fi

echo -e "\nApplication exited. Press Enter to close..."
read -r
