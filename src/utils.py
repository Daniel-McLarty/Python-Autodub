# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

import hashlib
import sys
import re
import numpy as np
import librosa
import subprocess
import logging
import time
from pathlib import Path

def get_file_hash(filepath: Path) -> str:
    if not filepath or not filepath.exists(): return ""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def estimate_gender_from_pitch(audio_data, sr):
    try:
        # If stereo, average to mono
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)

        # Normalize volume for pitch detection
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            samples = audio_data / max_val
        else:
            return "male"

        f0 = librosa.yin(samples, fmin=75, fmax=300, sr=sr)
        valid_f0 = f0[~np.isnan(f0)]

        if len(valid_f0) == 0:
            return "male"

        median_pitch = np.median(valid_f0)
        return "female" if median_pitch >= 165 else "male"
    except Exception as e:
        print(f"Pitch detection failed: {e}")
        return "male"

def run_and_log(cmd, logger):
    cmd_str = [str(c) for c in cmd]
    logger.info(f"EXECUTING: {' '.join(cmd_str)}")

    process = subprocess.Popen(
        cmd_str, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, universal_newlines=True
    )

    for line in process.stdout:
        clean_line = line.strip()
        if clean_line:
            logger.info(f"[SUBPROCESS] {clean_line}")

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {process.returncode}: {' '.join(cmd_str)}")

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

class HFDownloadLogger:
    """Intercepts stderr to capture Hugging Face tqdm progress bars cleanly."""
    def __init__(self, logger):
        self.logger = logger
        self.original_stderr = sys.stderr
        self.buffer = ""
        self.last_percent = -1
        self.last_log_time = 0.0

    def write(self, text):
        self.buffer += text
        while '\r' in self.buffer or '\n' in self.buffer:
            sep = '\n' if '\n' in self.buffer else '\r'
            line, self.buffer = self.buffer.split(sep, 1)
            clean_line = line.strip()

            if clean_line:
                # Look for percentages like "45%" in the tqdm bar
                match = re.search(r'(\d+)%', clean_line)
                if match:
                    percent = int(match.group(1))
                    current_time = time.time()

                    # Log if 1 second has passed AND the percentage has actually changed, or if it hit 100%
                    if (current_time - self.last_log_time >= 1.0 and percent != self.last_percent) or percent == 100:
                        self.logger.info(f"[Downloading Weights] {clean_line}")
                        self.last_log_time = current_time
                        self.last_percent = percent

                    if percent == 100:
                        self.last_percent = -1 # Reset for the next file
                elif "Downloading" in clean_line or "Fetching" in clean_line or "model" in clean_line.lower():
                    self.logger.info(f"[HuggingFace] {clean_line}")

    def flush(self):
        pass

    def __enter__(self):
        sys.stderr = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr = self.original_stderr
