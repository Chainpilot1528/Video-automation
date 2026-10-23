# Models: what the pipeline uses, and why

Every model below runs **on this Mac**. None is a paid cloud service, and no API key is needed. The internet is only used to download a model once, and to fetch public-domain images from museums.

Checked on 2026-10-23 against the code and the machine.

## At a glance

| Model | What it does | Runs in | Licence | Size | Status |
|---|---|---|---|---|---|
| **Kokoro-82M**, voice `am_liam` | Narration: the **Reckoner** voice | Voicebox app | Apache-2.0 | 346 MB | ✅ **In use** for all current videos |
| **Qwen3-TTS CustomVoice 0.6B**, voice `Ryan` | Narration: the **sage** voice (calm, deeper) | Voicebox app | Apache-2.0 | 2.4 GB | ⏸ Available, not used now |
| **U²-Net** (`u2net.onnx`) | Background removal for busts and objects (cut-outs) | OpenCV, in the pipeline | Apache-2.0 | 176 MB | ✅ **In use** (`archive cutout`) |
| **Qwen3 4B Instruct** (`qwen3:4b-instruct-2507-q4_K_M`) | Optional script drafts and research suggestions | Ollama app | Apache-2.0 | about 2.5 GB | ⏸ Installed, not used |
| **Qwen3 0.6B / 1.7B** | The same optional text jobs, inside Voicebox | Voicebox app | Apache-2.0 | 1.4 / 3.9 GB | ⏸ Installed, not used |
| macOS `say` | Quick timing previews only | macOS | Apple licence, **non-commercial** | built in | 🚫 Preview only, never publishable |
| Whisper base | Speech-to-text (to study a reference video) | Voicebox app | MIT | about 140 MB | ❌ Not installed (the download stalled and was cancelled) |
| Image or video generation | Making new pictures | none | — | — | ❌ None enabled, by design |

## Each model in more detail

### 1. Narration: Kokoro-82M, the "Reckoner" voice (in use)
- **Purpose:** reads the script aloud, scene by scene.
- **Setup:** `--preset reckoner --humanize`. That's Kokoro voice `am_liam` at speed 0.87, with the `annt` documentary EQ.
  - `--humanize` speaks one sentence at a time and adds natural pauses: a beat before short lines, a breath at "…", and varied paragraph gaps.
- **Why this one:** a natural adult male documentary voice that's fast on this Mac (a few seconds per scene) and free for commercial use.
- **Rule:** don't change the voice (speed, tone or processing). Improve the script and the visuals instead.
- **Not a clone:** it's style-matched to a reference, never a copy of a real narrator's voice.

### 2. Narration: Qwen3-TTS CustomVoice 0.6B, the "sage" voice (available)
- **Purpose:** an alternative, calmer philosophy-documentary voice (`--preset sage`, preset voice "Ryan").
- **Trade-off:** more expressive, but about 12× slower than real time on this Mac (roughly 35 minutes of generating for a 3-minute script).
- **Status:** not used since Reckoner was chosen.

### 3. Background removal: U²-Net (in use)
- **Purpose:** cuts a statue or object out of its museum photo backdrop, so it floats on the black canvas (for example *The Thinker*, the Epicurus bust, the pendulum clock).
- **How:** `pipeline archive cutout <project> <image> --id <new-id>`. It takes about a second.
- **Output:** the cut-out is saved as a new image derived from the original, and needs its own rights review.
- **Where:** `models/u2net/u2net.onnx`, which git doesn't track. The file's checksum is verified before every use.
- **Why OpenCV and not rembg:** rembg's runtime has no build for Intel Macs on Python 3.14, so the same model runs through OpenCV instead.

### 4. Text models: Qwen3 via Ollama or Voicebox (optional, not used)
- **Purpose:** `pipeline script draft` (a first draft of a script from the brief and research) and `pipeline research suggest` (a list of claims worth checking).
- **Safety:** their output goes to `script/drafts/` and `research/notes/` only, never into the research ledger. Every AI-suggested claim stays "unverified" until a person checks it.
- **Status:** turned off by default (`PIPELINE_LLM_PROVIDER=none`). The scripts for the recent videos were not written with these models.

### 5. macOS `say` (preview only)
- **Purpose:** an instant robot voice, just to check timing.
- **Why preview only:** Apple's licence doesn't allow commercial use, so the pipeline marks this audio "not allowed" and it can never be published.

### 6. Whisper (not installed)
- **Purpose:** turning speech into text. It was tried once to transcribe a reference video for style analysis.
- **What happened:** the download inside Voicebox stalled, so it was cancelled and the analysis used audio measurements instead.

### 7. Image generation (none)
- **Status:** no image or video generator is enabled.
  - Running one locally on this 8 GB Intel Mac isn't practical.
  - Hosted services cost money and send prompts off the machine.
- **Instead:** pictures come from **public-domain museum collections** (The Met and the Art Institute of Chicago, both CC0) and from our own drawings: maps, diagrams, figures, text.

## Services that are not models
- **The Met and Art Institute of Chicago APIs:** search and download public-domain artworks. Free, no key.
- **Pexels API:** licensed stock footage (needs a key). Not used in the archival-style videos.

## Who wrote what
- **Claude Code** (the AI assistant in this desktop app) built the pipeline code, drew the map designs, and wrote or adapted the scripts for the recent videos. That includes "Why Your Brain Hates Contradictions", adapted from the creator's own Substack essay.
- **Claude is not part of the pipeline:** the pipeline never calls Claude or any other cloud AI when it runs.
- **Research facts and quotations** were checked by Claude against the original sources. Each one still needs a **person's approval** (`pipeline research review`) before publishing.

## Switching or adding a model
- **Voice:** `pipeline narration build <project> --preset reckoner` (current) or `--preset sage`.
- **Text model (optional):** set `PIPELINE_LLM_PROVIDER=ollama` or `voicebox`.
- **A new model:** needs a licence check, a disk and memory check, and your approval before it's added. Its licence is recorded so the rights check can block anything that isn't cleared.
