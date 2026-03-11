# Python Autodub

An automated, AI-powered video dubbing pipeline that extracts audio, separates vocals from background noise (using Demucs), diarizes speakers (using Pyannote), and generates translated voice clones (using F5-TTS). It then re-assembles the audio using fast, frame-accurate numpy math and muxes it back into a final MKV video file.

Copyright (C) Daniel McLarty 2026

## Features
* **Vocal Separation:** Isolates background noise and music from dialogue using 4-stem htdemucs.
* **Speaker Diarization:** Identifies multiple speakers in the audio using Pyannote. (Automatically bypassed when targeting a single speaker to save massive amounts of VRAM).
* **Voice Cloning:** Automatically extracts clean samples for each identified speaker and uses F5-TTS to generate high-fidelity, translated lines.
* **Hybrid Cloning:** Optional setting to blend the original emotional cadence of the source vocals with the base voice clone.
* **Smart Audio Assembly:** Features a "Shrink-Only Guillotine" that uses phase vocoder time-stretching to strictly confine AI-generated audio to its exact subtitle window, preventing dialogue overlap.
* **Latency Auto-Trimming:** Automatically scans and trims dead air or low-volume rumbling from the start of generated lines to ensure frame-perfect lip-sync timing.
* **Graphical Interface:** Easy-to-use Tkinter GUI to configure thresholds, workers, file paths, and output settings (with native Windows 11 Light/Dark theming).
* **Smart Resume & Caching:** Automatically hashes input files to detect changes, allowing the pipeline to seamlessly resume interrupted jobs and skip heavy processing steps, saving hours of GPU time.

## Prerequisites
1. **NVIDIA GPU:** A CUDA-compatible GPU is required.
2. **Hugging Face Account:** You need a Hugging Face token to use the Pyannote diarization models. You must also visit the following pages while logged in to accept their user conditions:
   * [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   * [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
   * [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)

## FFmpeg Dependency & Licensing
To handle high-performance audio normalization and video muxing, this project utilizes **FFmpeg**.

### **Installation**
* **Windows:** A custom-built, optimized FFmpeg binary is included in the `bin/` folder. No additional installation is required.
* **Linux:** Please install FFmpeg via your system's package manager:
  * **Ubuntu/Debian:** `sudo apt update && sudo apt install ffmpeg`
  * **Fedora:** `sudo dnf install ffmpeg`
  * **Arch:** `sudo pacman -S ffmpeg`

### **Licensing & LGPL Compliance**
This software uses a custom build of **FFmpeg** licensed under the [GNU Lesser General Public License (LGPL) version 2.1](http://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).
* **No Changes:** We have not modified the FFmpeg source code.
* **License Text:** A copy of the LGPL v2.1 is provided in `bin/FFMPEG_LGPL`.
* **Build Instructions:** Details on how this binary was configured and compiled can be found in `bin/build_info.md`.
* **Source Code:** You can obtain the official FFmpeg source code at [ffmpeg.org](https://ffmpeg.org/download.html).

## Installation & Usage

Python Autodub uses `uv` for lightning-fast, reproducible dependency management. The included launchers will automatically detect your environment, download necessary build tools, and sync the CUDA-enabled libraries before launching the UI.

### Windows
1. Double-click `Python-Autodub.exe` (or run `Launch_UI.ps1` if running from source).
2. The launcher will automatically configure MSVC Build Tools, sync the `uv` environment, and launch the GUI.

### Linux
1. Open your terminal in the project root.
2. Run `bash install_linux_shortcut.sh` to automatically configure execution permissions and add the app to your desktop environment's application grid.
3. Launch "Python Autodub Studio" from your app menu, or run `src/Launch_UI.sh` directly from the terminal.

## Folder Structure & Artifacts
To keep the root directory clean, the project organizes files dynamically:
-   `src/`: Contains all python scripts, launchers, and base voice templates.
-   `temp/`: Generated during execution. Holds all intermediate files including separated vocals (`htdemucs/`), voice samples (`base_clones/`), individual generated lines (`temp_lines/`), and intermediate audio mixing tracks.
-   `output/`: Generated upon completion. Contains the final `FINAL_DUBBED_MOVIE.mkv`.
-   `.uv_cache/`: Localized package cache to support cross-drive hard linking and prevent phantom disk usage.
