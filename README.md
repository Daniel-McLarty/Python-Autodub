# Python Autodub

An automated, AI-powered video dubbing pipeline that extracts audio, separates vocals from background noise (using Demucs), diarizes speakers (using Pyannote), and generates translated voice clones (using Coqui XTTSv2). It then re-assembles the audio and muxes it back into a final MKV video file.

## Features
* **Vocal Separation:** Isolates background noise and music from dialogue using 4-stem Demucs.
* **Speaker Diarization:** Identifies up to 22 different speakers in the audio using Pyannote.
* **Voice Cloning:** Automatically extracts clean samples for each identified speaker and uses XTTSv2 to generate translated English lines.
* **Hybrid Cloning:** Optional setting to blend the original emotional cadence of the Japanese/source vocals with the base voice clone.
* **Graphical Interface:** Easy-to-use Tkinter GUI to configure thresholds, workers, file paths, and output settings (with native Windows 11 Light/Dark theming).
* **Smart Resume & Caching:** Automatically hashes input files to detect changes, allowing the pipeline to seamlessly resume interrupted jobs and skip heavy processing steps, saving hours of GPU time.

## Smart Resume & File Hashing
To save processing time and GPU resources, AutoDub features an intelligent caching system:
* **State Detection:** When you start the pipeline, the app calculates an MD5 hash of your input Video and SRT files in chunks (to prevent memory overloads).
* **Seamless Resuming:** If the hashes match your previous run, the pipeline safely skips the heavy extraction, Demucs separation, and Pyannote diarization steps. It will resume directly from where it left off, only generating TTS lines that don't already exist in the `temp/` folder.
* **Automatic Purging:** If you select a new video or edit your SRT file, the app detects the hash mismatch and automatically wipes the `temp/` directory to prevent audio contamination.
* **Force Clean Build:** You can manually override the caching system at any time by checking "Force Clean Build (Wipe Temp)" in the UI to guarantee a fresh run.

## Prerequisites
1. **NVIDIA GPU:** A CUDA-compatible GPU is highly recommended (and practically required) for XTTSv2, Demucs, and Pyannote to run in a reasonable timeframe.
2. **Python 3.9 - 3.11:** Recommended Python version.
3. **Hugging Face Account:** You need a Hugging Face token to use Pyannote. You must also visit the following pages while logged in to accept their user conditions:
   * [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   * [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)

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

## Installation

### Windows
Run `uv sync --extra cu121` to set up the environment.
Or you can also use the `Python-Autodub.exe` found in the project root directory directly.
You can also download a zip folder of a Windows release on the GitHub Releases page.

### Linux
Run the following commands in your terminal: `uv sync --extra cu121`

## Usage

- Run `uv run --extra cu121 src/ui.py`
(Alternatively, configure the variables inside `src/run_dub.py` and run `uv run --extra cu121 src/run_dub.py` for a headless CLI experience).
Additionally, Windows users can just run Python-Autodub.exe and avoid any manual python setup.

## Folder Structure & Artifacts
To keep the root directory clean, the project organizes files dynamically:
-   `src/`: Contains all python scripts and base voice templates.
-   `temp/`: Generated during execution. Holds all intermediate files including separated vocals (`separated/`), voice samples (`base_clones/`), individual generated lines (`temp_lines/`), and intermediate audio mixing tracks (`full_audio.wav`, `final_background_noise.wav`, `final_dialogue.wav`, `mixed.wav`).
-   `output/`: Generated upon completion. Contains the final `FINAL_DUBBED_MOVIE.mkv`.
