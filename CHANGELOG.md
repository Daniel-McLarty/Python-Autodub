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
