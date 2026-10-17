# Architecture

## Principles

- **Manifests are the source of truth.** Versioned JSON files, validated by Pydantic models, describe every production. Code reads and writes them, never hidden state.
- **Humans decide.** Claim reviews, script and asset approvals are recorded with a name, a time and a fingerprint of what was reviewed (`approvals.json`). Nothing is published automatically.
- **Providers are adapters.** TTS, LLM and image generation sit behind interfaces. The free, local, manual route always works, and nothing external runs unless it's explicitly enabled.
- **Measure, don't guess.** Durations come from audio (ffprobe). Planned durations are estimates only.
- **Never overwrite.** Originals are read-only. Generated outputs are named by an input fingerprint, and every write is atomic.

## Modules (`src/reckoning_pipeline/`)

| Module | Responsibility |
|---|---|
| `cli.py` | Typer CLI; exit codes 0/1/2/3/4 |
| `config.py`, `logging_utils.py`, `doctor.py` | `PIPELINE_*` settings, structured logs, environment checks |
| `schemas/` | All data contracts: project, scenes, research ledger, assets, approvals, narration, visuals, timeline, render report |
| `project/` | Scaffolding, whole-project validation (references, paths, checksums, status gates), migrations |
| `approvals.py` | Fingerprints and derived approval state (script, claim exceptions, assets) |
| `research/` | Research report, ledger import and review, bibliography, LLM-suggestion guardrails |
| `script/` | Script readiness checks, approve and revoke |
| `assets/` | Manual intake (read-only originals), derivatives, rights review, rights report, credits |
| `media/` | FFmpeg/ffprobe discovery, audio measurement and normalization, video probing |
| `narration/` | Per-scene narration build (imported takes, then optional TTS) |
| `subtitles/` | Caption segmentation, timing, SRT parsing and validation, aligner interface |
| `graphics/` | Deterministic SVG graphics from specs |
| `visuals/` | Visual-plan report, placeholders, HTML contact sheet |
| `timeline/` | **Pure** compiler: manifests → `TimelinePlan` |
| `render/` | Profiles, FFmpeg command builders (pure), runner (execute, cache, concat, validate, report) |
| `providers/{llm,tts,image}` | Adapter interfaces. Only macOS `say` (preview-only) is implemented |

## Data flow

```text
brief.md, script.md ──► research/ledger.json ──► research report ──► script approve ─┐
                                                                                     │ approvals.json
assets add/derive ──► assets/registry.json ──► assets review ────────────────────────┤ (fingerprinted)
                                                                                     │
scenes.json ──► narration build ──► narration/<scene>/<fp>.wav + reports/narration.json
            │                     └─► scenes.actual_narration_duration_seconds
            ├─► captions build ──► captions/<id>.<lang>.srt
visuals.json ─┤
graphics render ─► assets/graphics/*.svg
            ▼
timeline compiler (pure) ──► reports/timeline-<profile>.json
            ▼
render runner ──► renders/<profile>/scenes/<scene>-<fp>.mp4 ──► concat ──► <id>-<profile>-<fp>.mp4 (+ .srt)
                                                                         └─► reports/render-<profile>-<time>.json
```

## Provider boundaries

| Interface | File | Enabled by default | Implementations |
|---|---|---|---|
| LLM | `providers/llm/base.py` | no | none yet (Phase 9) |
| TTS | `providers/tts/base.py` | only when `--provider` is given | `macos-say` (offline, not commercially cleared, so its output is blocked from publication) |
| Image/video generation | `providers/image/base.py` | no | none (placeholders instead) |

Each adapter declares `sends_data_externally` and `commercial_use_cleared`. Output that isn't cleared is registered as `commercial_use: not_allowed` and can never be approved.

## Cache model

The same principle applies at every level: **reuse only when the full input fingerprint is unchanged.** Modification times are never trusted.

| Level | Fingerprint covers | Output |
|---|---|---|
| Narration chunk | text after pronunciation overrides (or take checksum), provider, voice, provider version, rate, sample rate, normalizer version | `narration/<scene>/<fp16>.wav` |
| Scene render | segment asset checksums or placeholder text, timings, motion, labels, fades, narration checksum and duration, captions (if burned), profile, pipeline version, FFmpeg version, `RENDER_VERSION`, **hash of `render/commands.py`** | `renders/<profile>/scenes/<scene>-<fp16>.mp4` |
| Final render | list of scene fingerprints | `renders/<profile>/<id>-<profile>-<fp12>.mp4` |
| Approvals | script: narration + used claims. Claim exception: claim text, status, sources. Asset: checksum + rights fields | `approvals.json` entries become *stale* when content changes |

A cached scene must also still probe to its expected duration with an audio stream. Changing one scene re-renders only that scene, plus the cheap concat.

## Timing model

- Narrated scene = 0.25 s lead-in + measured narration + 0.5 s tail hold. Silent scene = planned duration (default 3 s).
- Transitions happen inside each scene's own time (fade in at the start, fade out at the end; a dissolve is a dip through black). Scenes butt-join, so total = sum of scenes, with no overlap to double-count.
- Beats within a scene follow explicit `offset_seconds` when every beat sets one; otherwise they split the scene evenly.
- Captions are placed per scene from measured speech (audio minus measured silence), offset by the scene's start and lead-in.

## Safety and reliability

- Subprocesses are argument arrays. Filtergraphs reference helper files by relative name with FFmpeg's working directory set, so no user text is interpolated into a filtergraph.
- Paths are resolved inside the project or media root, and symlink escapes are rejected.
- Picture inputs are decoded once before rendering, because FFmpeg's looped-image input can spin forever on a bad file. Every FFmpeg call has a timeout.
- Outputs go to `.partial` files, are checked with ffprobe, then renamed atomically. Failures keep logs (`renders/<profile>/logs/`) and intermediates, and write a failed render report. Re-running resumes from scenes that already succeeded.
- Nothing is deleted automatically. Superseded renders and narration files stay until a person removes them.
