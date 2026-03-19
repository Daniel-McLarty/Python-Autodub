# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import sys
import subprocess
import shutil
import srt
import torch
import logging
import threading
import queue
import warnings

import multiprocessing as mp
import tkinter as tk

from tkinter import filedialog, ttk, scrolledtext
from pydub import AudioSegment
from pyannote.audio import Pipeline 

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# --- PATHING SETUP ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
TEMP_DIR = os.path.join(ROOT_DIR, "temp")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")

# --- WORKER INITIALIZATION ---
worker_model = None

def init_worker():
    global worker_model
    from TTS.api import TTS
    # Load model once per worker process
    worker_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")

def dub_worker_standalone(args):
    # Unpack UI-configured variables
    sub_item, speaker_turns, vocals_path, use_hybrid, conf_thresh = args
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
        if not current_speaker or (max_overlap / duration) < conf_thresh:
            ref_path = generic_path if os.path.exists(generic_path) else None
        else:
            ref_path = os.path.join(TEMP_DIR, f"base_clones/{current_speaker}.wav")

        # HYBRID TOGGLE
        if use_hybrid and ref_path:
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

# --- CUSTOM LOG HANDLER FOR TKINTER ---
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

# --- MAIN GUI APP ---
class DubbingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Auto-Dubbing Studio")
        self.root.geometry("750x850")
        
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.is_running = False

        self.ensure_directories()
        self.build_ui()
        self.setup_logging()
        self.check_queues()

    def ensure_directories(self):
        os.makedirs(TEMP_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(os.path.join(TEMP_DIR, "base_clones"), exist_ok=True)
        os.makedirs(os.path.join(TEMP_DIR, "temp_lines"), exist_ok=True)

    def setup_logging(self):
        self.logger = logging.getLogger("DubLogger")
        self.logger.setLevel(logging.INFO)
        # Clear existing handlers
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
            
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
        
        # GUI Log Handler
        gui_handler = QueueHandler(self.log_queue)
        gui_handler.setFormatter(formatter)
        self.logger.addHandler(gui_handler)
        
        # File Handler
        log_file = os.path.join(TEMP_DIR, "dubbing_process.log")
        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def build_ui(self):
        pad = {'padx': 10, 'pady': 5}
        
        # --- File Selection Frame ---
        file_frame = ttk.LabelFrame(self.root, text="Files")
        file_frame.pack(fill="x", **pad)

        ttk.Label(file_frame, text="Video File:").grid(row=0, column=0, sticky="e", **pad)
        self.video_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.video_var, width=50).grid(row=0, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=self.browse_video).grid(row=0, column=2, **pad)

        ttk.Label(file_frame, text="SRT File:").grid(row=1, column=0, sticky="e", **pad)
        self.srt_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.srt_var, width=50).grid(row=1, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=self.browse_srt).grid(row=1, column=2, **pad)

        # --- Settings Frame ---
        set_frame = ttk.LabelFrame(self.root, text="Configuration")
        set_frame.pack(fill="x", **pad)

        ttk.Label(set_frame, text="HF Token:").grid(row=0, column=0, sticky="e", **pad)
        self.token_var = tk.StringVar(value="hf_YOUR_TOKEN_HERE")
        ttk.Entry(set_frame, textvariable=self.token_var, width=40).grid(row=0, column=1, columnspan=3, sticky="w", **pad)

        ttk.Label(set_frame, text="Max Speakers:").grid(row=1, column=0, sticky="e", **pad)
        self.speakers_var = tk.IntVar(value=22)
        ttk.Spinbox(set_frame, from_=1, to=50, textvariable=self.speakers_var, width=5).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(set_frame, text="Confidence Threshold:").grid(row=1, column=2, sticky="e", **pad)
        self.conf_var = tk.DoubleVar(value=0.5)
        ttk.Spinbox(set_frame, from_=0.1, to=1.0, increment=0.1, textvariable=self.conf_var, width=5).grid(row=1, column=3, sticky="w", **pad)

        ttk.Label(set_frame, text="Max Workers:").grid(row=2, column=0, sticky="e", **pad)
        self.workers_var = tk.IntVar(value=3)
        ttk.Spinbox(set_frame, from_=1, to=10, textvariable=self.workers_var, width=5).grid(row=2, column=1, sticky="w", **pad)

        self.hybrid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(set_frame, text="Use Hybrid Emotion Cloning", variable=self.hybrid_var).grid(row=2, column=2, columnspan=2, sticky="w", **pad)

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

    def write_log(self, msg):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def check_queues(self):
        # Process log messages
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.write_log(msg)
            
        # Process progress updates
        while not self.progress_queue.empty():
            val = self.progress_queue.get()
            self.progress_var.set(val)

        # Re-run check every 100ms
        self.root.after(100, self.check_queues)

    def start_pipeline(self):
        if self.is_running: return
        
        v_file = self.video_var.get()
        s_file = self.srt_var.get()
        if not v_file or not s_file:
            self.log_queue.put("ERROR: Please select both a Video and SRT file.")
            return

        self.is_running = True
        self.start_btn.config(state="disabled")
        self.progress_var.set(0)
        
        # Grab config values to pass to thread
        config = {
            "video_file": v_file,
            "srt_file": s_file,
            "token": self.token_var.get(),
            "max_speakers": self.speakers_var.get(),
            "confidence": self.conf_var.get(),
            "workers": self.workers_var.get(),
            "hybrid": self.hybrid_var.get()
        }

        # Run pipeline in a background thread to prevent GUI freezing
        thread = threading.Thread(target=self.run_pipeline_thread, args=(config,))
        thread.daemon = True
        thread.start()

    def run_pipeline_thread(self, cfg):
        log = self.logger
        log.info("--- SYSTEM CHECK ---")
        if torch.cuda.is_available():
            log.info(f"SUCCESS: CUDA active. Using {torch.cuda.get_device_name(0)}")
        else:
            log.error("FAILED: No GPU detected. Check drivers!")
            self.reset_ui()
            return

        try:
            self.progress_queue.put(5)
            # 1. Extraction
            log.info("Step 1: Extracting Audio...")
            full_audio = os.path.join(TEMP_DIR, "full_audio.wav")
            subprocess.run(["ffmpeg", "-y", "-i", cfg['video_file'], "-map", "0:a:0", full_audio], check=True)

            self.progress_queue.put(15)
            # 2. Demucs
            log.info("Step 2: Demucs Separation (4-Stem Mode)...")

            # Use python -m to ensure it runs explicitly in this environment and catches errors
            subprocess.run([sys.executable, "-m", "demucs.separate", "-d", "cuda", "-o", TEMP_DIR, full_audio], check=True)

            # Fix the pathing so Windows uses proper backslashes
            stem_dir = os.path.join(TEMP_DIR, "htdemucs", "full_audio")
            v_stem = os.path.join(stem_dir, "vocals.wav")

            # Verify Demucs actually did its job
            if not os.path.exists(v_stem):
                raise FileNotFoundError(f"Demucs failed silently! Could not find stems in {stem_dir}. You might have run out of GPU VRAM.")

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

            self.progress_queue.put(30)
            # 3. Diarization
            log.info(f"Step 3: Diarization (Capping at {cfg['max_speakers']} speakers)...")
            pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=cfg['token']).to(torch.device("cuda"))
            diarization = pipeline(v_stem, num_speakers=cfg['max_speakers'])
            
            ja_vocals = AudioSegment.from_wav(v_stem)
            speaker_segments, turns = {}, []

            log.info("Extracting diarization timestamps...")
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                start_ms = int(turn.start * 1000)
                end_ms = int(turn.end * 1000)
                turns.append({'start': start_ms, 'end': end_ms, 'speaker': speaker})
                
                chunk = ja_vocals[start_ms:end_ms]
                if speaker not in speaker_segments:
                    speaker_segments[speaker] = []
                speaker_segments[speaker].append(chunk)

            self.progress_queue.put(40)
            # 4. Audit
            log.info("Step 4: Auditing speaker segments...")
            for spk, chunks in speaker_segments.items():
                valid_chunks = [c for c in chunks if len(c) > 2000]
                if not valid_chunks: continue

                def score_chunk(chunk):
                    rms = chunk.rms
                    volume_score = 1.0 - (abs(rms - 5000) / 5000)
                    length_bonus = 1.2 if 8000 < len(chunk) < 12000 else 1.0
                    return volume_score * length_bonus

                best_chunk = sorted(valid_chunks, key=score_chunk, reverse=True)[0]
                if len(best_chunk) > 12000: best_chunk = best_chunk[:12000]
                clone_path = os.path.join(TEMP_DIR, f"base_clones/{spk}.wav")
                best_chunk.export(clone_path, format="wav")

            self.progress_queue.put(50)
            # 5. Parallel Generation
            with open(cfg['srt_file'], 'r', encoding='utf-8') as f:
                subs = list(srt.parse(f.read()))

            worker_args = [(sub, turns, v_stem, cfg['hybrid'], cfg['confidence']) for sub in subs]
            log.info(f"Step 5: Parallel Dubbing (Workers: {cfg['workers']})...")

            final_results = []
            completed = 0
            total_subs = len(subs)

            with mp.Pool(processes=cfg['workers'], initializer=init_worker) as pool:
                for res in pool.imap_unordered(dub_worker_standalone, worker_args):
                    if isinstance(res, str): 
                        log.error(res)
                    elif res: 
                        final_results.append(res)
                    
                    completed += 1
                    prog = 50 + (completed / total_subs) * 35
                    self.progress_queue.put(prog)
                    if completed % 10 == 0:
                        log.info(f"Progress: {completed}/{total_subs} lines generated.")

            self.progress_queue.put(85)
            # 6. Assembly
            log.info("Step 6: Merging generated lines into final track...")
            final_dialogue_track = AudioSegment.silent(duration=len(ja_vocals))
            sorted_results = sorted(final_results, key=lambda x: x[1])

            batch_size = 100
            for i in range(0, len(sorted_results), batch_size):
                batch = sorted_results[i : i + batch_size]
                for res in batch:
                    path, start, target_ms, idx = res
                    try:
                        line_audio = AudioSegment.from_wav(path)
                        if len(line_audio) > (target_ms + 200):
                            ratio = max(0.5, min(len(line_audio)/target_ms, 2.0))
                            tmp = path.replace(".wav", "_adj.wav")
                            subprocess.run(["ffmpeg", "-y", "-i", path, "-filter:a", f"atempo={ratio}", tmp], capture_output=True)
                            line_audio = AudioSegment.from_wav(tmp)
                        final_dialogue_track = final_dialogue_track.overlay(line_audio, position=start)
                    except Exception as e:
                        log.error(f"Failed to overlay line {idx}: {e}")

            self.progress_queue.put(90)
            # 7 & 8. Mixing and Muxing
            log.info("Step 7: Mixing Audio...")
            final_dialogue_path = os.path.join(TEMP_DIR, "final_dialogue.wav")
            mixed_path = os.path.join(TEMP_DIR, "mixed.wav")
            final_movie_path = os.path.join(OUTPUT_DIR, "FINAL_DUBBED_MOVIE.mkv")

            final_dialogue_track.export(final_dialogue_path, format="wav")
            final_bg = AudioSegment.from_wav(bg_stem)
            final_bg.overlay(final_dialogue_track).export(mixed_path, format="wav")

            self.progress_queue.put(95)
            log.info("Step 8: Muxing into MKV...")
            subprocess.run(["ffmpeg", "-y", "-i", cfg['video_file'], "-i", mixed_path,
                            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                            final_movie_path], capture_output=True)
            
            self.progress_queue.put(100)
            log.info("--- SUCCESS! Pipeline Complete. ---")

        except Exception as e:
            log.error(f"PIPELINE FAILED: {str(e)}")
        finally:
            self.reset_ui()

    def reset_ui(self):
        self.is_running = False
        self.root.after(0, lambda: self.start_btn.config(state="normal"))

if __name__ == "__main__":
    mp.freeze_support()
    try: mp.set_start_method('spawn', force=True)
    except RuntimeError: pass

    root = tk.Tk()
    app = DubbingApp(root)
    root.mainloop()
