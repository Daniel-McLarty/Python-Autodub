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
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# --- MODEL REDIRECTION ---
MODELS_DIR = os.path.join(ROOT_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Set these BEFORE importing torch or pyannote
os.environ["HF_HOME"] = os.path.join(MODELS_DIR, "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(MODELS_DIR, "huggingface")
os.environ["TORCH_HOME"] = os.path.join(MODELS_DIR, "torch")
os.environ["XDG_CACHE_HOME"] = os.path.join(MODELS_DIR, "misc_cache")
os.environ["TTS_HOME"] = os.path.join(MODELS_DIR, "tts")

# --- STANDARD LIBRARY IMPORTS ---
import subprocess
import srt
import logging
import multiprocessing as mp
from tqdm import tqdm

# --- AI IMPORTS ---
import torch
from pydub import AudioSegment
from pyannote.audio import Pipeline 


# --- DIRECTORY SETUP ---
TEMP_DIR = os.path.join(ROOT_DIR, "temp")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.join(TEMP_DIR, "base_clones"), exist_ok=True)
os.makedirs(os.path.join(TEMP_DIR, "temp_lines"), exist_ok=True)

# --- CONFIGURATION ---
VIDEO_FILE = os.path.join(ROOT_DIR, "input_file.mkv")  # Assuming input is at root
EN_SRT = os.path.join(ROOT_DIR, "en.srt")              # Assuming input is at root
HF_TOKEN = "hf_" # Your token
MAX_WORKERS = 3
USE_HYBRID_CLONING = False  # TOGGLE: Set to True for more scene-specific emotion
MAX_SPEAKERS = 22           # Based on IMDB Cast List
CONFIDENCE_THRESHOLD = 0.5  # Subtitle must overlap at least 50% of a diarized turn
LOG_FILE = os.path.join(TEMP_DIR, "dubbing_process.log")

# --- WORKER INITIALIZATION ---
worker_model = None

def init_worker():
    global worker_model
    from TTS.api import TTS
    worker_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")

def dub_worker_standalone(args):
    sub_item, speaker_turns, vocals_path = args
    global worker_model

    eng_path = os.path.join(TEMP_DIR, f"temp_lines/eng_{sub_item.index}.wav")
    if os.path.exists(eng_path):
        return (eng_path, int(sub_item.start.total_seconds() * 1000),
                int((sub_item.end - sub_item.start).total_seconds() * 1000), sub_item.index)

    try:
        start_ms = int(sub_item.start.total_seconds() * 1000)
        end_ms = int(sub_item.end.total_seconds() * 1000)
        duration = end_ms - start_ms

        # ENHANCED CONFIDENCE MATCHING
        current_speaker = None
        max_overlap = 0
        for turn in speaker_turns:
            overlap = max(0, min(end_ms, turn['end']) - max(start_ms, turn['start']))
            if overlap > max_overlap:
                max_overlap = overlap
                current_speaker = turn['speaker']
            if turn['start'] > end_ms: break

        # FALLBACK LOGIC
        generic_path = os.path.join(SCRIPT_DIR, "generic_male.wav")
        if not current_speaker or (max_overlap / duration) < CONFIDENCE_THRESHOLD:
            ref_path = generic_path if os.path.exists(generic_path) else None
        else:
            ref_path = os.path.join(TEMP_DIR, f"base_clones/{current_speaker}.wav")

        # HYBRID TOGGLE
        if USE_HYBRID_CLONING and ref_path:
            ja_vocals = AudioSegment.from_wav(vocals_path)
            base_clone = AudioSegment.from_wav(ref_path)
            temp_ref = os.path.join(TEMP_DIR, f"temp_lines/ref_{sub_item.index}.wav")
            (base_clone + ja_vocals[start_ms:end_ms]).export(temp_ref, format="wav")
            ref_path = temp_ref

        worker_model.tts_to_file(
            text=sub_item.content.replace('\n', ' '),
            speaker_wav=ref_path,
            language="en",
            file_path=eng_path
        )
        return (eng_path, start_ms, duration, sub_item.index)
    except Exception as e:
        return f"Line {sub_item.index} Error: {str(e)}"

# --- MAIN BLOCK ---
if __name__ == "__main__":
    mp.freeze_support()
    try: mp.set_start_method('spawn', force=True)
    except RuntimeError: pass

    # --- COQUI TOS AGREEMENT CHECK ---
    tos_file = os.path.join(MODELS_DIR, "tts", ".tos_agreed")

    if not os.path.exists(tos_file):
        print("\n" + "="*60)
        print("Coqui TTS Model License Agreement")
        print("="*60)
        print("To use the voice cloning features, you must confirm the following:")
        print(' > "I have purchased a commercial license from Coqui: licensing@coqui.ai"')
        print(' > "Otherwise, I agree to the terms of the non-commercial CPML: https://coqui.ai/cpml"')
        print("="*60)

        while True:
            ans = input("Do you agree to these terms? [y/n]: ").strip().lower()
            if ans in ['y', 'yes']:
                # Save the agreement so we don't ask again
                os.makedirs(os.path.dirname(tos_file), exist_ok=True)
                with open(tos_file, 'w') as f:
                    f.write("Agreed")
                break
            elif ans in ['n', 'no']:
                print("You must agree to the Terms of Service to use the voice generation. Exiting...")
                sys.exit(1)
            else:
                print("Please type 'y' or 'n'.")

    # If the file exists or they just agreed, safely bypass the worker prompt
    os.environ["COQUI_TOS_AGREED"] = "1"

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.FileHandler(LOG_FILE, mode='w'), logging.StreamHandler()])
    log = logging.getLogger(__name__)

    log.info("--- SYSTEM CHECK ---")
    if torch.cuda.is_available():
        log.info(f"SUCCESS: CUDA is active. Using {torch.cuda.get_device_name(0)}")
    else:
        log.error("FAILED: No GPU detected. Check your drivers!")
        exit()

    # 1. Extraction
    log.info("Step 1: Extracting Audio...")
    full_audio = os.path.join(TEMP_DIR, "full_audio.wav")
    subprocess.run(["ffmpeg", "-y", "-i", VIDEO_FILE, "-map", "0:a:0", full_audio])

    # 2. Handle 4-Stem Demucs
    try:
        log.info("Step 2: Demucs Separation (4-Stem Mode)...")
        subprocess.run(["demucs", "-d", "cuda", "-o", TEMP_DIR, full_audio], check=True)

        stem_dir = os.path.join(TEMP_DIR, "htdemucs/full_audio")
        v_stem = os.path.join(stem_dir, "vocals.wav")

        log.info("Merging non-vocal stems into background track...")
        bg_stem = os.path.join(TEMP_DIR, "final_background_noise.wav")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", os.path.join(stem_dir, "bass.wav"),
            "-i", os.path.join(stem_dir, "drums.wav"),
            "-i", os.path.join(stem_dir, "other.wav"),
            "-filter_complex", "amix=inputs=3:duration=first",
            bg_stem
        ], check=True, capture_output=True)

    except Exception as e:
        log.error(f"Demucs/Merging failed: {e}")
        exit()

    # 3. SMART DIARIZATION
    log.info(f"Step 3: Diarization (Capping at {MAX_SPEAKERS} speakers)...")
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=HF_TOKEN).to(torch.device("cuda"))
    diarization = pipeline(v_stem, num_speakers=MAX_SPEAKERS)
    
    ja_vocals = AudioSegment.from_wav(v_stem)
    speaker_segments, turns = {}, []

    # --- BUG FIX: Populate turns and speaker_segments ---
    log.info("Extracting diarization timestamps and building speaker chunks...")
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        start_ms = int(turn.start * 1000)
        end_ms = int(turn.end * 1000)

        turns.append({'start': start_ms, 'end': end_ms, 'speaker': speaker})

        chunk = ja_vocals[start_ms:end_ms]
        if speaker not in speaker_segments:
            speaker_segments[speaker] = []
        speaker_segments[speaker].append(chunk)

    # 4. HIGH-FIDELITY SPEAKER AUDIT
    log.info("Step 4: Auditing speaker segments for the cleanest voice identity...")

    for spk, chunks in speaker_segments.items():
        valid_chunks = [c for c in chunks if len(c) > 2000]

        if not valid_chunks:
            log.warning(f"Speaker {spk} has no valid audio for cloning. Using generic fallback.")
            continue

        def score_chunk(chunk):
            length_ms = len(chunk)
            rms = chunk.rms
            volume_score = 1.0 - (abs(rms - 5000) / 5000)
            length_bonus = 1.2 if 8000 < length_ms < 12000 else 1.0
            return volume_score * length_bonus

        best_chunk = sorted(valid_chunks, key=score_chunk, reverse=True)[0]

        if len(best_chunk) > 12000:
            best_chunk = best_chunk[:12000]

        clone_path = os.path.join(TEMP_DIR, f"base_clones/{spk}.wav")
        best_chunk.export(clone_path, format="wav")
        log.info(f" -> Locked identity for {spk} (Score: {score_chunk(best_chunk):.2f})")

    # 5. Parallel Processing
    with open(EN_SRT, 'r', encoding='utf-8') as f:
        subs = list(srt.parse(f.read()))

    worker_args = [(sub, turns, v_stem) for sub in subs]
    log.info(f"Step 5: Starting Parallel Dubbing (Workers: {MAX_WORKERS})")

    final_results = []
    with mp.Pool(processes=MAX_WORKERS, initializer=init_worker) as pool:
        for res in tqdm(pool.imap_unordered(dub_worker_standalone, worker_args), total=len(subs), desc="GPU Processing"):
            if isinstance(res, str): log.error(res)
            elif res: final_results.append(res)

    # 6. Memory-Efficient Assembly
    log.info("Step 6: Merging generated lines into final track (Incremental mode)...")
    final_dialogue_track = AudioSegment.silent(duration=len(ja_vocals))
    
    sorted_results = sorted(final_results, key=lambda x: x[1])

    batch_size = 100
    for i in range(0, len(sorted_results), batch_size):
        batch = sorted_results[i : i + batch_size]
        log.info(f"Assembling batch {i//batch_size + 1}...")
        for res in batch:
            path, start, target_ms, idx = res
            try:
                line_audio = AudioSegment.from_wav(path)

                # --- BUG FIX: Hardware-safe clamp for atempo filter ---
                if len(line_audio) > (target_ms + 200):
                    ratio = max(1, min(len(line_audio)/target_ms, 2.0))
                    tmp = path.replace(".wav", "_adj.wav")
                    subprocess.run(["ffmpeg", "-y", "-i", path, "-filter:a", f"atempo={ratio}", tmp], capture_output=True)
                    line_audio = AudioSegment.from_wav(tmp)

                final_dialogue_track = final_dialogue_track.overlay(line_audio, position=start)
            except Exception as e:
                log.error(f"Failed to overlay line {idx}: {e}")

    # 7 & 8: Final Mixing
    log.info("Step 7: Exporting Dialogue and Mixing with Background...")
    final_dialogue_path = os.path.join(TEMP_DIR, "final_dialogue.wav")
    mixed_path = os.path.join(TEMP_DIR, "mixed.wav")
    final_movie_path = os.path.join(OUTPUT_DIR, "FINAL_DUBBED_MOVIE.mkv")

    final_dialogue_track.export(final_dialogue_path, format="wav")

    final_bg = AudioSegment.from_wav(bg_stem)
    final_mix = final_bg.overlay(final_dialogue_track)
    final_mix.export(mixed_path, format="wav")

    log.info("Step 8: Muxing into Final MKV...")
    subprocess.run(["ffmpeg", "-y", "-i", VIDEO_FILE, "-i", mixed_path,
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                    final_movie_path])
    
    log.info("--- SUCCESS! ---")
