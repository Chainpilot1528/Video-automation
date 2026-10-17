# Installation

## Supported environment

- macOS 15, on Apple Silicon or Intel. The current dev machine is a **2019 Intel MacBook Pro (i5, 8 GB)**.
- Python 3.11 or newer (tested with 3.14.7).
- FFmpeg and ffprobe on `PATH`. Needed from Phase 5 onward; `pipeline doctor` reports FAIL until they are installed.

## 1. Python environment

From the repo root:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[dev]"
```

For exact versions, install from the lock file first:

```bash
.venv/bin/pip install -r requirements-lock.txt && .venv/bin/pip install -e . --no-deps
```

Check it:

```bash
.venv/bin/pipeline doctor
```

No models are downloaded and no ML packages are installed by these steps.

## 2. FFmpeg via MacPorts (you run the password steps)

Homebrew now supports Apple Silicon only, so this Intel Mac uses **MacPorts**. Installed on this machine on 2026-10-17: MacPorts 2.12.7 and FFmpeg 9.0.2.

1. Download the macOS 15 Sequoia installer from <https://www.macports.org/install.php>. Check that it's signed and notarized:
   ```bash
   pkgutil --check-signature ~/Downloads/MacPorts-2.12.7-15-Sequoia.pkg
   ```
2. Install it, either by double-clicking it or with:
   ```bash
   sudo installer -pkg ~/Downloads/MacPorts-2.12.7-15-Sequoia.pkg -target /
   ```
3. Open a **new** Terminal window, so `/opt/local/bin` is on PATH. Then:
   ```bash
   sudo port selfupdate && sudo port -N install ffmpeg
   ```
4. Verify:
   ```bash
   .venv/bin/pipeline doctor
   ```

Notes:
- `doctor` and the pipeline also look in `/opt/local/bin` directly, for apps that don't load `~/.zprofile`.
- MacPorts' FFmpeg is built with GPL components (x264, x265). Running it locally to render your videos is fine; the licence matters only if you redistribute FFmpeg itself.
- The first run of a freshly installed `ffmpeg` can be slow while macOS scans it.
- The Terminal panel inside the Claude app didn't pass `sudo` password input through. Use the separate Terminal app for password prompts.

## Intel Mac notes

- There is no Metal/MLX/Neural Engine acceleration. Local LLMs (Ollama), local TTS (e.g. Kokoro) and diffusion models run on the CPU and are slow. Benchmark them in Phase 9 before relying on them.
- FFmpeg encoding uses 4 cores. Use the preview profile while iterating and render the 1080p master only at the end.
- With 8 GB of memory, run one heavy job at a time: render, local model, or editor.

## Disk and storage

- Keep at least 25 GiB free for media work. `doctor` warns below `PIPELINE_WARN_FREE_DISK_GB` (default 25) and fails below `PIPELINE_MIN_FREE_DISK_GB` (default 10).
- Large media, renders and model weights are git-ignored. Set `PIPELINE_MEDIA_ROOT` to move media to an external drive.
- Do not keep projects in iCloud-synced folders. iCloud storage on this Mac is full, and syncing large media fails or evicts files.

## Configuration

Settings come from `PIPELINE_*` environment variables. See `.env.example` for the full list and defaults.
