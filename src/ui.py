# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (C) Daniel McLarty 2026

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
LOCAL_CACHE = PROJECT_ROOT / ".uv_cache"
os.environ["UV_CACHE_DIR"] = str(LOCAL_CACHE)

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=SyntaxWarning)

import queue
import json
import logging
import threading
import multiprocessing as mp
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox # --- ADDED: messagebox

import sv_ttk
import darkdetect

from config import CONFIG_FILE, SUPPORTED_LANGS, TEMP_DIR, OUTPUT_DIR, PipelineConfig
from utils import QueueHandler
from pipeline import DubbingPipeline

class DubbingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Autodub Studio")
        self.root.geometry("780x950")

        icon_path = PROJECT_ROOT / "assets" / "Icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except Exception:
                pass

        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.is_running = False

        self.config_data = {
            "hf_token": "hf_YOUR_TOKEN_HERE",
            "max_speakers": 1,
            "confidence": 0.10,
            "workers": 1,
            "hybrid": False,
            "source_lang": "ja",
            "target_lang": "en",
            "out_dir": str(OUTPUT_DIR),
            "out_name": "FINAL_DUBBED_MOVIE.mkv"
        }

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config_data.update(json.load(f))
            except Exception: pass

        self.setup_logging()
        self.build_ui()
        self.check_queues()

    def setup_logging(self):
        self.logger = logging.getLogger("DubLogger")
        self.logger.setLevel(logging.INFO)
        if self.logger.hasHandlers(): self.logger.handlers.clear()

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

        # --- File Section ---
        file_frame = ttk.LabelFrame(self.root, text="Files & Output")
        file_frame.pack(fill="x", **pad)

        ttk.Label(file_frame, text="Video File:").grid(row=0, column=0, sticky="e", **pad)
        self.video_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.video_var, width=50).grid(row=0, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=lambda: self.video_var.set(filedialog.askopenfilename())).grid(row=0, column=2, **pad)

        ttk.Label(file_frame, text="Source SRT:").grid(row=1, column=0, sticky="e", **pad)
        self.src_srt_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.src_srt_var, width=50).grid(row=1, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=lambda: self.src_srt_var.set(filedialog.askopenfilename())).grid(row=1, column=2, **pad)

        ttk.Label(file_frame, text="Target SRT:").grid(row=2, column=0, sticky="e", **pad)
        self.tgt_srt_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.tgt_srt_var, width=50).grid(row=2, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=lambda: self.tgt_srt_var.set(filedialog.askopenfilename())).grid(row=2, column=2, **pad)

        ttk.Label(file_frame, text="Output Folder:").grid(row=3, column=0, sticky="e", **pad)
        self.out_dir_var = tk.StringVar(value=self.config_data["out_dir"])
        ttk.Entry(file_frame, textvariable=self.out_dir_var, width=50).grid(row=3, column=1, **pad)
        ttk.Button(file_frame, text="Browse", command=lambda: self.out_dir_var.set(filedialog.askdirectory())).grid(row=3, column=2, **pad)

        ttk.Label(file_frame, text="Output Name:").grid(row=4, column=0, sticky="e", **pad)
        self.out_name_var = tk.StringVar(value=self.config_data["out_name"])
        ttk.Entry(file_frame, textvariable=self.out_name_var, width=50).grid(row=4, column=1, sticky="w", **pad)

        # --- Settings Section ---
        set_frame = ttk.LabelFrame(self.root, text="Configuration")
        set_frame.pack(fill="x", **pad)

        ttk.Label(set_frame, text="HF Token (Pyannote):").grid(row=0, column=0, sticky="e", **pad)
        self.token_var = tk.StringVar(value=self.config_data["hf_token"])
        ttk.Entry(set_frame, textvariable=self.token_var, width=40).grid(row=0, column=1, columnspan=3, sticky="w", **pad)

        ttk.Label(set_frame, text="Max Speakers:").grid(row=1, column=0, sticky="e", **pad)
        self.speakers_var = tk.IntVar(value=self.config_data["max_speakers"])
        ttk.Spinbox(set_frame, from_=1, to=50, textvariable=self.speakers_var, width=5).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(set_frame, text="Confidence Margin:").grid(row=1, column=2, sticky="e", **pad)
        self.conf_var = tk.DoubleVar(value=self.config_data["confidence"])
        # --- ADDED: Adjusted lower bound to 0.0 so users can set 0% margin if they want
        ttk.Spinbox(set_frame, from_=0.0, to=1.0, increment=0.05, textvariable=self.conf_var, width=5).grid(row=1, column=3, sticky="w", **pad)

        ttk.Label(set_frame, text="Max Workers:").grid(row=2, column=0, sticky="e", **pad)
        self.workers_var = tk.IntVar(value=self.config_data["workers"])
        ttk.Spinbox(set_frame, from_=1, to=10, textvariable=self.workers_var, width=5).grid(row=2, column=1, sticky="w", **pad)

        self.hybrid_var = tk.BooleanVar(value=self.config_data["hybrid"])
        ttk.Checkbutton(set_frame, text="Use Hybrid Emotion", variable=self.hybrid_var).grid(row=2, column=2, columnspan=2, sticky="w", **pad)

        ttk.Label(set_frame, text="Source Lang:").grid(row=3, column=0, sticky="e", **pad)
        self.source_lang_var = tk.StringVar(value=self.config_data.get("source_lang", "ja"))
        ttk.Combobox(set_frame, textvariable=self.source_lang_var, values=SUPPORTED_LANGS, state="readonly", width=5).grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(set_frame, text="Target Lang:").grid(row=3, column=2, sticky="e", **pad)
        self.target_lang_var = tk.StringVar(value=self.config_data.get("target_lang", "en"))
        ttk.Combobox(set_frame, textvariable=self.target_lang_var, values=SUPPORTED_LANGS, state="readonly", width=5).grid(row=3, column=3, sticky="w", **pad)

        self.force_clean_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(set_frame, text="Force Clean Build", variable=self.force_clean_var).grid(row=4, column=0, columnspan=2, sticky="w", **pad)

        # --- Execution & Logs ---
        exec_frame = tk.Frame(self.root)
        exec_frame.pack(fill="x", **pad)

        self.start_btn = ttk.Button(exec_frame, text="START DUBBING PIPELINE", command=self.start_pipeline)
        self.start_btn.pack(pady=10)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(exec_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", padx=10)

        log_frame = ttk.LabelFrame(self.root, text="Console Output")
        log_frame.pack(fill="both", expand=True, **pad)

        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', bg="black", fg="lightgreen", font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)

    def write_log(self, msg):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def check_queues(self):
        while not self.log_queue.empty(): self.write_log(self.log_queue.get())
        while not self.progress_queue.empty(): self.progress_var.set(self.progress_queue.get())
        self.root.after(100, self.check_queues)

    def start_pipeline(self):
        if self.is_running: return

        try:
            raw_conf = float(self.conf_var.get())
            if raw_conf > 1.0 and raw_conf <= 100.0:
                raw_conf = raw_conf / 100.0
                self.conf_var.set(raw_conf) # Correct it in the UI
            elif raw_conf > 1.0 or raw_conf < 0.0:
                messagebox.showwarning("Invalid Margin", "The confidence margin must be a decimal between 0.0 and 1.0 (e.g., 0.10 for 10%).")
                return
            final_conf_thresh = raw_conf
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid number for the confidence margin.")
            return

        self.config_data = {
            "hf_token": self.token_var.get(),
            "max_speakers": self.speakers_var.get(),
            "confidence": final_conf_thresh, # --- ADDED: Use the validated variable here
            "workers": self.workers_var.get(),
            "hybrid": self.hybrid_var.get(),
            "source_lang": self.source_lang_var.get(),
            "target_lang": self.target_lang_var.get(),
            "out_dir": self.out_dir_var.get(),
            "out_name": self.out_name_var.get()
        }

        try:
            with open(CONFIG_FILE, "w") as f: json.dump(self.config_data, f)
        except Exception as e: self.log_queue.put(f"Warning: Could not save config: {e}")

        v_file = self.video_var.get()
        src_file = self.src_srt_var.get()
        tgt_file = self.tgt_srt_var.get()
        if not v_file or not src_file or not tgt_file:
            self.log_queue.put("ERROR: Please select a Video, Source SRT, and Target SRT file.")
            return

        self.is_running = True
        self.start_btn.config(state="disabled")
        self.progress_var.set(0)

        config = PipelineConfig(
            video_file=Path(v_file),
            source_srt_file=Path(src_file),
            target_srt_file=Path(tgt_file),
            source_lang=self.source_lang_var.get(),
            target_lang=self.target_lang_var.get(),
            output_file=Path(self.out_dir_var.get()) / self.out_name_var.get(),
            token=self.token_var.get(),
            max_speakers=self.speakers_var.get(),
            confidence=final_conf_thresh,
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
        self.is_running = False
        self.root.after(0, lambda: self.start_btn.config(state="normal"))

if __name__ == "__main__":
    mp.freeze_support()
    try: mp.set_start_method('spawn', force=True)
    except RuntimeError: pass

    root = tk.Tk()
    if darkdetect.isDark(): sv_ttk.set_theme("dark")
    else: sv_ttk.set_theme("light")
    app = DubbingApp(root)
    root.mainloop()
