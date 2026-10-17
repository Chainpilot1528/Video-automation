# Operations

The production workflow, phase by phase. Commands assume the repo root and `.venv`.

## Narration (Phase 5)

Narration is built **per scene**, and every duration is **measured from the audio**. Planned durations are estimates only and are never used for timing.

### Route 1: human narration (preferred)

Record each scene separately, then import it. The file is copied in, checksummed and kept read-only:

```bash
.venv/bin/pipeline narration import projects/my-film s01-cold-open ~/Recordings/s01.wav --creator "Your Name"
```

Re-record a scene by importing `--take 2`, `--take 3` and so on. The highest take is used, and earlier takes stay on disk.

### Route 2: TTS (optional)

```bash
.venv/bin/pipeline narration voices --locale en_IN
```

```bash
.venv/bin/pipeline narration build projects/my-film --provider macos-say --voice Rishi
```

- `macos-say` is free and offline, but Apple licenses its voices for **personal, non-commercial use only**. Its output is registered as `commercial_use: not_allowed` and `blocked`, so it's useful for timing previews but can never be approved for publication.
- A scene with an imported take always uses the take, even when `--provider` is given.
- Other TTS providers, such as a Kokoro-class local model or a hosted service, plug in through `providers/tts/base.py`. Each needs a licence review and approval before it's added (Phase 9).

### Build

```bash
.venv/bin/pipeline narration build projects/my-film --dry-run
```

```bash
.venv/bin/pipeline narration build projects/my-film
```

For each scene, the build:
1. Converts the audio to 48 kHz (or the project rate) mono 16-bit WAV, with 10 ms edge fades to prevent clicks at joins. Loudness is measured, not changed.
2. Writes `narration/<scene>/<fingerprint>.wav`. The name is a fingerprint of the text (after pronunciation overrides), take checksum, provider, voice, provider version, rate and audio settings. Unchanged scenes are reused, and no file is ever overwritten.
3. Measures duration (ffprobe), loudness (EBU R128 integrated LUFS and true peak) and leading, trailing and internal silence.
4. Updates the scene's `narration_asset_id` and `actual_narration_duration_seconds`. If the audio changed, it resets `caption_status` and `final_duration_seconds`.
5. Registers or updates asset `narr-<scene>`. Imported narration inherits the take's rights. Every narration asset still needs `pipeline assets review` before publication.
6. Writes `reports/narration.json`.

