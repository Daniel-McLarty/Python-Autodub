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

            # --- STEP 2: CHUNKED DEMUCS ---
            log.info("Step 2: Demucs Separation")

            v_stem = TEMP_DIR / "vocals.wav"
            bg_stem = TEMP_DIR / "final_background_noise.wav"
            chunk_dir = TEMP_DIR / "demucs_chunks"
            chunk_dir.mkdir(exist_ok=True)

            if not v_stem.exists():
                f_info = sf.info(str(full_audio))
                duration = f_info.frames / f_info.samplerate

                chunk_len = 600  # 10 minutes
                overlap = 4      # 4 seconds of overlap for the crossfade buffer
                
                processed_v_chunks = []
                processed_bg_chunks = []

                # 1. Process with Overlap
                start = 0
                idx = 0
                while start < duration:
                    end = min(start + chunk_len + overlap, duration)
                    c_input = chunk_dir / f"in_{idx:03d}.wav"

                    # Extract chunk with overlap
                    run_and_log([
                        "ffmpeg", "-y", "-ss", str(start), "-to", str(end),
                        "-i", str(full_audio), "-c", "copy", str(c_input)
                    ], log)

                    # Run Demucs on the small chunk
                    run_and_log([
                        sys.executable, "-m", "demucs.separate", "-n", "htdemucs",
                        "-d", "cuda", "--two-stems", "vocals", "--segment", "7", "-j", "1",
                        "-o", str(chunk_dir), str(c_input)
                    ], log)

                    # Move results and track them
                    out_path = chunk_dir / "htdemucs" / f"in_{idx:03d}"
                    v_chunk = chunk_dir / f"v_{idx:03d}.wav"
                    bg_chunk = chunk_dir / f"bg_{idx:03d}.wav"

                    import shutil
                    shutil.move(str(out_path / "vocals.wav"), str(v_chunk))
                    shutil.move(str(out_path / "no_vocals.wav"), str(bg_chunk))

                    processed_v_chunks.append(v_chunk)
                    processed_bg_chunks.append(bg_chunk)

                    if end >= duration: break
                    start += chunk_len
                    idx += 1

                # 2. Seamless Reassembly using FFmpeg Crossfade
                def stitch_stems(chunks, output_path):
                    if len(chunks) == 1:
                        shutil.move(str(chunks[0]), str(output_path))
                        return

                    # Construct a complex filter graph to crossfade all chunks sequentially
                    # This prevents the "10-minute click"
                    filter_str = ""
                    for i in range(len(chunks) - 1):
                        if i == 0:
                            filter_str += f"[0][1]acrossfade=d={overlap}:c1=tri:c2=tri[a1];"
                        else:
                            filter_str += f"[a{i}][{i+1}]acrossfade=d={overlap}:c1=tri:c2=tri[a{i+1}];"

                    inputs = []
                    for c in chunks: inputs.extend(["-i", str(c)])

                    last_label = f"[a{len(chunks)-1}]"
                    run_and_log(["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_str, "-map", last_label, str(output_path)], log)

                log.info("Stitching stems with 4-second linear crossfades...")
                stitch_stems(processed_v_chunks, v_stem)
                stitch_stems(processed_bg_chunks, bg_stem)

                shutil.rmtree(chunk_dir, ignore_errors=True)
            else:
                log.info("Stems already isolated. Skipping.")

            # --- STEP 3: CHUNKED WHISPERX ALIGNMENT & DIARIZATION ---
            log.info(f"Step 3: Chunked Alignment & Diarization (Max {self.cfg.max_speakers} speakers per segment)...")

            orig_vocals, sr = sf.read(str(v_stem), dtype='float32')

            if len(orig_vocals.shape) > 1:
                orig_vocals = orig_vocals.mean(axis=1)

            total_duration_samples = len(orig_vocals)

            with open(self.cfg.source_srt_file, 'r', encoding='utf-8') as f:
                src_subs = list(srt.parse(f.read()))
            # Map target subtitles by index so we can attach them to the correct chunks
            with open(self.cfg.target_srt_file, 'r', encoding='utf-8') as f:
                tgt_subs = {sub.index: sub for sub in list(srt.parse(f.read()))}

            # --- Create 10-Minute SRT Packages ---
            CHUNK_SIZE = 600.0
            chunks = []
            current_chunk_subs = []
            current_chunk_start = max(0.0, src_subs[0].start.total_seconds() - 1.0) if src_subs else 0.0

            for sub in src_subs:
                sub_start = sub.start.total_seconds()
                # Split precisely on an SRT boundary if we cross the 10-min mark
                if sub_start - current_chunk_start > CHUNK_SIZE and current_chunk_subs:
                    chunk_end = current_chunk_subs[-1].end.total_seconds() + 1.0
                    chunks.append({"start": current_chunk_start, "end": chunk_end, "subs": current_chunk_subs})
                    current_chunk_start = max(0.0, sub_start - 1.0)
                    current_chunk_subs = [sub]
                else:
                    current_chunk_subs.append(sub)

            if current_chunk_subs:
                chunks.append({"start": current_chunk_start, "end": current_chunk_subs[-1].end.total_seconds() + 1.0, "subs": current_chunk_subs})

            # --- Initialize Models Once ---
            with HFDownloadLogger(log):
                model_a, metadata = whisperx.load_align_model(language_code=self.cfg.source_lang, device="cuda")
                if self.cfg.max_speakers > 1:
                    from whisperx.diarize import DiarizationPipeline
                    diarize_model = DiarizationPipeline(token=self.cfg.token, device="cuda")

            master_worker_args = []
            speaker_segments = {}

            # --- Loop Through Packages ---
            for i, chunk in enumerate(chunks):
                log.info(f"Processing Section {i+1}/{len(chunks)} ({chunk['start']:.1f}s to {chunk['end']:.1f}s)...")
                c_start, c_end = chunk["start"], chunk["end"]

                # Slice 32-bit audio for this specific chunk
                start_sample = max(0, int(c_start * sr))
                end_sample = min(total_duration_samples, int(c_end * sr))
                chunk_audio = orig_vocals[start_sample:end_sample]

                if len(chunk_audio) == 0: continue

                # Resample chunk to 16kHz specifically for WhisperX to process
                chunk_audio_16k = librosa.resample(chunk_audio, orig_sr=sr, target_sr=16000)

                # Offset SRT timestamps to zero for the aligner
                offset_chunk = [{"text": s.content.replace('\n', ' '), "start": max(0.0, s.start.total_seconds() - c_start), "end": max(0.0, s.end.total_seconds() - c_start)} for s in chunk["subs"]]

                aligned_chunk = whisperx.align(offset_chunk, model_a, metadata, chunk_audio_16k, "cuda", return_char_alignments=False)

                if self.cfg.max_speakers > 1:
                    diarize_segments = diarize_model(chunk_audio_16k, min_speakers=1, max_speakers=self.cfg.max_speakers)
                    chunk_result = whisperx.assign_word_speakers(diarize_segments, aligned_chunk)
                else:
                    chunk_result = aligned_chunk
                    for seg in chunk_result["segments"]: seg["speaker"] = "SPEAKER_00"

                # Process clones and absolute turns for this chunk
                chunk_turns = []
                for segment in chunk_result.get("segments", []):
                    if "speaker" not in segment: continue
                    # Prepend Chunk ID to completely isolate Pyannote logic per 10-min block
                    speaker = f"C{i}_{segment['speaker']}"

                    # Worker.py requires absolute milliseconds for overlap math
                    abs_start_ms = int((segment["start"] + c_start) * 1000)
                    abs_end_ms = int((segment["end"] + c_start) * 1000)
                    segment_text = segment.get("text", "").strip()

                    chunk_turns.append({'start': abs_start_ms, 'end': abs_end_ms, 'speaker': speaker, 'text': segment_text})

                    # Calculate numpy array indices using original 32-bit audio
                    s_frame = int(segment["start"] * sr)
                    e_frame = int(segment["end"] * sr)
                    audio_snippet = chunk_audio[s_frame:e_frame]

                    if speaker not in speaker_segments: speaker_segments[speaker] = []
                    speaker_segments[speaker].append({"audio": audio_snippet, "text": segment_text, "length_frames": len(audio_snippet)})

                # Attach TARGET translations to this chunk's timing data
                for sub in chunk["subs"]:
                    tgt_sub = tgt_subs.get(sub.index)
                    if tgt_sub:
                        master_worker_args.append((tgt_sub, chunk_turns, str(v_stem), self.cfg.hybrid, self.cfg.confidence, self.cfg.target_lang, self.cfg.max_speakers))

            log.info("Freeing WhisperX VRAM to make room for F5-TTS...")
            try:
                del model_a
                if self.cfg.max_speakers > 1: del diarize_model
            except Exception: pass
            import gc; gc.collect(); torch.cuda.empty_cache()

            self.progress_queue.put(40)

            # --- STEP 4: AUDIT ---
            log.info("Step 4: Auditing speaker segments & writing transcripts...")
            for spk, snippets in speaker_segments.items():
                clone_path = TEMP_DIR / "base_clones" / f"{spk}.wav"
                text_path = TEMP_DIR / "base_clones" / f"{spk}.txt"
                if clone_path.exists(): continue

                max_frames = (7 * sr) if self.cfg.hybrid else (12 * sr)
                min_frames = 2 * sr
                valid_chunks = [c for c in snippets if min_frames < c["length_frames"] <= max_frames]

                if not valid_chunks:
                    fallback = [c for c in snippets if c["length_frames"] > min_frames]
                    if not fallback: continue
                    best_chunk = sorted(fallback, key=lambda x: x["length_frames"])[0]
                else:
                    best_chunk = sorted(valid_chunks, key=lambda x: x["length_frames"], reverse=True)[0]

                sf.write(str(clone_path), best_chunk["audio"], sr)
                with open(text_path, "w", encoding="utf-8") as f: f.write(best_chunk["text"])

            self.progress_queue.put(50)

            # --- STEP 5: PARALLEL GENERATION ---
            log.info("Step 4.5: Pre-fetching/Verifying F5-TTS Models...")

            # Wrap the F5-TTS loading in the interceptor to capture any HF downloads and log them!
            with HFDownloadLogger(log):
                from f5_tts.api import F5TTS
                _temp_tts = F5TTS(device="cuda")
                del _temp_tts
                import gc; gc.collect()

            log.info(f"Step 5: Parallel Dubbing (Workers: {self.cfg.workers})...")
            final_results = []
            completed = 0
            
            with mp.Pool(processes=self.cfg.workers, initializer=init_worker) as pool:
                # Swapped 'worker_args' for 'master_worker_args'
                for res in pool.imap_unordered(dub_worker_standalone, master_worker_args):
                    if isinstance(res, str): log.error(res)
                    elif res: 
                        final_results.append(res)
                        log.info(f'[Worker] Successfully generated Line {res[3]}: "{res[4]}"')
                    completed += 1
                    # Swapped len(subs) for len(master_worker_args)
                    self.progress_queue.put(50 + (completed / len(master_worker_args)) * 35)
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

            # --- PRE-DUBBING CLEANUP ---
            log.info("Clearing Transcription/Diarization models from VRAM...")
            try:
                # Delete the large model objects
                if 'model' in locals(): del model
                if 'diarize_model' in locals(): del diarize_model

                # Force Python and PyTorch to physically release the memory
                import gc
                gc.collect()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            except Exception as e:
                log.warning(f"Cleanup failed (non-critical): {e}")

            # --- STEP 7: AUDIO MIXING & NORMALIZATION ---
            log.info("Step 7: Normalizing and Mixing Audio (LUFS Balancing)...")
            final_dialogue_path = TEMP_DIR / "final_dialogue.wav"
            mixed_path = TEMP_DIR / "mixed.wav"

            sf.write(final_dialogue_path, final_dialogue_track, sr)

            run_and_log([
                "ffmpeg", "-y", "-loglevel", "verbose",
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
                "ffmpeg", "-y", "-loglevel", "verbose",
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
