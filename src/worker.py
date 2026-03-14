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

def init_worker(device_str):
    global worker_model
    from f5_tts.api import F5TTS
    worker_model = F5TTS(device=device_str)

def dub_worker_standalone(args):
    sub_item, speaker_turns, orig_path, use_hybrid, conf_thresh, target_lang, max_speakers = args
    global worker_model

    clean_text = sub_item.content.replace('\n', ' ').strip()
    if not clean_text.endswith(('.', '!', '?', '"')):
        clean_text += '.'

    targ_path = TEMP_DIR / "temp_lines" / f"line_{sub_item.index}.wav"
    
    if targ_path.exists():
        # Better to return actual calculated ms duration
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
            current_speaker = "SPEAKER_00"
            for turn in speaker_turns:
                if max(0, min(end_ms, turn['end']) - max(start_ms, turn['start'])) > 0:
                    scene_text += turn.get('text', "") + " "
        else:
            # Multi-Speaker Absolute Margin Logic
            speaker_overlaps = {}
            scene_texts = {}

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

            sorted_spks = sorted(speaker_overlaps.items(), key=lambda x: x[1], reverse=True)

            if sorted_spks:
                top_spk, top_overlap = sorted_spks[0]
                top_ratio = top_overlap / duration

                runner_up_ratio = 0.0
                if len(sorted_spks) > 1:
                    runner_up_ratio = sorted_spks[1][1] / duration

                if (top_ratio - runner_up_ratio) >= conf_thresh:
                    current_speaker = top_spk
                    scene_text = " ".join(scene_texts[top_spk])

        # --- BASE CLONE SELECTION (WITH 2-SECOND ENFORCEMENT) ---
        base_text = ""
        ref_path = None

        if current_speaker:
            temp_ref = TEMP_DIR / "base_clones" / f"{current_speaker}.wav"
            temp_txt = TEMP_DIR / "base_clones" / f"{current_speaker}.txt"

            if temp_ref.exists() and temp_txt.exists():
                # STRICT CHECK: Ensure the clone is at least 2.0 seconds long to prevent F5-TTS from generating garbage!
                clone_info = sf.info(str(temp_ref))
                if (clone_info.frames / clone_info.samplerate) >= 2.0:
                    ref_path = temp_ref
                    with open(temp_txt, "r", encoding="utf-8") as f:
                        base_text = f.read().strip()

        # If it's a generic speaker, OR the clone file went missing, OR the clone was less than 2 seconds long
        if not ref_path:
            current_snippet, _ = sf.read(orig_path, start=start_frame, stop=end_frame)
            detected_gender = estimate_gender_from_pitch(current_snippet, sr)
            ref_path = SCRIPT_DIR / f"generic_{detected_gender}.wav"
            txt_path = SCRIPT_DIR / f"generic_{detected_gender}.txt"

            if txt_path.exists():
                with open(txt_path, "r", encoding="utf-8") as f:
                    base_text = f.read().strip()
            else:
                base_text = "This is a generic fallback voice."

        final_ref_path = str(ref_path)
        final_ref_text = base_text

        # --- HYBRID CLONING (Append Scene Audio + Scene Text) ---
        if use_hybrid and ref_path:
            base_audio, b_sr = sf.read(str(ref_path))
            scene_audio, _ = sf.read(orig_path, start=start_frame, stop=end_frame)

            if len(base_audio.shape) == 1 and len(scene_audio.shape) > 1:
                scene_audio = scene_audio.mean(axis=1)

            hybrid_audio = np.concatenate([base_audio, scene_audio])
            temp_ref_wav = TEMP_DIR / "temp_lines" / f"ref_{sub_item.index}.wav"
            sf.write(temp_ref_wav, hybrid_audio, b_sr)

            final_ref_text = f"{base_text} {scene_text}".strip()
            final_ref_path = str(temp_ref_wav)

        # --- F5-TTS INFERENCE ---
        with open(os.devnull, 'w', encoding="utf-8") as devnull, redirect_stdout(devnull):
            infer_result = worker_model.infer(
                ref_file=final_ref_path,
                ref_text=final_ref_text,
                gen_text=clean_text
            )

        wav = infer_result[0]
        gen_sr = infer_result[1]

        wav_trimmed, _ = librosa.effects.trim(wav, top_db=35)
        sf.write(str(targ_path), wav_trimmed, gen_sr)
        
        return (str(targ_path), start_ms, duration, sub_item.index, clean_text)
    
    except Exception as e:
        return f"Line {sub_item.index} Error: {str(e)}"
