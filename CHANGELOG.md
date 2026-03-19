# Changelog

## [v0.9.3] - 2026-03-05
*(Developer Note: This is a massive structural update masquerading as a patch version! Paving the way for the v1.0.0 Installer release.)*

### Setup & Deployment
* **Deterministic Environment Locking:** Replaced the loose `requirements.txt` with a strict lock-file system using `uv`. Setup is now 100% reproducible across machines, eliminating "works on my machine" dependency conflicts.
* **Cache-Busting Installer:** `setup.bat` now uses `--no-cache-dir` to prevent corrupted or outdated local packages from breaking fresh installations.
* **Automated CUDA Resolution:** PyTorch `+cu121` packages are now automatically resolved during dependency locking via strict index-url injection.
* **Zero-Config FFmpeg (Windows):** Users no longer need to manually install FFmpeg or edit system Environment Variables. The app now dynamically injects a local `bin/` folder into the runtime PATH.
* **Developer QOL Script:** Added `versioning.bat` to automate the process of freezing the environment (`base.txt`) and safely compiling the final deployment requirements.

### Portability & Model Management
* **Fully Portable Architecture:** AI models no longer download to hidden system folders (e.g., `%USERPROFILE%\.cache`). Overrode `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME`, and `TTS_HOME` to force all multi-gigabyte models into a local `models/` directory in the project root.
* **Fixed Download Race Conditions:** Resolved a critical bug where parallel multiprocessing workers would simultaneously attempt to download the XTTSv2 model, corrupting the files.
* **Smart Pre-Fetching (Step 4.5):** The main thread now safely pre-fetches the TTS model single-handedly (or verifies its existence on disk) before spinning up background workers.

### UI & User Experience
* **Persistent UI Memory:** Implemented `ui_config.json` to save user state. The application now remembers your Hugging Face token between sessions.
* **Coqui CPML License Integration:** Fixed an `EOFError` crash caused by Coqui TTS attempting to request license agreement via standard input inside headless worker threads.
* **GUI License Checkbox:** Added a formal TOS agreement checkbox to the UI and a CLI prompt to `run_dub.py`.
* **TOS State Saving:** License agreements are now written to a hidden `.tos_agreed` file, permanently suppressing the console prompt for future runs.

### Refactoring & Repo Maintenance
* **Strict Import Ordering:** Completely refactored the top of `run_dub.py`, `ui.py`, and `test_env.py`. Environment variables and path overrides are now strictly defined *before* heavy AI libraries (`torch`, `pyannote`) are imported to prevent initialization lock-in.
* **Repository Clean-Up:** Updated `.gitignore` to safely ignore the new `models/` directory and `ui_config.json`.
* **Documentation:** Updated the `README.md` to reflect the new simplified setup instructions and modernized architecture.

## [v1.0.0] - 2026-03-05

(Developer Note: The "One-Click" Milestone. This release transforms the project from a developer-centric script collection into a portable, user-friendly Windows application.)

### Distribution & Portability

-   Standalone Executables: Introduced `AutoDub-UI.exe` and `AutoDub-Tester.exe`. Users can now run the application directly without manually installing Python, Git, or managing system paths.

-   Auto-Bootstrapping Engine: Integrated a high-performance PowerShell launcher that automatically handles `uv` installation, Python 3.10 fetching, and virtual environment management on the first run.

-   Hermetic Environment (`dub_env`): The application now builds its own isolated Python environment locally within the project root, ensuring zero interference with existing system-wide Python installs.

## [v1.0.0] - 2026-03-07

### Bug  Fixes

- The Windows exe works without printing incorrect errors to the screen.
- The Windows exe now saves install state to load quicker on future loads.

## [v1.1.0] - 2026-03-08
*(Developer Note: The "Quality of Life & Architecture" Update. A massive refactor separating the GUI from the AI logic, alongside highly requested features like dark mode, smart resuming, and full state saving.)*

### UI & User Experience
* **Native OS Theming:** Integrated `sv_ttk` and `darkdetect` to automatically apply a modern Windows 11 Light/Dark theme based on the user's system preferences.
* **Full UI State Persistence:** Expanded `ui_config.json` functionality. The app now remembers all configuration settings (workers, max speakers, output paths, etc.) between sessions, rather than just the Hugging Face token.
* **Custom Output Controls:** Added dedicated UI fields allowing users to specify the exact output directory and filename for the final dubbed MKV.
* **Force Clean Build:** Added a checkbox to manually purge the `temp/` directory (safely preserving logs) for users wanting to guarantee a fresh pipeline run.

### Pipeline Intelligence & Logging
* **Smart Resume via File Hashing:** Implemented MD5 chunk-hashing for input video and SRT files. The pipeline now detects if inputs have changed; if they match the previous run, it safely resumes using existing isolated stems and cloned voices, saving significant processing time.
* **Enhanced Worker Logging:** Modified the parallel worker return tuples to pass subtitle text back to the main thread. Logs now explicitly print the text of the line being generated (e.g., `[Worker] Successfully generated Line 42: "Hello world"`).

### Architecture & Refactoring
* **Separation of Concerns:** Broke apart the UI "God Class." Extracted all backend FFmpeg, Demucs, Pyannote, and TTS logic into a dedicated, standalone `DubbingPipeline` class to prevent UI freezing and improve maintainability.
* **Strict Configuration Typing:** Replaced generic dictionary passing with a `PipelineConfig` dataclass, ensuring strict type-checking and IDE auto-completion for pipeline variables.
* **Pathlib Migration:** Refactored all internal directory and file management to use Python's built-in `pathlib` instead of `os.path`, eliminating cross-platform slash escaping issues (especially around Demucs).

