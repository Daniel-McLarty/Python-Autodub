# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

import os
import sys
from pathlib import Path
from dataclasses import dataclass

# --- PATHING SETUP ---
if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent
    SCRIPT_DIR = ROOT_DIR / "src"
else:
    SCRIPT_DIR = Path(__file__).resolve().parent
    ROOT_DIR = SCRIPT_DIR.parent

MODELS_DIR = ROOT_DIR / "models"
TEMP_DIR = ROOT_DIR / "temp"
OUTPUT_DIR = ROOT_DIR / "output"

MODELS_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# --- AI MODEL REDIRECTION ---
os.environ["HF_HOME"] = str(MODELS_DIR / "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(MODELS_DIR / "huggingface")
os.environ["TORCH_HOME"] = str(MODELS_DIR / "torch")
os.environ["XDG_CACHE_HOME"] = str(MODELS_DIR / "misc_cache")

# --- BINARY PATHING ---
bin_dir = ROOT_DIR / "bin"
if bin_dir.exists() and os.name == 'nt':
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]

# --- GLOBAL CONSTANTS ---
CONFIG_FILE = ROOT_DIR / "ui_config.json"
SUPPORTED_LANGS = ["en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh", "hu", "ko", "ja"]

@dataclass
class PipelineConfig:
    video_file: Path
    source_srt_file: Path
    target_srt_file: Path
    source_lang: str
    target_lang: str
    output_file: Path
    token: str
    max_speakers: int
    confidence: float
    workers: int
    hybrid: bool
    force_clean: bool
