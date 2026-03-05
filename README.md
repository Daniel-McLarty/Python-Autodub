# AI Auto-Dubbing Studio

An automated, AI-powered video dubbing pipeline that extracts audio, separates vocals from background noise (using Demucs), diarizes speakers (using Pyannote), and generates translated voice clones (using Coqui XTTSv2). It then re-assembles the audio and muxes it back into a final MKV video file.

## Features
* **Vocal Separation:** Isolates background noise and music from dialogue using 4-stem Demucs.
* **Speaker Diarization:** Identifies up to 22 different speakers in the audio using Pyannote.
* **Voice Cloning:** Automatically extracts clean samples for each identified speaker and uses XTTSv2 to generate translated English lines.
* **Hybrid Cloning:** Optional setting to blend the original emotional cadence of the Japanese/source vocals with the base voice clone.
* **Graphical Interface:** Easy-to-use Tkinter GUI to configure thresholds, workers, and file paths.

## Prerequisites
1. **NVIDIA GPU:** A CUDA-compatible GPU is highly recommended (and practically required) for XTTSv2, Demucs, and Pyannote to run in a reasonable timeframe.
2. **Python 3.9 - 3.11:** Recommended Python version.
3. **Hugging Face Account:** You need a Hugging Face token to use Pyannote. You must also visit the following pages while logged in to accept their user conditions:
   * [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   * [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)

## FFmpeg Dependency & Licensing

To handle high-performance audio normalization and video muxing, this project utilizes **FFmpeg**.

### **Installation**
- **Windows:** A custom-built, optimized FFmpeg binary is included in the `bin/` folder. No additional installation is required.
- **Linux:** Please install FFmpeg via your system's package manager:
  - **Ubuntu/Debian:** `sudo apt update && sudo apt install ffmpeg`
  - **Fedora:** `sudo dnf install ffmpeg`
  - **Arch:** `sudo pacman -S ffmpeg`

### **Licensing & LGPL Compliance**
This software uses a custom build of **FFmpeg** licensed under the [GNU Lesser General Public License (LGPL) version 2.1](http://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).

- **No Changes:** We have not modified the FFmpeg source code.
- **License Text:** A copy of the LGPL v2.1 is provided in `bin/FFMPEG_LGPL`.
- **Build Instructions:** Details on how this binary was configured and compiled can be found in `bin/build_info.md`.
- **Source Code:** You can obtain the official FFmpeg source code at [ffmpeg.org](https://ffmpeg.org/download.html).

## Installation

### Windows
Double-click `setup.bat` or run it from the command line. This will create a virtual environment named `dub_env` and install all dependencies.
*(Note: Ensure you have downloaded and installed FFmpeg and added it to your Windows Environment Variables).*

### Linux
Run the following commands in your terminal:
```bash
chmod +x setup.sh
./setup.sh
```

## Usage
1. Activate your virtual environment:

Windows: `dub_env\Scripts\activate`
Linux: `source dub_env/bin/activate`

2. Test your environment: `python src/test_env.py`

3. Run the GUI Application: `python src/ui.py`

(Alternatively, configure the variables inside `src/run_dub.py` and run `python src/run_dub.py` for a headless CLI experience).

## Folder Structure & Artifacts

### To keep the root directory clean, the project organizes files dynamically:
- src/: Contains all python scripts and base voice templates.
- temp/: Generated during execution. Holds all intermediate files including separated vocals (separated/), voice samples (base_clones/), individual generated lines (temp_lines/), and intermediate audio mixing tracks (full_audio.wav, final_background_noise.wav, final_dialogue.wav, mixed.wav).
- output/: Generated upon completion. Contains the final FINAL_DUBBED_MOVIE.mkv.
