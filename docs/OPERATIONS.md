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
- **`voicebox`** is a local, offline [Voicebox](https://github.com/jamiepine/voicebox) app (setup in `docs/INSTALL.md`). Voices are Voicebox profiles, or `kokoro:<voice_id>` for a Kokoro preset (`pipeline narration voices --provider voicebox`). Rights are decided per voice:
  - **Kokoro preset voices** are cleared: the model is Apache-2.0. Their narration is registered `commercial_use: allowed`, `pending_review`, and still needs `pipeline assets review`.
  - **Cloned voices** are blocked until the voice owner's written consent is recorded in `rights_evidence` and the asset is reviewed. Only clone your own voice, or a voice whose owner has agreed in writing.
  - **Designed voices and other engines** (Chatterbox, Qwen, LuxTTS, TADA) are blocked until their model licence has been reviewed and added to `REVIEWED_ENGINES`.
  - Non-local Voicebox URLs are refused unless `PIPELINE_ALLOW_NETWORK=true` is approved.
- Other providers, such as hosted TTS services, plug in through `providers/tts/base.py` after a licence and cost review (Phase 9).

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

### Voice styles and presets

- `--style documentary` processes the voice like a documentary narration: rumble cut, warmth, de-mud, presence lift, gentle de-essing, 3:1 compression, a barely-there room, and a limiter at about -1.5 dBFS (auto-level off). It applies to TTS and to your own recordings, and it's part of the cache key, so editing a style rebuilds only what used it.
- `--style annt` is the documentary chain plus a **tone-matching EQ** measured against the ANNT reference (fuller low-mids, less 1.6–2.5 kHz "honk", more presence above 4 kHz). The average band gap dropped from 5.4 dB to 2.5 dB.
- `--preset reckoner` (the channel's house narrator, named 2026-10-20; `--preset annt` is an alias and sounds identical) is shorthand for `--provider voicebox --voice kokoro:am_liam --speed 0.87 --style annt`. It's tuned to the **style** of the ANNT reference (`references/ANNT/`): male, about 133 Hz median pitch, about 165 words/min, about -20.5 LUFS. It is **not** a clone of that narrator, and the pipeline won't clone a voice without the owner's consent. Explicit options override the preset's values.

```bash
.venv/bin/pipeline narration build projects/my-film --preset reckoner
```

### Per-scene pacing

Two optional fields in `scenes.json`:
- `narration_speed` (0.7–1.3) multiplies the TTS speed for one scene. Use it to slow down for dramatic lines (0.93–0.97) or speed up through lists (1.03). It's part of the cache key, so only that scene rebuilds.
- `hold_after_seconds` (0–5) sets how long the picture holds after the narration ends, replacing the default 0.5 s. Use it for a breath between ideas, or a longer final hold.

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

## Rendering (Phase 7)

```bash
.venv/bin/pipeline timeline build projects/my-film
```

```bash
.venv/bin/pipeline render preview projects/my-film --burn-captions
```

```bash
.venv/bin/pipeline render master projects/my-film
```

| Profile | Size | Encoding | Rules |
|---|---|---|---|
| `preview` | 960×540 | x264 veryfast, CRF 28, AAC 128k | placeholders allowed; scenes without narration play silently for their planned estimate |
| `master_16x9` | project resolution (1920×1080) | x264 medium, CRF 18, AAC 192k | every narrated scene needs measured audio; no placeholders |
| `vertical_9x16` | — | — | Phase 11, after the landscape master is approved |

- `timeline build` compiles `reports/timeline-<profile>.json` (scene starts, durations, segments, fades, cues) without rendering. Use `render … --dry-run` to do the same before a render.
- Rendering first re-validates the whole project **including asset checksums**, and refuses changed files.
- Each scene renders to `renders/<profile>/scenes/<scene>-<fingerprint>.mp4`. Unchanged scenes are reused, so editing one scene re-renders only that scene.
- The final file is `renders/<profile>/<project>-<profile>-<fingerprint>.mp4`, checked for duration, size, frame rate, codecs and audio rate before it's promoted. Earlier renders are kept.
- Sidecar captions on the final timeline sit next to the video (`.srt`). `--burn-captions` also draws them onto the picture in a readable box.
- On-screen labels for generated visuals and reconstructions are always drawn.
- `slow_push` and `pan` motion are rendered. `reveal`, `highlight` and `build` are shown static, with a warning, until they're authored as animated graphics.
- Music isn't mixed yet. Narration plays at its recorded level; final loudness levelling comes with the audio-mix work.
- **On failure**, the error names the scene. Its FFmpeg log is in `renders/<profile>/logs/<scene>.log`, and a `status: failed` render report is written. Fix the input and re-run: finished scenes are reused.
- Disk space is checked before rendering. Superseded scene and final files are never auto-deleted; remove old `renders/` folders yourself when you need the space.

## Music bed

```bash
.venv/bin/pipeline music pad projects/my-film --id music-pad
```

```bash
.venv/bin/pipeline music set projects/my-film music-pad --gain-db -6
```

- `music pad` synthesizes an **original** ambient bed: a minor add-9 chord, slow breathing, a soft low pulse every 4 s and filtered "air". It has no samples, so it's rights-clear and can't match Content ID. It's registered as a `music` asset, pending review. The default length is the narration length plus 10 s. Use `--key A|C|D|E` to change the key.
- `music set` puts any registered `music` asset under the whole video. That includes a licensed track added with `pipeline assets add --type music`, which needs `platform_cleared` before approval. `--gain-db` sets the bed level, and `--no-duck` turns ducking off. `music clear` removes it.
- Rendering joins the scenes, then runs one audio-only pass: the bed is looped to length, faded in and out, **ducked under the narration** with a sidechain compressor, mixed, and limited. Video is copied untouched. Changing the music re-runs only this pass; scene renders are reused.
- The music asset counts as "used" in `assets report`, so it must be approved before `publication_ready`.

## QA and sign-off (Phase 8)

```bash
.venv/bin/pipeline qa report projects/my-film
```

- Checks the latest **master** render (`--profile preview` for a preview) and every publication gate. It writes `reports/qa-master_16x9.json` and a readable `reports/qa-master_16x9.md` with the human review checklist, and exits 1 while blockers remain.
- One FFmpeg pass measures loudness, true peak, silences, and black and frozen picture. It takes about 4 s for a 4-minute 540p preview. `--skip-media` skips this pass, but such a report can't be signed off.
- Fix blockers. Fix or waive warnings: `pipeline qa waive <project> "<code>@<subject>" --by NAME --rationale "..."`.
- Watch the master, work through the checklist, then `pipeline qa signoff <project> --by NAME --checklist-done`. The project becomes `publication_ready`. Upload it yourself; nothing is published automatically.
- Details and thresholds: `docs/EDITORIAL_QA.md`.

