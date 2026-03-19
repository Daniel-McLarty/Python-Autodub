# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

import os
import sys
import warnings
from pathlib import Path

# --- SILENCE WARNINGS ---
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# --- PATHING & ENV SETUP ---
if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent
    SCRIPT_DIR = ROOT_DIR / "src"
else:
    SCRIPT_DIR = Path(__file__).resolve().parent
    ROOT_DIR = SCRIPT_DIR.parent

# --- MODEL REDIRECTION ---
MODELS_DIR = ROOT_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

os.environ["HF_HOME"] = str(MODELS_DIR / "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(MODELS_DIR / "huggingface")
os.environ["TORCH_HOME"] = str(MODELS_DIR / "torch")
os.environ["XDG_CACHE_HOME"] = str(MODELS_DIR / "misc_cache")
os.environ["TTS_HOME"] = str(MODELS_DIR / "tts")

# --- BINARY PATHING ---
bin_dir = ROOT_DIR / "bin"
if bin_dir.exists() and os.name == 'nt':
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]

# --- STANDARD LIBRARY IMPORTS ---
import subprocess
import srt
import logging
import threading
import queue
import json
import multiprocessing as mp
import tkinter as tk
import hashlib
import shutil
from tkinter import filedialog, ttk, scrolledtext
from dataclasses import dataclass

# --- AI & UI IMPORTS ---
import torch
from pydub import AudioSegment
from pyannote.audio import Pipeline
import sv_ttk
import darkdetect

# --- OTHER DIRECTORIES ---
TEMP_DIR = ROOT_DIR / "temp"
OUTPUT_DIR = ROOT_DIR / "output"
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# --- SETTINGS FILES ---
CONFIG_FILE = ROOT_DIR / "ui_config.json"
TOS_FILE = MODELS_DIR / "tts" / ".tos_agreed"

# --- CONFIGURATION DATACLASS ---
@dataclass
class PipelineConfig:
    video_file: Path
    srt_file: Path
    output_file: Path
    token: str
    max_speakers: int
    confidence: float
    workers: int
    hybrid: bool
    force_clean: bool

