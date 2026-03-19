# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

import sys
import queue
import logging
import json
import shutil
import librosa
import numpy as np
import soundfile as sf
import multiprocessing as mp

import srt
import torch
import whisperx
from whisperx.diarize import DiarizationPipeline

from config import PipelineConfig, TEMP_DIR
from utils import get_file_hash, run_and_log, HFDownloadLogger
from worker import init_worker, dub_worker_standalone

class DubbingPipeline:
    def __init__(self, config: PipelineConfig, logger: logging.Logger, progress_queue: queue.Queue):
        self.cfg = config
        self.logger = logger
        self.progress_queue = progress_queue

    def manage_temp_state(self) -> bool:
        log = self.logger
        hash_file = TEMP_DIR / "run_hashes.json"
        
        log.info("Hashing input files to determine if resume is possible...")
        vid_hash = get_file_hash(self.cfg.video_file)
        src_hash = get_file_hash(self.cfg.source_srt_file)
        tgt_hash = get_file_hash(self.cfg.target_srt_file)
        current_hashes = {"video": vid_hash, "source_srt": src_hash, "target_srt": tgt_hash}

        old_hashes = {}
        if hash_file.exists():
            try:
                with open(hash_file, "r") as f:
                    old_hashes = json.load(f)
            except Exception: pass

        mismatch = (old_hashes.get("video") != vid_hash) or \
                   (old_hashes.get("source_srt") != src_hash) or \
                   (old_hashes.get("target_srt") != tgt_hash)

        if self.cfg.force_clean or mismatch:
            reason = "Force Clean requested." if self.cfg.force_clean else "Input files changed."
            log.info(f"{reason} Purging temporary files to start fresh...")
            for item in TEMP_DIR.iterdir():
                if item.name == "dubbing_process.log": continue
                if item.is_file(): item.unlink()
                elif item.is_dir(): shutil.rmtree(item)

            (TEMP_DIR / "base_clones").mkdir(exist_ok=True)
            (TEMP_DIR / "temp_lines").mkdir(exist_ok=True)

            with open(hash_file, "w") as f:
                json.dump(current_hashes, f)
            return True
        else:
            log.info("Input files match previous run. Resuming from existing temp files...")
            return False

    def run(self):
        log = self.logger
        log.info("--- SYSTEM CHECK ---")
        if torch.cuda.is_available():
            log.info(f"SUCCESS: CUDA active. Using {torch.cuda.get_device_name(0)}")
        else:
            log.error("FAILED: No GPU detected. Check drivers!")
            return False

        try:
            self.manage_temp_state()
            self.progress_queue.put(5)

            # --- STEP 1: EXTRACTION ---
            log.info("Step 1: Extracting Audio...")
            full_audio = TEMP_DIR / "full_audio.wav"
            if not full_audio.exists():
                run_and_log(["ffmpeg", "-y", "-loglevel", "verbose", "-i", self.cfg.video_file, "-map", "0:a:0", full_audio], log)
            else: log.info("Audio already extracted. Skipping.")
            self.progress_queue.put(15)

            # --- STEP 2: DEMUCS ---
            log.info("Step 2: Demucs Separation (4-Stem Mode)...")
            stem_dir = TEMP_DIR / "htdemucs" / "full_audio"
            v_stem = stem_dir / "vocals.wav"
            bg_stem = TEMP_DIR / "final_background_noise.wav"

            if not v_stem.exists():
                run_and_log([sys.executable, "-m", "demucs.separate", "-d", "cuda", "-o", TEMP_DIR, full_audio], log)
                if not v_stem.exists(): raise FileNotFoundError("Demucs failed silently!")
                
                log.info("Merging non-vocal stems into background track...")
                run_and_log([
                    "ffmpeg", "-y", "-loglevel", "verbose",
                    "-i", stem_dir / "bass.wav", "-i", stem_dir / "drums.wav", "-i", stem_dir / "other.wav",
                    "-filter_complex", "amix=inputs=3:duration=first", bg_stem
                ], log)
            else: log.info("Stems already isolated. Skipping.")
            self.progress_queue.put(30)

            # --- STEP 3: WHISPERX ---
            log.info(f"Step 3: WhisperX Alignment & Diarization (Max {self.cfg.max_speakers} speakers)...")
            audio = whisperx.load_audio(str(v_stem))
            with open(self.cfg.source_srt_file, 'r', encoding='utf-8') as f:
                src_subs = list(srt.parse(f.read()))

            word_segments = [{"text": sub.content.replace('\n', ' '), "start": sub.start.total_seconds(), "end": sub.end.total_seconds()} for sub in src_subs]

            with HFDownloadLogger(log):
                model_a, metadata = whisperx.load_align_model(language_code=self.cfg.source_lang, device="cuda")
                aligned_result = whisperx.align(word_segments, model_a, metadata, audio, "cuda", return_char_alignments=False)

                if self.cfg.max_speakers > 1:
                    from whisperx.diarize import DiarizationPipeline
                    diarize_model = DiarizationPipeline(token=self.cfg.token, device="cuda")
                    diarize_segments = diarize_model(audio, min_speakers=1, max_speakers=self.cfg.max_speakers)
                    final_result = whisperx.assign_word_speakers(diarize_segments, aligned_result)
                else:
                    log.info("Max speakers is 1. Skipping diarization model to save VRAM and assigning 'SPEAKER_00'.")
                    final_result = {"segments": []}
                    for seg in aligned_result["segments"]:
                        seg["speaker"] = "SPEAKER_00"
                        final_result["segments"].append(seg)

            orig_vocals, sr = sf.read(str(v_stem))
            speaker_segments, turns = {}, []

            for segment in final_result.get("segments", []):
                if "speaker" not in segment: continue
                speaker = segment["speaker"]
                start_ms = int(segment["start"] * 1000)
                end_ms = int(segment["end"] * 1000)
                segment_text = segment.get("text", "").strip()

                turns.append({
                    'start': start_ms,
                    'end': end_ms,
                    'speaker': speaker,
                    'text': segment_text
                })

                # Calculate numpy array indices
                start_frame = int((start_ms / 1000) * sr)
                end_frame = int((end_ms / 1000) * sr)
                chunk = orig_vocals[start_frame:end_frame]

                if speaker not in speaker_segments: speaker_segments[speaker] = []
                speaker_segments[speaker].append({
                    "audio": chunk,
                    "text": segment_text,
                    "length_frames": len(chunk)
                })

            log.info("Freeing WhisperX VRAM to make room for F5-TTS...")
            try:
                del model_a
                if self.cfg.max_speakers > 1:
                    del diarize_model
            except Exception: pass

            import gc
            gc.collect()
            torch.cuda.empty_cache()

            self.progress_queue.put(40)

            # --- STEP 4: AUDIT ---
            log.info("Step 4: Auditing speaker segments & writing transcripts...")
            for spk, chunks in speaker_segments.items():
                clone_path = TEMP_DIR / "base_clones" / f"{spk}.wav"
                text_path = TEMP_DIR / "base_clones" / f"{spk}.txt"
                if clone_path.exists(): continue

                # If Hybrid is ON, we want a smaller base clone (max 7s) to leave room for the scene audio.
                # If Hybrid is OFF, we can safely use up to 12s.
                max_frames = (7 * sr) if self.cfg.hybrid else (12 * sr)
                min_frames = 2 * sr

                valid_chunks = [c for c in chunks if min_frames < c["length_frames"] <= max_frames]

                if not valid_chunks:
                    fallback_chunks = [c for c in chunks if c["length_frames"] > min_frames]
                    if not fallback_chunks: continue
                    best_chunk = sorted(fallback_chunks, key=lambda x: x["length_frames"])[0]
                else:
                    best_chunk = sorted(valid_chunks, key=lambda x: x["length_frames"], reverse=True)[0]

                sf.write(str(clone_path), best_chunk["audio"], sr)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(best_chunk["text"])
            self.progress_queue.put(50)

            # --- STEP 5: PARALLEL GENERATION ---
            log.info("Step 5: Pre-fetching/Verifying F5-TTS Models...")

            # Wrap the F5-TTS loading in the interceptor to capture any HF downloads and log them!
            with HFDownloadLogger(log):
                from f5_tts.api import F5TTS
                _temp_tts = F5TTS(device="cuda")
                del _temp_tts
                import gc; gc.collect()

            with open(self.cfg.target_srt_file, 'r', encoding='utf-8') as f:
                subs = list(srt.parse(f.read()))

            worker_args = [(sub, turns, str(v_stem), self.cfg.hybrid, self.cfg.confidence, self.cfg.target_lang, self.cfg.max_speakers) for sub in subs]
            log.info(f"Step 5: Parallel Dubbing (Workers: {self.cfg.workers})...")
            final_results = []
            completed = 0
            
            with mp.Pool(processes=self.cfg.workers, initializer=init_worker) as pool:
                for res in pool.imap_unordered(dub_worker_standalone, worker_args):
                    if isinstance(res, str): log.error(res)
                    elif res: 
                        final_results.append(res)
                        log.info(f'[Worker] Successfully generated Line {res[3]}: "{res[4]}"')
                    completed += 1
                    self.progress_queue.put(50 + (completed / len(subs)) * 35)
            self.progress_queue.put(85)

            # --- STEP 6: ASSEMBLY ---
            log.info("Step 6: Merging generated lines into final track...")
            v_info = sf.info(v_stem)
            total_duration_samples = v_info.frames
            sr = v_info.samplerate

            final_dialogue_track = np.zeros(total_duration_samples, dtype=np.float32)

            for res in sorted(final_results, key=lambda x: x[1]):
                path, start_ms, target_ms, idx, _ = res
                try:
                    line_audio, l_sr = sf.read(path)
                    if l_sr != sr:
                        line_audio = librosa.resample(line_audio, orig_sr=l_sr, target_sr=sr)

                    if len(line_audio.shape) > 1:
                        line_audio = line_audio.mean(axis=1)

                    # Calculate exact samples allowed (with a 200ms grace period for natural trailing breaths)
                    safe_target_samples = int(((target_ms + 200) / 1000) * sr)
                    actual_samples = len(line_audio)

                    if actual_samples > safe_target_samples:
                        rate = actual_samples / safe_target_samples

                        capped_rate = min(rate, 2)
                        log.info(f"Line {idx} exceeds slot. Shrinking time by {capped_rate:.2f}x.")

                        line_audio = librosa.effects.time_stretch(line_audio, rate=capped_rate)

                        if len(line_audio) > safe_target_samples:
                            log.warning(f"Line {idx} hallucinated excessively. Hard-truncating the tail.")
                            line_audio = line_audio[:safe_target_samples]

                    start_sample = int((start_ms / 1000) * sr)
                    end_sample = start_sample + len(line_audio)

                    if end_sample > total_duration_samples:
                        line_audio = line_audio[:total_duration_samples - start_sample]
                        end_sample = total_duration_samples

                    final_dialogue_track[start_sample:end_sample] += line_audio

                except Exception as e:
                    log.error(f"Failed to assemble line {idx}: {e}")

            final_dialogue_track = np.clip(final_dialogue_track, -1.0, 1.0)
            self.progress_queue.put(90)

            # --- STEP 7: AUDIO MIXING & NORMALIZATION ---
            log.info("Step 7: Normalizing and Mixing Audio (LUFS Balancing)...")
            final_dialogue_path = TEMP_DIR / "final_dialogue.wav"
            mixed_path = TEMP_DIR / "mixed.wav"

            sf.write(final_dialogue_path, final_dialogue_track, sr)

            run_and_log([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", bg_stem, "-i", final_dialogue_path,
                "-filter_complex",
                "[0:a]loudnorm=I=-26:TP=-2.0:LRA=11[bg]; "
                "[1:a]loudnorm=I=-12:TP=-1.0:LRA=11[dialog]; "
                "[bg][dialog]amix=inputs=2:duration=longest[out]",
                "-map", "[out]", "-ac", "2", mixed_path
            ], log)
            self.progress_queue.put(95)

            # --- STEP 8: FINAL MUXING (Video + Audio + 2x Subs) ---
            log.info("Step 8: Muxing Video, Audio, and dual-language Subtitles...")
            self.cfg.output_file.parent.mkdir(parents=True, exist_ok=True)
            
            mux_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", self.cfg.video_file,
                "-i", mixed_path,
                "-i", self.cfg.source_srt_file,
                "-i", self.cfg.target_srt_file,

                "-map", "0:v:0",
                "-map", "1:a:0",
                "-map", "2:s:0",
                "-map", "3:s:0",

                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "320k",
                "-c:s", "srt",

                "-metadata:s:s:0", f"language={self.cfg.source_lang}",
                "-metadata:s:s:0", f"title=Original ({self.cfg.source_lang})",
                "-metadata:s:s:1", f"language={self.cfg.target_lang}",
                "-metadata:s:s:1", f"title=Translated ({self.cfg.target_lang})",

                str(self.cfg.output_file)
            ]

            run_and_log(mux_cmd, log)

            self.progress_queue.put(100)
            log.info("--- SUCCESS! Pipeline Complete. ---")
            torch.cuda.empty_cache()
            return True

        except Exception as e:
            log.error(f"PIPELINE FAILED: {str(e)}")
            torch.cuda.empty_cache()
            return False
