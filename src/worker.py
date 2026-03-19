# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

import soundfile as sf
import numpy as np
import os
import librosa
from contextlib import redirect_stdout
from config import TEMP_DIR, SCRIPT_DIR
from utils import estimate_gender_from_pitch

worker_model = None

def init_worker():
    global worker_model
    from f5_tts.api import F5TTS
    worker_model = F5TTS(device="cuda")

def dub_worker_standalone(args):
    # Unpack the new max_speakers argument
    sub_item, speaker_turns, orig_path, use_hybrid, conf_thresh, target_lang, max_speakers = args
    global worker_model

    clean_text = sub_item.content.replace('\n', ' ').strip()
    if not clean_text.endswith(('.', '!', '?', '"')):
        clean_text += '.'

    targ_path = TEMP_DIR / "temp_lines" / f"line_{sub_item.index}.wav"
    
    if targ_path.exists():
        # Remember to return duration (0 here is just a placeholder if it already exists,
        # but better to calculate actual ms duration)
        return (str(targ_path), int(sub_item.start.total_seconds() * 1000),
                int((sub_item.end - sub_item.start).total_seconds() * 1000), sub_item.index, clean_text)

    try:
        info = sf.info(orig_path)
        sr = info.samplerate

        start_ms = int(sub_item.start.total_seconds() * 1000)
        end_ms = int(sub_item.end.total_seconds() * 1000)
        duration = end_ms - start_ms

        start_frame = int(sub_item.start.total_seconds() * sr)
        end_frame = int(sub_item.end.total_seconds() * sr)

        # --- SPEAKER & SCENE TEXT IDENTIFICATION ---
        current_speaker = None
        scene_text = ""

        if max_speakers == 1:
            # Bypass all math. Force SPEAKER_00 and never fail to generic.
            current_speaker = "SPEAKER_00"
            for turn in speaker_turns:
                # Grab text for hybrid mode if it overlaps at all
                if max(0, min(end_ms, turn['end']) - max(start_ms, turn['start'])) > 0:
                    scene_text += turn.get('text', "") + " "
        else:
            # Multi-Speaker Absolute Margin Logic
            speaker_overlaps = {}
            scene_texts = {}

            # Calculate total overlap per speaker in this timeframe
            for turn in speaker_turns:
                overlap = max(0, min(end_ms, turn['end']) - max(start_ms, turn['start']))
                if overlap > 0:
                    spk = turn['speaker']
                    speaker_overlaps[spk] = speaker_overlaps.get(spk, 0) + overlap
                    if spk not in scene_texts:
                        scene_texts[spk] = []
                    if turn.get('text'):
                        scene_texts[spk].append(turn['text'])
                if turn['start'] > end_ms: break

            # Sort speakers by who talked the most in this slot
            sorted_spks = sorted(speaker_overlaps.items(), key=lambda x: x[1], reverse=True)

            if sorted_spks:
                top_spk, top_overlap = sorted_spks[0]
                top_ratio = top_overlap / duration

                runner_up_ratio = 0.0
                if len(sorted_spks) > 1:
                    runner_up_ratio = sorted_spks[1][1] / duration

                # Check if the top speaker beats the runner-up by the user's defined margin (conf_thresh)
                # E.g., 21% - 10% = 11%. If conf_thresh is 0.10, this passes!
                if (top_ratio - runner_up_ratio) >= conf_thresh:
                    current_speaker = top_spk
                    scene_text = " ".join(scene_texts[top_spk])

        # --- BASE CLONE SELECTION ---
        base_text = ""
        # The generic fallback now ONLY triggers if max_speakers > 1 AND the margin test failed
        if not current_speaker:
            current_snippet, _ = sf.read(orig_path, start=start_frame, stop=end_frame)
            detected_gender = estimate_gender_from_pitch(current_snippet, sr)
            ref_path = SCRIPT_DIR / f"generic_{detected_gender}.wav"
            txt_path = SCRIPT_DIR / f"generic_{detected_gender}.txt"
            if txt_path.exists():
                with open(txt_path, "r", encoding="utf-8") as f:
                    base_text = f.read().strip()
        else:
            ref_path = TEMP_DIR / "base_clones" / f"{current_speaker}.wav"
            txt_path = TEMP_DIR / "base_clones" / f"{current_speaker}.txt"
            if txt_path.exists():
                with open(txt_path, "r", encoding="utf-8") as f:
                    base_text = f.read().strip()

        final_ref_path = str(ref_path)
        final_ref_text = base_text

        # --- HYBRID CLONING (Append Scene Audio + Scene Text) ---
        if use_hybrid and ref_path:
            base_audio, b_sr = sf.read(str(ref_path))
            scene_audio, _ = sf.read(orig_path, start=start_frame, stop=end_frame)

            # Ensure snippet matches base channels
            if len(base_audio.shape) == 1 and len(scene_audio.shape) > 1:
                scene_audio = scene_audio.mean(axis=1)

            hybrid_audio = np.concatenate([base_audio, scene_audio])
            temp_ref_wav = TEMP_DIR / "temp_lines" / f"ref_{sub_item.index}.wav"
            sf.write(temp_ref_wav, hybrid_audio, b_sr)

            # Combine the texts (Base Transcript + Source Transcript of the current scene)
            final_ref_text = f"{base_text} {scene_text}".strip()
            final_ref_path = str(temp_ref_wav)

        # --- F5-TTS INFERENCE ---
        with open(os.devnull, 'w', encoding="utf-8") as devnull, redirect_stdout(devnull):
            infer_result = worker_model.infer(
                ref_file=final_ref_path,
                ref_text=final_ref_text,
                gen_text=clean_text
            )

        # F5-TTS returns (wav, sr, spectrogram), so we safely grab just the first two
        wav = infer_result[0]
        gen_sr = infer_result[1]

        wav_trimmed, _ = librosa.effects.trim(wav, top_db=35)
        sf.write(str(targ_path), wav_trimmed, gen_sr)
        
        return (str(targ_path), start_ms, duration, sub_item.index, clean_text)
    except Exception as e:
        return f"Line {sub_item.index} Error: {str(e)}"