## [v1.2.0] - 2026-03-09

### Project Management & Deployment
* **Everything is UV:** Fully migrated dependency management to a strict `pyproject.toml` standard.

## [v1.2.1] - 2026-03-09
*(Developer Note: The "Native Build & Audio Polish" Update. Did some bulletproofing of the deployment process for users without development environments. Also fixed some diva behavior from FFmpeg!)*

### Project Management & Deployment
* **Automated MSVC Build Tools Installer:** The PowerShell launcher now uses `vswhere.exe` to check for C++ build environments. If missing, it automatically downloads and passively installs the required Visual Studio C++ workloads, preventing `uv` from crashing when compiling C-extensions from source.

### Audio Pipeline Improvements
* **Better Audio Mixing (LUFS Calibration):** Fixed an issue where the background music/noise was aggressively loud. Lowered the background normalization target from `-14 LUFS` to `-26 LUFS`, ensuring the background track sits comfortably underneath the `-12 LUFS` focal dialogue track.
* **Custom FFmpeg Upgrade:** Updated the minimal MSYS2 FFmpeg build configuration to explicitly include the `atempo` filter (`--enable-filter=...,atempo`), enabling native WSOLA time-stretching while keeping the binary ultra-lightweight.

### Bug Fixes
* **Resilient Audio Assembly (Step 6):** Fixed a critical bug where the pipeline would silently fail to merge dialogue if FFmpeg couldn't time-stretch a line (resulting in a completely blank dialogue track). Switched `subprocess.run` to `run_and_log` to catch errors, and added a safe fallback that inserts the original, unadjusted TTS audio if the `_adj.wav` file fails to generate.

## [1.2.2] - 2026-03-11

### Bug Fixes
* **Build Environment:** Fixed a bug in Test-MSVCBuildTools where the script failed to detect existing Visual Studio Community/Pro/Enterprise installations, causing redundant downloads of MSVC Build Tools.
* **Detection Logic:** Updated vswhere query to use the -products * flag and version pinning [17.0, 18.0) to correctly identify Visual Studio 2022 environments.

## [2.0.0] - 2026-03-11
### The "Next-Gen Audio" Overhaul
Version 2.0.0 is a complete architectural rebuild of the Python Autodub pipeline, focusing on state-of-the-art voice generation, strict audio-sync safety nets, and seamless cross-platform deployment.

### Added
* **F5-TTS Integration:** Completely replaced Coqui XTTSv2 with the transformer-based F5-TTS model, drastically improving prosody, emotion, and generation speed.
* **Smart Diarization Bypass:** The pipeline now automatically bypasses the Pyannote Diarization model entirely when `Max Speakers` is set to 1, saving ~3GB of VRAM and significantly reducing processing time.
* **Absolute Margin Speaker Logic:** Introduced a robust math system for multi-speaker overlap. The pipeline now compares the ratio of overlapping speakers and assigns voices based on the user-defined `Confidence Margin` (default 10%), preventing background noises from stealing clones.
* **The "Guillotine" Assembly Step:** Added intelligent time-shrinking via `librosa`. If F5-TTS hallucinates extra audio, the pipeline uses a phase vocoder to safely speed the audio up (max 2x). If it still exceeds the subtitle window, the tail is hard-truncated to guarantee it never bleeds into the next line.
* **Pre-Speech Auto-Trimming:** Added an aggressive `top_db=35` trim to the start of all generated lines to eliminate AI "warm-up" latency and ensure frame-perfect lip sync.
* **Native Launchers:** Replaced `test_env.py` and `run_dub.py` with native OS deployment scripts:
  * `Launch_UI.ps1` / `.exe` for Windows (includes automatic MSVC Build Tools detection and installation).
  * `Launch_UI.sh` / `install_linux_shortcut.sh` for Linux (includes distro-agnostic C++ compiler checks and native `.desktop` app grid integration).
* **Console Spam Suppression:** Redirected F5-TTS inference logs to `os.devnull` (with UTF-8 encoding support) to keep the parent shell clean during generation.
* **Hugging Face Progress Bars:** Added a custom `sys.stderr` interceptor to capture and display Hugging Face model download progress directly inside the Tkinter GUI (updating once per second).

### Changed
* **Audio Backend Engine Swap:** Completely removed `pydub`. The entire pipeline now relies purely on `numpy`, `soundfile`, and `librosa` for frame-accurate audio manipulation, resolving cross-drive caching issues and millisecond-rounding drift.
* **Environment Management:** Transitioned from `pip` to `uv` for lightning-fast, reproducible dependency syncing.
* **VRAM Management:** Added aggressive `gc.collect()` and `torch.cuda.empty_cache()` commands between major pipeline steps (e.g., after WhisperX diarization) to prevent Out-Of-Memory (OOM) crashes on long videos.
* **Hallucination Mitigation:** The pipeline now automatically forces terminal punctuation (e.g., a period) onto the end of open-ended subtitles to explicitly trigger the F5-TTS stop token.
* **Hybrid Clone Optimization:** The Base Clone auditor now strictly filters for shorter 4-to-7-second reference audio chunks when Hybrid mode is active, preventing F5-TTS from exceeding its context window and hallucinating.

### Removed
* Removed `pydub` from all dependencies.
* Removed legacy `run_dub.py` headless script (functionality absorbed by the UI and config system).
* Removed `test_env.py` (environment validation is now handled natively by the OS launchers).