# --- HASHING UTILITY ---
def get_file_hash(filepath: Path) -> str:
    """Reads files in 1MB chunks to safely hash massive video files without OOM errors."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

# --- WORKER INITIALIZATION ---
worker_model = None

def init_worker():
    global worker_model
    os.environ["COQUI_TOS_AGREED"] = "1"
    from TTS.api import TTS
    worker_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")

def dub_worker_standalone(args):
    sub_item, speaker_turns, vocals_path, use_hybrid, conf_thresh = args
    global worker_model

    # Get the clean text right away
    clean_text = sub_item.content.replace('\n', ' ')

    eng_path = TEMP_DIR / "temp_lines" / f"eng_{sub_item.index}.wav"
    if eng_path.exists():
        return (str(eng_path), int(sub_item.start.total_seconds() * 1000),
                int((sub_item.end - sub_item.start).total_seconds() * 1000), sub_item.index, clean_text)

    try:
        start_ms = int(sub_item.start.total_seconds() * 1000)
        end_ms = int(sub_item.end.total_seconds() * 1000)
        duration = end_ms - start_ms

        current_speaker = None
        max_overlap = 0
        for turn in speaker_turns:
            overlap = max(0, min(end_ms, turn['end']) - max(start_ms, turn['start']))
            if overlap > max_overlap:
                max_overlap = overlap
                current_speaker = turn['speaker']
            if turn['start'] > end_ms: break

        generic_path = SCRIPT_DIR / "generic_male.wav"
        if not current_speaker or (max_overlap / duration) < conf_thresh:
            ref_path = generic_path if generic_path.exists() else None
        else:
            ref_path = TEMP_DIR / "base_clones" / f"{current_speaker}.wav"

        if use_hybrid and ref_path:
            ja_vocals = AudioSegment.from_wav(str(vocals_path))
            base_clone = AudioSegment.from_wav(str(ref_path))
            temp_ref = TEMP_DIR / "temp_lines" / f"ref_{sub_item.index}.wav"
            (base_clone + ja_vocals[start_ms:end_ms]).export(str(temp_ref), format="wav")
            ref_path = temp_ref

        worker_model.tts_to_file(
            text=clean_text,
            speaker_wav=str(ref_path),
            language="en",
            file_path=str(eng_path)
        )
        return (str(eng_path), start_ms, duration, sub_item.index, clean_text)
    except Exception as e:
        return f"Line {sub_item.index} Error: {str(e)}"

# --- CUSTOM LOG HANDLER FOR TKINTER ---
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

def run_and_log(cmd, logger):
    cmd_str = [str(c) for c in cmd]
    logger.info(f"EXECUTING: {' '.join(cmd_str)}")

    process = subprocess.Popen(
        cmd_str,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    for line in process.stdout:
        clean_line = line.strip()
        if clean_line:
            logger.info(f"[SUBPROCESS] {clean_line}")

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {process.returncode}: {' '.join(cmd_str)}")


# --- DUBBING PIPELINE (BUSINESS LOGIC) ---
class DubbingPipeline:
    def __init__(self, config: PipelineConfig, logger: logging.Logger, progress_queue: queue.Queue):
        self.cfg = config
        self.logger = logger
        self.progress_queue = progress_queue

    def manage_temp_state(self) -> bool:
        """Handles hashing and temp directory cleanup."""
        log = self.logger
        hash_file = TEMP_DIR / "run_hashes.json"

        log.info("Hashing input files to determine if resume is possible...")
        vid_hash = get_file_hash(self.cfg.video_file)
        srt_hash = get_file_hash(self.cfg.srt_file)
        current_hashes = {"video": vid_hash, "srt": srt_hash}

        old_hashes = {}
        if hash_file.exists():
            try:
                with open(hash_file, "r") as f:
                    old_hashes = json.load(f)
            except Exception: pass

        mismatch = (old_hashes.get("video") != vid_hash) or (old_hashes.get("srt") != srt_hash)

        if self.cfg.force_clean or mismatch:
            reason = "Force Clean requested." if self.cfg.force_clean else "Input files changed."
            log.info(f"{reason} Purging temporary files to start fresh...")

            for item in TEMP_DIR.iterdir():
                if item.name == "dubbing_process.log": continue
                if item.is_file(): item.unlink()
                elif item.is_dir(): shutil.rmtree(item)

            # Recreate required dirs
            (TEMP_DIR / "base_clones").mkdir(exist_ok=True)
            (TEMP_DIR / "temp_lines").mkdir(exist_ok=True)

            with open(hash_file, "w") as f:
                json.dump(current_hashes, f)
            return True # Clean build occurred
        else:
            log.info("Input files match previous run. Resuming from existing temp files...")
            return False # Resume occurred

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

            # 1. Extraction
            log.info("Step 1: Extracting Audio...")
            full_audio = TEMP_DIR / "full_audio.wav"
            if not full_audio.exists():
                run_and_log([
                    "ffmpeg", "-y", "-loglevel", "verbose",
                    "-i", self.cfg.video_file, "-map", "0:a:0", full_audio
                ], log)
            else:
                log.info("Audio already extracted. Skipping.")

            self.progress_queue.put(15)

            # 2. Demucs
            log.info("Step 2: Demucs Separation (4-Stem Mode)...")
            stem_dir = TEMP_DIR / "htdemucs" / "full_audio"
            v_stem = stem_dir / "vocals.wav"
            bg_stem = TEMP_DIR / "final_background_noise.wav"

            if not v_stem.exists():
                run_and_log([sys.executable, "-m", "demucs.separate", "-d", "cuda", "-o", TEMP_DIR, full_audio], log)
                if not v_stem.exists():
                    raise FileNotFoundError("Demucs failed silently!")

                log.info("Merging non-vocal stems into background track...")
                run_and_log([
                    "ffmpeg", "-y", "-loglevel", "verbose",
                    "-i", stem_dir / "bass.wav",
                    "-i", stem_dir / "drums.wav",
                    "-i", stem_dir / "other.wav",
                    "-filter_complex", "amix=inputs=3:duration=first",
                    bg_stem
                ], log)
            else:
                log.info("Stems already isolated. Skipping.")

            self.progress_queue.put(30)

            # 3. Diarization
            log.info(f"Step 3: Diarization (Capping at {self.cfg.max_speakers} speakers)...")
            log.info("Running Pyannote AI (This may take a while with no output)...")
            pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=self.cfg.token).to(torch.device("cuda"))
            diarization = pipeline(str(v_stem), num_speakers=self.cfg.max_speakers)
            
            ja_vocals = AudioSegment.from_wav(str(v_stem))
            speaker_segments, turns = {}, []

            turn_count = 0
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                start_ms = int(turn.start * 1000)
                end_ms = int(turn.end * 1000)
                turns.append({'start': start_ms, 'end': end_ms, 'speaker': speaker})
                
                chunk = ja_vocals[start_ms:end_ms]
                if speaker not in speaker_segments: speaker_segments[speaker] = []
                speaker_segments[speaker].append(chunk)
                turn_count += 1
            log.info(f"Extracted {turn_count} total speaking turns across {len(speaker_segments)} identified speakers.")

            self.progress_queue.put(40)

            # 4. Audit
            log.info("Step 4: Auditing speaker segments...")
            for spk, chunks in speaker_segments.items():
                clone_path = TEMP_DIR / "base_clones" / f"{spk}.wav"
                if clone_path.exists(): continue

                valid_chunks = [c for c in chunks if len(c) > 2000]
                if not valid_chunks:
                    log.warning(f" -> Speaker {spk} has no valid audio for cloning.")
                    continue

                def score_chunk(chunk):
                    rms = chunk.rms
                    volume_score = 1.0 - (abs(rms - 5000) / 5000)
                    length_bonus = 1.2 if 8000 < len(chunk) < 12000 else 1.0
                    return volume_score * length_bonus

                best_chunk = sorted(valid_chunks, key=score_chunk, reverse=True)[0]
                if len(best_chunk) > 12000: best_chunk = best_chunk[:12000]
                best_chunk.export(str(clone_path), format="wav")
                log.info(f" -> Locked identity for {spk}")

            self.progress_queue.put(50)

            # 5. Parallel Generation
            xtts_folder_name = "tts_models--multilingual--multi-dataset--xtts_v2"
            if not (MODELS_DIR / "tts" / xtts_folder_name / "model.pth").exists() and not (MODELS_DIR / "tts" / "tts" / xtts_folder_name / "model.pth").exists():
                log.info("Pre-fetching TTS Model...")
                from TTS.api import TTS
                _temp_tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
                del _temp_tts
                import gc; gc.collect()

            with open(self.cfg.srt_file, 'r', encoding='utf-8') as f:
                subs = list(srt.parse(f.read()))

            worker_args = [(sub, turns, str(v_stem), self.cfg.hybrid, self.cfg.confidence) for sub in subs]
            log.info(f"Step 5: Parallel Dubbing (Workers: {self.cfg.workers})...")

            final_results = []
            completed = 0
            total_subs = len(subs)

            with mp.Pool(processes=self.cfg.workers, initializer=init_worker) as pool:
                for res in pool.imap_unordered(dub_worker_standalone, worker_args):
                    if isinstance(res, str): log.error(res)
                    elif res: 
                        final_results.append(res)
                        path, start, target_ms, idx, text = res
                        log.info(f'[Worker] Successfully generated Line {idx}: "{text}"')
                    
                    completed += 1
                    self.progress_queue.put(50 + (completed / total_subs) * 35)

            self.progress_queue.put(85)

            # 6. Assembly
            log.info("Step 6: Merging generated lines into final track...")
            final_dialogue_track = AudioSegment.silent(duration=len(ja_vocals))
            sorted_results = sorted(final_results, key=lambda x: x[1])

            for i in range(0, len(sorted_results), 100):
                batch = sorted_results[i : i + 100]
                for res in batch:
                    path, start, target_ms, idx, text = res
                    try:
                        line_audio = AudioSegment.from_wav(path)

                        # Only stretch if the generated audio is significantly longer than the subtitle
                        if len(line_audio) > (target_ms + 200):
                            # Prevent ZeroDivisionError if an SRT has a glitchy 0-second duration
                            safe_target = max(target_ms, 1)
                            ratio = max(0.5, min(len(line_audio) / safe_target, 2.0))
                            tmp = str(Path(path).with_name(f"{Path(path).stem}_adj.wav"))

                            try:
                                # Using run_and_log to catch FFmpeg divadom instead of failing silently
                                run_and_log(["ffmpeg", "-y", "-i", path, "-filter:a", f"atempo={ratio:.4f}", tmp], log)

                                # Verify the file actually got created before trying to load it
                                if Path(tmp).exists():
                                    line_audio = AudioSegment.from_wav(tmp)
                                else:
                                    log.warning(f"File missing after atempo filter for line {idx}, falling back to original.")
                            except Exception as ffmpeg_err:
                                log.warning(f"Time-stretch failed for line {idx} ({ffmpeg_err}), falling back to original.")

                        final_dialogue_track = final_dialogue_track.overlay(line_audio, position=start)
                    except Exception as e:
                        log.error(f"Failed to overlay line {idx}: {e}")

            self.progress_queue.put(90)

            # 7. Mixing and LUFS Normalization
            log.info("Step 7: Normalizing LUFS and Mixing Audio...")
            final_dialogue_path = TEMP_DIR / "final_dialogue.wav"
            mixed_path = TEMP_DIR / "mixed.wav"

            final_dialogue_track.export(str(final_dialogue_path), format="wav")

            # Lowered background LUFS from -14 to -26 so it doesn't overpower the dialogue
            filter_complex = "[0:a]loudnorm=I=-26:TP=-2.0:LRA=11[bg]; [1:a]loudnorm=I=-12:TP=-1.0:LRA=11[dialog]; [bg][dialog]amix=inputs=2:duration=longest[out]"

            run_and_log([
                "ffmpeg", "-y", "-loglevel", "verbose",
                "-i", bg_stem, "-i", final_dialogue_path,
                "-filter_complex", filter_complex, "-map", "[out]", "-ac", "2", mixed_path
            ], log)

            self.progress_queue.put(95)

            # 8. Muxing
            log.info("Step 8: Muxing into output file...")
            self.cfg.output_file.parent.mkdir(parents=True, exist_ok=True)

            run_and_log([
                "ffmpeg", "-y", "-loglevel", "verbose",
                "-i", self.cfg.video_file, "-i", mixed_path,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                self.cfg.output_file
            ], log)
            
            self.progress_queue.put(100)
            log.info("--- SUCCESS! Pipeline Complete. ---")
            return True

        except Exception as e:
            log.error(f"PIPELINE FAILED: {str(e)}")
            return False


# --- MAIN GUI APP ---
class DubbingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Auto-Dubbing Studio")
        self.root.geometry("750x950") # Slightly taller for new rows

        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.is_running = False

        # --- LOAD SAVED CONFIG ---
        self.config_data = {
            "hf_token": "hf_YOUR_TOKEN_HERE",
            "max_speakers": 22,
            "confidence": 0.5,
            "workers": 3,
            "hybrid": False,
            "out_dir": str(OUTPUT_DIR),
            "out_name": "FINAL_DUBBED_MOVIE.mkv"
        }

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config_data.update(json.load(f))
            except Exception:
                pass

        self.saved_tos = TOS_FILE.exists()

        self.ensure_directories()
        self.build_ui()
        self.setup_logging()
        self.check_queues()

    def ensure_directories(self):
        TEMP_DIR.mkdir(exist_ok=True)
        OUTPUT_DIR.mkdir(exist_ok=True)
        (TEMP_DIR / "base_clones").mkdir(exist_ok=True)
        (TEMP_DIR / "temp_lines").mkdir(exist_ok=True)

    def setup_logging(self):
        self.logger = logging.getLogger("DubLogger")
        self.logger.setLevel(logging.INFO)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

        gui_handler = QueueHandler(self.log_queue)
        gui_handler.setFormatter(formatter)
        self.logger.addHandler(gui_handler)

        log_file = TEMP_DIR / "dubbing_process.log"
        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def build_ui(self):
        pad = {'padx': 10, 'pady': 5}

        # --- File Selection Frame ---
        file_frame = ttk.LabelFrame(self.root, text="Files & Output")
        file_frame.pack(fill="x", **pad)

        ttk.Label(file_frame, text="Video File:").grid(row=0, column=0, sticky="e", **pad)
        self.video_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.video_var, width=50).grid(row=0, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=self.browse_video).grid(row=0, column=2, **pad)

        ttk.Label(file_frame, text="SRT File:").grid(row=1, column=0, sticky="e", **pad)
        self.srt_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.srt_var, width=50).grid(row=1, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=self.browse_srt).grid(row=1, column=2, **pad)

        ttk.Label(file_frame, text="Output Folder:").grid(row=2, column=0, sticky="e", **pad)
        self.out_dir_var = tk.StringVar(value=self.config_data["out_dir"])
        ttk.Entry(file_frame, textvariable=self.out_dir_var, width=50).grid(row=2, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=self.browse_out_dir).grid(row=2, column=2, **pad)

        ttk.Label(file_frame, text="Output Name:").grid(row=3, column=0, sticky="e", **pad)
        self.out_name_var = tk.StringVar(value=self.config_data["out_name"])
        ttk.Entry(file_frame, textvariable=self.out_name_var, width=50).grid(row=3, column=1, sticky="w", **pad)

        # --- Settings Frame ---
        set_frame = ttk.LabelFrame(self.root, text="Configuration")
        set_frame.pack(fill="x", **pad)

        ttk.Label(set_frame, text="HF Token:").grid(row=0, column=0, sticky="e", **pad)
        self.token_var = tk.StringVar(value=self.config_data["hf_token"])
        ttk.Entry(set_frame, textvariable=self.token_var, width=40).grid(row=0, column=1, columnspan=3, sticky="w", **pad)

        ttk.Label(set_frame, text="Max Speakers:").grid(row=1, column=0, sticky="e", **pad)
        self.speakers_var = tk.IntVar(value=self.config_data["max_speakers"])
        ttk.Spinbox(set_frame, from_=1, to=50, textvariable=self.speakers_var, width=5).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(set_frame, text="Confidence Threshold:").grid(row=1, column=2, sticky="e", **pad)
        self.conf_var = tk.DoubleVar(value=self.config_data["confidence"])
        ttk.Spinbox(set_frame, from_=0.1, to=1.0, increment=0.1, textvariable=self.conf_var, width=5).grid(row=1, column=3, sticky="w", **pad)

        ttk.Label(set_frame, text="Max Workers:").grid(row=2, column=0, sticky="e", **pad)
        self.workers_var = tk.IntVar(value=self.config_data["workers"])
        ttk.Spinbox(set_frame, from_=1, to=10, textvariable=self.workers_var, width=5).grid(row=2, column=1, sticky="w", **pad)

        self.hybrid_var = tk.BooleanVar(value=self.config_data["hybrid"])
        ttk.Checkbutton(set_frame, text="Use Hybrid Emotion Cloning", variable=self.hybrid_var).grid(row=2, column=2, columnspan=2, sticky="w", **pad)

        self.force_clean_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(set_frame, text="Force Clean Build (Wipe Temp)", variable=self.force_clean_var).grid(row=3, column=0, columnspan=2, sticky="w", **pad)

        self.tos_var = tk.BooleanVar(value=self.saved_tos)
        ttk.Checkbutton(set_frame, text="I agree to the Coqui TTS Terms of Service (coqui.ai/cpml)", variable=self.tos_var).grid(row=4, column=0, columnspan=4, sticky="w", **pad)

        # --- Execution Frame ---
        exec_frame = tk.Frame(self.root)
        exec_frame.pack(fill="x", **pad)

        self.start_btn = ttk.Button(exec_frame, text="START DUBBING PIPELINE", command=self.start_pipeline)
        self.start_btn.pack(pady=10)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(exec_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", padx=10)

        # --- Log Output ---
        log_frame = ttk.LabelFrame(self.root, text="Console Output")
        log_frame.pack(fill="both", expand=True, **pad)

        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', bg="black", fg="lightgreen", font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)

    def browse_video(self):
        filepath = filedialog.askopenfilename(filetypes=[("Video Files", "*.mkv *.mp4 *.avi")])
        if filepath: self.video_var.set(filepath)

    def browse_srt(self):
        filepath = filedialog.askopenfilename(filetypes=[("Subtitle Files", "*.srt")])
        if filepath: self.srt_var.set(filepath)

    def browse_out_dir(self):
        dirpath = filedialog.askdirectory()
        if dirpath: self.out_dir_var.set(dirpath)

    def write_log(self, msg):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def check_queues(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.write_log(msg)

        while not self.progress_queue.empty():
            val = self.progress_queue.get()
            self.progress_var.set(val)

        self.root.after(100, self.check_queues)

    def start_pipeline(self):
        if self.is_running: return

        if not self.tos_var.get():
            self.log_queue.put("ERROR: You must agree to the Coqui TTS Terms of Service to start the pipeline.")
            return

        # --- SAVE FULL SETTINGS TO JSON ---
        self.config_data = {
            "hf_token": self.token_var.get(),
            "max_speakers": self.speakers_var.get(),
            "confidence": self.conf_var.get(),
            "workers": self.workers_var.get(),
            "hybrid": self.hybrid_var.get(),
            "out_dir": self.out_dir_var.get(),
            "out_name": self.out_name_var.get()
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config_data, f)
        except Exception as e:
            self.log_queue.put(f"Warning: Could not save config: {e}")

        TOS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOS_FILE, "w") as f:
            f.write("Agreed")

        os.environ["COQUI_TOS_AGREED"] = "1"

        v_file = self.video_var.get()
        s_file = self.srt_var.get()
        if not v_file or not s_file:
            self.log_queue.put("ERROR: Please select both a Video and SRT file.")
            return

        self.is_running = True
        self.start_btn.config(state="disabled")
        self.progress_var.set(0)

        out_path = Path(self.out_dir_var.get()) / self.out_name_var.get()

        config = PipelineConfig(
            video_file=Path(v_file),
            srt_file=Path(s_file),
            output_file=out_path,
            token=self.token_var.get(),
            max_speakers=self.speakers_var.get(),
            confidence=self.conf_var.get(),
            workers=self.workers_var.get(),
            hybrid=self.hybrid_var.get(),
            force_clean=self.force_clean_var.get()
        )

        thread = threading.Thread(target=self.run_pipeline_thread, args=(config,))
        thread.daemon = True
        thread.start()

    def run_pipeline_thread(self, config):
        pipeline = DubbingPipeline(config, self.logger, self.progress_queue)
        pipeline.run()
        self.reset_ui()

    def reset_ui(self):
        self.is_running = False
        self.root.after(0, lambda: self.start_btn.config(state="normal"))

if __name__ == "__main__":
    mp.freeze_support()
    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

    root = tk.Tk()

    if darkdetect.isDark():
        sv_ttk.set_theme("dark")
    else:
        sv_ttk.set_theme("light")

    app = DubbingApp(root)
    root.mainloop()
