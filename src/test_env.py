# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import subprocess
import torch
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

HF_TOKEN = "hf_" # Put your token here!

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
print("If you see 4 SUCCESS messages above, your environment is bulletproof. You are cleared to run the main script!")