It warns about near-empty or silent audio, true peak above -1 dBTP, leading silence over 1 s, trailing silence over 1.5 s, pauses over 2 s, speaking rates outside 90–210 words/min (often a sign the audio doesn't match the text), large gaps between measured and planned duration, and loudness differing by more than 3 LU between scenes.

### Pronunciation overrides

`narration/pronunciations.json` changes what the TTS voice reads, without changing narration text or captions:

```json
{"schema_version": "1.0", "overrides": [
  {"term": "Ladakh", "say_as": "Luh-dahk"},
  {"term": "ISRO", "say_as": "Iss-ro", "case_sensitive": true}
]}
```

Longer terms are applied first, and matching respects word boundaries. Editing an override rebuilds only the scenes that contain the term.

## Captions (Phase 5)

```bash
.venv/bin/pipeline captions build projects/my-film
```

```bash
.venv/bin/pipeline captions validate projects/my-film/captions/my-film.en.srt
```

- Captions are written to `captions/<project>.<language>.srt`, from the approved `narration_text` and the measured audio.
- **Timing is approximate**, and recorded as `caption_status: approximate`. Each scene's cues span its measured speech, and time is shared between cues by character count. Cue boundaries inside a scene can be off by a second or so, but there is no cumulative drift, because every scene is anchored to its own measured audio.
- Cues are split at sentences, then clauses, then words: at most 2 lines of 42 characters. Validation flags overlaps, out-of-order cues, cues shorter than 0.7 s or longer than 7 s, and reading speeds above 20 characters/second.
- Caption times follow the narration timeline (scenes back to back). Phase 7 re-times them against the final edit.
- A forced aligner can be plugged in through `subtitles.srt.ForcedAligner` for word-accurate timing (`word_aligned`). None ships yet.
- If narration changes after captions were built, `captions build` refuses until `narration build` has been re-run.

## Visual planning (Phase 6)

Every narration beat gets a visual chosen down this hierarchy. It's a decision order, not a quota:

1. **Primary evidence**: documents, original data, real artifacts or footage that directly support the claim.
2. **Original graphics**: diagrams, charts, timelines, maps and screens that explain the mechanism.
3. **Licensed stock/archive**: context and atmosphere.
4. **Generated**: conceptual illustration or otherwise unavailable shots. Use a few high-impact ones, always labelled.
5. **Typography**: restrained text, when it improves clarity.

### The plan: `visuals.json`

Each beat records `beat_id`, `scene_id`, `order`, the `takeaway`, the `visual_question` it answers, `visual_type` (and `graphic_kind` for original graphics), `asset_ids`, the `source_ids` and `claim_ids` it shows, `requirements` while it's unresolved, `on_screen_text`, `motion` with a `motion_purpose`, optional timing, `is_reconstruction` with a `label`, an optional `generation` request, and `review_status`.

Rules enforced by the schema:
- Charts, timelines and maps must cite `source_ids`. Data is never invented.
- Primary evidence must reference the sources or claims it shows.
- Generated visuals and reconstructions must carry an on-screen `label` (for example "AI illustration" or "Reconstruction"). They're never passed off as genuine footage.
- Any motion needs a stated purpose: clarify, reveal evidence, guide attention, or pacing.
- An unresolved beat must say what it needs.

### Commands

```bash
.venv/bin/pipeline visuals report projects/my-film
```

```bash
.venv/bin/pipeline visuals sheet projects/my-film
```

```bash
.venv/bin/pipeline visuals placeholders projects/my-film
```

- `visuals report` lists every beat as resolved or unresolved, its rights state and its review state. It warns about scenes with no plan or no visual strategy, unresolved beats, precise or critical claims shown only with stock, generated or typographic visuals, beat/asset type mismatches, generated assets in unlabelled beats, on-screen text too long for a phone (over 42 characters or 14 words), and plans where more than a third of beats are generated.
- `visuals sheet` writes `reports/visuals.html`, a contact sheet of every scene's narration, beats, thumbnails, badges and gaps. Open it from the project's `reports/` folder.
- `visuals placeholders` writes red "PLACEHOLDER: NOT FOR PUBLICATION" frames to `visuals/placeholders/` for unresolved beats. They aren't assets, previews may show them, and QA blocks master renders containing them (Phase 8). The pipeline never silently substitutes unrelated media.
- `visuals generate` exits 3: no image provider ships. Local diffusion isn't practical on this Mac, and hosted services need cost and terms approval (Phase 9).

### Original graphics: `pipeline graphics render`

Deterministic SVGs from a JSON spec. The same spec always produces the same file:

```json
{"schema_version": "1.0", "asset_id": "s04-screen-time-chart", "kind": "bar_chart",
 "title": "Daily phone use by age", "source_ids": ["src-survey-2023"], "data_locator": "Table 2",
 "units": "h", "bars": [{"label": "13-17", "value": 4.8}, {"label": "18-29", "value": 3.9}],
 "intended_scene_ids": ["s04-evidence"]}
```

```bash
.venv/bin/pipeline graphics render projects/my-film specs/screen-time.json --dry-run
```

- Supported kinds: `title`, `bar_chart` (1–8 bars, zero-based, `data_locator` required) and `timeline` (2–6 events).
- Charts and timelines print their source citation in the frame, taken from the research ledger.
- The output goes to `assets/graphics/<asset_id>.svg` and is registered as an `original_graphic` asset with pending rights review. An existing file is never overwritten; give a changed graphic a new `asset_id`.
- Text sizes are chosen for phone legibility (body text at least 34 px at 1080p).
