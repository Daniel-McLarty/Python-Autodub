# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

import os
import sys
import warnings

# --- SILENCE WARNINGS ---
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# --- PATHING & ENV SETUP ---
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    # Assuming test_env.py is in /src/
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- MODEL REDIRECTION ---
MODELS_DIR = os.path.join(ROOT_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

os.environ["HF_HOME"] = os.path.join(MODELS_DIR, "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(MODELS_DIR, "huggingface")
os.environ["TORCH_HOME"] = os.path.join(MODELS_DIR, "torch")
os.environ["XDG_CACHE_HOME"] = os.path.join(MODELS_DIR, "misc_cache")
os.environ["TTS_HOME"] = os.path.join(MODELS_DIR, "tts")

# --- BINARY PATHING (FFMPEG) ---
bin_dir = os.path.join(ROOT_DIR, "bin")
if os.path.exists(bin_dir) and os.name == 'nt':
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]

# --- IMPORTS ---
import subprocess
import argparse
import torch

# --- CLI ARGUMENTS ---
parser = argparse.ArgumentParser(description="Test AI Auto-Dubbing Environment")
parser.add_argument("--hf-token", required=True, help="Your Hugging Face Token")
args = parser.parse_args()

HF_TOKEN = args.hf_token

print("--- COMMENCING PRE-FLIGHT CHECKS ---\n")

# 1. Check FFmpeg
print("1. Testing FFmpeg linkage...")
try:
    subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from pydub import AudioSegment
    print("   -> SUCCESS: FFmpeg and Pydub are locked and loaded.")
except Exception as e:
    print(f"   -> ERROR: FFmpeg/Pydub failed! {e}")

# 2. Check CUDA & PyTorch
print("\n2. Testing PyTorch CUDA connection...")
if torch.cuda.is_available():
    print(f"   -> SUCCESS: CUDA is active. GPU: {torch.cuda.get_device_name(0)}")
else:
    print("   -> ERROR: PyTorch cannot see your GPU! It is defaulting to CPU.")

# 3. Check Pyannote & Token
print("\n3. Testing Pyannote & Hugging Face Token...")
try:
    from pyannote.audio import Pipeline
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=HF_TOKEN)
    if pipeline is None:
        print("   -> ERROR: Token is valid, but you haven't accepted the conditions on the Hugging Face website!")
    else:
        print("   -> SUCCESS: Pyannote authenticated and loaded.")
except Exception as e:
    print(f"   -> ERROR: Pyannote failed to authenticate or load! {e}")

# 4. Check XTTSv2
print("\n4. Testing XTTSv2 Model Loading...")
try:
    from TTS.api import TTS
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
    print("   -> SUCCESS: XTTSv2 successfully loaded into VRAM.")
except Exception as e:
    print(f"   -> ERROR: XTTSv2 failed to load! {e}")

print("\n--- ALL CHECKS COMPLETED ---")
