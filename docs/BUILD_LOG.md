# Build Log

Phase status, decisions, tests, known issues, and next action. Newest entries at the bottom of each section.

## Phase status

| Phase | Status | Date |
|---|---|---|
| 0 — Discovery | PASS (approved by user) | 2026-10-17 |
| 1 — Python foundation and CLI | PASS (committed 5e6d735) | 2026-10-17 |
| 2 — Data contracts | PASS (committed d060526) | 2026-10-17 |
| 3 — Research, claim ledger, script approval | PASS (committed ea90b23) | 2026-10-17 |
| 4 — Asset sourcing, licensing, provenance | PASS (committed 98a99d6) | 2026-10-17 |
| 5 — Narration, timing, subtitles | PASS (committed a4b697e) | 2026-10-17 |
| 6 — Visual planning and provider adapters | PASS (committed bac1068) | 2026-10-17 |
| 7 — Timeline compiler and FFmpeg rendering | PASS (committed 601822a) | 2026-10-18 |
| 9 (early) — Voicebox TTS adapter | PASS (fake-server tests); live API reachable; Kokoro build pending model download | 2026-10-18 |
| 9 (early) — Pexels stock adapter | PASS (fake-API tests + live search) | 2026-10-18 |
| 9 (early) — AI script drafting (Voicebox Qwen3, then Ollama) | PASS (tests + live drafts) | 2026-10-18 |
| 10 (rehearsal) — "The Mathematics of Success" | PREVIEW 2 rendered; awaiting human claim and rights review | 2026-10-18 |

---

## Phase 0 — Discovery report (2026-10-17)

All findings below come from command output observed on 2026-10-17.

### Repository
- Working directory: `/Users/nikhiltalla/Desktop/Video`.
- The folder was **empty** (0 bytes) and was **not** a Git repository. No existing code to reuse or conflict with.
- `~/Desktop` is not synced to iCloud (no `CloudDocs/Desktop`), which matters because the Mac reports "iCloud Storage Full".

### Machine
| Item | Observed | Plan assumption |
|---|---|---|
| CPU | Intel Core i5-8257U @ 1.40 GHz (`x86_64`) | Apple Silicon M2 |
| Model | MacBook Pro 13-inch, 2019 | — |
| Memory | 8 GB | 8 GB |
| GPU | Intel Iris Plus 645 | Apple GPU / Metal |
| macOS | 15.8.1 (24H32) | — |
| Disk | 233 GiB volume, **158 GiB free** | 256 GB SSD |

### Toolchain
| Tool | Status |
|---|---|
| Python | 3.14.7 (python.org framework build, `/Library/Frameworks/Python.framework/Versions/3.14`) |
| pip | present (same framework) |
| git | 2.39.5 (Apple) |
| Xcode Command Line Tools | installed (`/Library/Developer/CommandLineTools`) |
| Homebrew | **not installed** |
| FFmpeg / ffprobe | **not installed** |
| Ollama | not installed (optional) |
| uv / pyenv / conda | not installed |

### Caches
- `~/.cache` 1.6 GB, `~/Library/Caches` 3.8 GB. No `~/.ollama`.
- Only internal disk mounted (`/Volumes`: `Macintosh HD`, `Claude`). No external media drive.

### Risks
1. **Intel, not Apple Silicon.** No Metal/MLX/Neural Engine acceleration. Local LLM, local TTS (e.g. Kokoro), and diffusion will run on CPU and be much slower than the plan assumes. Treat local generation as "evaluate carefully", not a default. FFmpeg rendering on a 4-core i5 is fine for preview and 1080p but slow; preview profiles matter.
2. **FFmpeg missing and no Homebrew.** Rendering (Phase 5+) is blocked until FFmpeg is installed. Installing Homebrew needs the user's admin password, so the user must run it.
3. **Python 3.14 is very new.** Core deps (Pydantic, Typer, pytest) support it, but some ML packages may not ship 3.14 wheels yet. Optional providers may need a separate 3.11/3.12 environment later.
4. **8 GB RAM.** Run heavy workloads one at a time (already in plan).

### Decisions
- Repo root: `/Users/nikhiltalla/Desktop/Video` (approved by user).
- Package: `src/reckoning_pipeline`, CLI command `pipeline`.
- Environment: stdlib `venv` at `.venv`, deps declared in `pyproject.toml`, exact versions locked in `requirements-lock.txt`.
- Base deps: `pydantic`, `typer`; dev deps: `pytest`. No ML packages.
- Large media stays outside Git; a configurable `PIPELINE_MEDIA_ROOT` is supported.
- FFmpeg: install via Homebrew, run by the user (needs password). The exact command is listed in `docs/INSTALL.md`.

---

## Phase 1 — Python foundation and CLI (2026-10-17)

### Implemented
- `git init` (branch `main`, nothing committed yet).
- Virtual environment at `.venv` (Python 3.14.7). Deps: pydantic 2.14.1, typer 0.27.3; dev: pytest 9.1.1. Exact versions are in `requirements-lock.txt`.
- CLI `pipeline` with these commands: `doctor`, `project init`, `project validate`, `render preview` (exits 3 "not implemented, Phase 7"), plus `--version`.
- Exit codes: 0 ok, 1 failure, 2 usage error, 3 not implemented, 4 config error.
- Config from `PIPELINE_*` env vars with safe defaults (network and paid providers off).
- Structured logs (text or JSON) to stderr with `ts`, `level`, `project_id`, `stage`, `scene_id`.
- `doctor` checks Python, architecture, ffmpeg, ffprobe, git, ollama (optional), disk, projects root, media root and the provider policy. Each check reports PASS, WARN or FAIL with a remedy.
- `project init` creates a slug-validated folder and a minimal `project.json` (schema 0.1), refuses to overwrite, and writes atomically. `project validate` checks the path, JSON, schema version, required fields and that `project_id` matches the folder name.
- `.gitignore`, `.env.example`, `README.md`, `docs/INSTALL.md`.

### Verification
- `pytest`: 51 passed (config, missing tools, disk thresholds, invalid paths, slugs, manifest errors, CLI exit codes, JSON log context).
- A fresh venv installed from `requirements-lock.txt` runs `pipeline doctor`, and the tests pass there too.
- `pipeline doctor` on this Mac: 5 pass, 3 warn (Python 3.14, Intel x86_64, Ollama absent), 2 fail (ffmpeg, ffprobe missing). Exits 1.
- No models downloaded. No external services called apart from PyPI for package installs.

### Known issues / limitations
- FFmpeg is not installed. The user needs to run the Homebrew commands in `docs/INSTALL.md` (they need the admin password). This blocks Phase 5+, not Phase 2.
- `project.json` is a stub. Phase 2 replaces it with the full manifest schema and adds migration from 0.1.
- `.env` is not auto-loaded. Variables must be exported.

### Next action
- Done. Phase 1 committed as `5e6d735`.

---

## Phase 2 — Data contracts (2026-10-17)

### Implemented
- `schemas/` package with Pydantic models for the project manifest, scenes, research ledger (sources and claims), asset registry and render report, all at `schema_version` "1.0". Unknown fields are rejected.
- Record-level rules:
  - Unsafe relative paths are rejected.
  - Planned, measured and final durations are kept separate, and a measured duration requires a narration asset.
  - Claim statuses other than `unverified` need a human reviewer and date.
  - Unknown rights can't be approved.
  - Generated assets must record their provenance.
- `project/validate.py` collects every issue in one pass: errors are duplicate IDs and orders, missing cross-references, unsafe paths and symlink escapes, missing files, sha256 mismatches and unsupported versions; warnings are asymmetric ledger links, unused assets and folder/ID mismatches. Errors name the record, e.g. `scenes[1](s02-claim-ledger).order`.
- `project/migrate.py` migrates 0.1 to 1.0 explicitly, keeps a backup, never overwrites, and refuses when data would be lost.
- CLI: `project validate` (`--strict`, `--skip-checksums`), `project migrate` (`--dry-run`), `schema export`. `project init` now creates a complete 1.0 project.
- Demo project `examples/demo-project/`: 4 scenes, 3 sources, 3 claims, 4 original SVG graphics made by `scripts/build_demo_assets.py`.
- Docs: `docs/SCHEMAS.md`, plus generated `docs/schemas/*.schema.json`.

### Decisions
- One ledger file holds both sources and claims. `scenes.json` holds the canonical narration; `script.md` is an editorial draft only.
- Added `claim_ids` to scenes, alongside `source_ids`, so each scene's claims are traceable directly.
- Demo folder is named `demo-project`, not the plan's `demo_project`, because project IDs are hyphenated slugs. A folder/ID mismatch is a warning, not an error.
- Demo claims cite files in this repo and are left **unverified**. No human has reviewed them, and the model must never mark claims verified.
- The demo assets stay `pending_review`. A human must approve them.
- The demo has narration text only. Narration audio arrives in Phase 5.

### Verification
- `pytest`: 124 passed.
- `pipeline project validate examples/demo-project`: OK with 0 errors and 0 warnings, including with `--strict`.
- Migrating a 0.1 project with `--dry-run` writes nothing. A real migration then validates OK.
- All four demo SVGs render in the browser, and their text fits inside the 1920 px frame (measured bounding boxes).
- No network or external services used.

### Known issues / limitations
- The research report (Phase 3) and rights report (Phase 4) aren't built yet. Phase 2 only validates structure and references.
- Checksums hash every asset on each validation. For large media, use `--skip-checksums` for quick checks; caching comes with Phase 7.
- Not pushed to GitHub yet, because the `gh auth login` step is still pending on the user's side.

### Next action
- Done. Phase 2 committed as `d060526`.

---

## Phase 3 — Research, claim ledger and script approval (2026-10-17)

### Implemented
- **Research report** (`research/report.py`): blockers, warnings and info for:
  - claims without sources
  - critical claims in narration that are unverified, partial or disputed
  - rejected claims still in use
  - retracted sources
  - "verified" claims with no checked supporting source
  - quotations without an excerpt and locator
  - causal claims resting only on correlational evidence
  - unused sources
  - scenes without claims
  - unreviewed AI suggestions

  Blockers only count claims the narration uses.
- **Ledger tooling:** `research import` (collision-safe, `--dry-run`, `--replace`) and `research review` (records reviewer, date and note; re-validated before an atomic write).
- **Approvals** (`approvals.py`, `schemas/approval.py`): an append-only `approvals.json`. A script approval is bound to a fingerprint of the narration and the claims it uses; editing either makes it stale. Claim exceptions need a 20+ character rationale and expire when the claim changes. Rejected-in-use, retracted-source and unknown-marker blockers can't be excepted.
- **Script gate** (`script/check.py`): `script validate` checks required sections, `[claim:id]` markers, empty narration, research blockers and approval state. `script approve` and `revoke` move status between `in_research` and `script_approved`.
- **Status gates in `project validate`:** `script_approved` and later statuses need a current approval; `publication_ready` also needs zero blockers.
- **Bibliography:** `research bibliography` lists sources in narration order, skipping retracted and internal sources unless `--include-internal`.
- **LLM adapter interface** (`providers/llm/base.py`), disabled. `research/assist.py` forces suggestions to unverified, unsourced and `origin: llm_suggestion`, and writes them to `research/notes/`, never the ledger. `research suggest` exits 3 until Phase 9.
- `PIPELINE_AUTHORIZED_REVIEWERS` optionally restricts who may approve or review.
- New projects get a `research/notes/` folder and a script template that explains claim markers.
- Docs: `docs/EDITORIAL_QA.md`; `docs/SCHEMAS.md` updated; JSON Schemas regenerated, including `approvals.schema.json`.

### Decisions
- New claim fields (`review_notes`, `evidence_basis`, `origin`) and `paths.approvals` are additive and optional, so `schema_version` stays 1.0 and Phase 2 files remain valid.
- Correlation-only detection uses an explicit `evidence_basis` recorded by the researcher. Inferring it from text would be unreliable.
- Quotations used in narration without an excerpt and locator are blockers, because misattributed quotes are high-risk.
- The demo is left honestly blocked: its critical claim is unverified because no human has reviewed it. Tests simulate a reviewer to exercise the approval flow. I did not record any real reviews or approvals.

### Verification
- `pytest`: 162 passed.
- `research report` on the demo: 1 blocker (`claim.critical_unreviewed`), 2 warnings, 1 info.
- `script validate` on the demo exits 1 because of that blocker. In tests, after simulated reviews, approval succeeds; editing narration or a claim then makes it stale, and `project validate` flags the status.
- `project validate examples/demo-project --strict`: OK.
- No network or external services used.

### Known issues / limitations
- No LLM provider yet (Phase 9).
- Automated checks can't verify that a reviewer actually read a source. The recorded name is the accountability.
- Not pushed to GitHub yet: `gh auth login` is still pending on the user's side.

### Next action
- Done. Phase 3 committed as `ea90b23`.

---

## Phase 4 — Asset sourcing, licensing and provenance (2026-10-17)

### Implemented
- **Rights checklist fields** on assets: `identifiable_people` and `people_clearance`, `trademarks_visible` and `trademark_notes`, `raw_redistribution_allowed`, `platform_cleared`. Approval also requires `license_url` for downloads and `generation.terms_url` for generated media.
- **Manual intake** (`assets add`):
  - copies the file into `assets/originals/<id>.<ext>` or the media root, verifies the SHA-256 against the source, and makes the copy read-only
  - never overwrites, checks disk space, and supports `--dry-run`
  - starts every asset as `pending_review`, or `blocked` if commercial use isn't allowed
  - takes extra fields from a `--metadata` JSON file
- **Derivatives** (`assets derive`): stored in `assets/derived/`, inherit the original's rights and point back to it. Refused when the original forbids derivatives.
- **Asset review** (`assets review --decision approve|block`): recorded in `approvals.json` with a fingerprint of the checksum and rights fields, so later edits make the approval stale. Blocking needs a reason. Approval is refused while any checklist item is missing.
- **Rights report** (`assets report`): groups assets as approved, pending_review or blocked, and lists what each pending asset still needs. Non-exceptable publication blockers: unapproved, blocked, stale or unrecorded assets used by scenes, and derivatives of no-derivatives originals.
- **Credits** (`assets credits`): exact attribution text (de-duplicated, in order of first use), licensed material and AI-generated material.
- **Publication gate:** `publication_ready` now also requires zero rights blockers. Validation also errors on no-derivatives violations and warns about derivatives stored under `originals/`.
- `.gitignore` now keeps `projects/*/assets/registry.json` tracked while still ignoring media.
- Docs: `docs/RIGHTS_AND_PROVENANCE.md`; `docs/SCHEMAS.md` updated; JSON Schemas regenerated.

### Decisions
- Intake is manual only. There are no stock or archive search adapters, downloads or scraping in the MVP; search adapters come later and only for sources whose terms allow API access.
- Asset approval reuses Phase 3's append-only approval log and fingerprinting, so there's one audit trail for every human decision.
- Rights blockers can never be excepted, unlike research blockers. Publishing with unknown rights isn't a judgment call.
- A derivative copies its parent's rights fields but gets its own review.
- The demo graphics stay `pending_review`. I didn't approve them, so `assets report` shows 4 publication blockers.

### Verification
- `pytest`: 191 passed. Tests cover the original staying unchanged (bytes and mtime), the copy being read-only, refusals, the media root, the disk margin, derivatives, the checklist, staleness, the gate and credits.
- `assets report` on the demo: 4 pending, 4 blockers ("rights recorded; ready for human review").
- `project validate examples/demo-project --strict`: OK.
- No network or external services used.

### Known issues / limitations
- No stock or archive search adapters (deliberately deferred).
- Read-only originals guard against accidental edits, not against someone deliberately changing permissions. Checksums catch either.
- Not pushed to GitHub yet: `gh auth login` is still pending on the user's side.

### Next action
- Done. Phase 4 committed as `98a99d6`.

---

## Phase 5 — Narration, timing and subtitles (2026-10-17)

### Environment
- The user installed MacPorts 2.12.7 (Apple-notarized installer) and FFmpeg 9.0.2 (`+gpl2+vmaf`) via MacPorts. Homebrew refuses Intel Macs.
- `pipeline doctor`: 7 pass, 3 warn (Python 3.14, Intel, no Ollama), 0 fail.
- Doctor and the pipeline now also look in `/opt/local/bin`, `/usr/local/bin` and `/opt/homebrew/bin` when a tool isn't on PATH.

### Implemented
- `media/audio.py`: ffprobe measurement; normalization to project-rate mono 16-bit WAV with 10 ms edge fades (bit-exact and deterministic); EBU R128 loudness and true peak; silence detection. All commands are argument arrays.
- **TTS interface** (`providers/tts/base.py`), declaring data egress and commercial clearance. **macOS `say` adapter**: offline and free, text passed via a file so it can't be read as options. It's marked not commercially cleared (Apple's licence), so its output is registered as `not_allowed` and `blocked`.
- **Imported human narration**, the first-class route: `narration import` with numbered takes; the highest take wins and earlier takes are kept.
- **Per-scene build** (`narration build`): imported take first, then TTS (only if a provider is chosen), otherwise reported missing. Output files are named by an input fingerprint, so unchanged scenes are reused and nothing is overwritten. The build measures duration, loudness and silence, updates scene durations, resets captions and timeline when the audio changes, registers `narr-<scene>` assets, and writes `reports/narration.json`.
- **Checks:** near-empty or silent audio, true peak above -1 dBTP, long leading/trailing silence, pauses over 2 s, implausible words/min, measured vs planned duration, and loudness spread across scenes.
- **Pronunciation overrides** (`narration/pronunciations.json`), applied to TTS input only and part of the cache key.
- **Captions** (`captions build` and `captions validate`): sentence, then clause, then word segmentation into at most 2×42-character cues; approximate timing within each scene's measured speech; strict SRT parse and validation; a `ForcedAligner` interface for later word-aligned timing.
- Docs: `docs/OPERATIONS.md` (new); `INSTALL.md` updated for MacPorts; `SCHEMAS.md`, README and JSON Schemas updated (`pronunciations`, `narration_report`).

### Decisions
- Kokoro-82M was not installed. It needs a model download (several hundred MB) plus an ML runtime. PyTorch no longer publishes Intel-Mac wheels, and this project runs Python 3.14, so whether Kokoro can run here at all needs checking first. That's a decision for the user (Phase 9 benchmark).
- `say` is preview-only and is enforced through the rights system, not just documented.
- Normalization changes format and sample rate, not loudness. Final levels are set in the Phase 7 mix.
- Captions follow the narration timeline (scenes back to back). Phase 7 re-times them against the final edit.
- The demo project stays without committed narration audio: `say` output can't be published, and audio is git-ignored. Tests build narration for it from synthetic tones and, on macOS, from `say`.

### Verification
- `pytest`: 217 passed. Tests cover normalization determinism, measurements against known synthetic silence, cache hits and invalidation (text, take, voice, pronunciation), no overwrites, warnings, the TTS route, `say` output being blocked, captions end to end, SRT round trip and validation, and the CLI.
- Manual run on a demo copy with `say` (voice Rishi): 4 chunks, 31.1 s, first build about 6 s and the cached rebuild 1.2 s. 9 caption cues, 0 errors, 0 warnings. Two chunks flagged at about -0.8 dBTP true peak.
- No network use apart from the user's MacPorts install.

### Known issues / limitations
- Captions are approximate (no forced aligner yet).
- Downmixing stereo takes to mono lowers their level by about 3 dB. It's measured and reported, and the mix handles it.
- Not pushed to GitHub yet, because the `gh auth login` step is still pending.

### Next action
- Done. Phase 5 committed as `a4b697e`.

---

## Phase 6 — Visual planning and provider adapters (2026-10-17)

### Implemented
- **Visual plan** (`schemas/visual.py`, `visuals.json`, optional `paths.visual_plan`): per-beat takeaway, visual question, type from the decision hierarchy, graphic kind, assets, sources and claims, requirements, on-screen text, purposeful motion, timing, reconstruction label, generation request, and review status. Schema rules: data graphics must cite sources, primary evidence must reference sources or claims, generated visuals and reconstructions must be labelled, motion needs a purpose, and unresolved beats must state requirements.
- Project validation cross-checks beat references (scene, asset, source, claim), duplicate beat IDs and duplicate per-scene order.
- **Visuals report** (`visuals report`): resolved or unresolved beats, rights and review state, gaps, generic visuals for precise or critical claims, type mismatches, unlabelled generated assets, text too long for a phone, and too many generated beats.
- **Deterministic graphics** (`graphics render`): title cards, zero-based bar charts (1–8 bars, data locator required) and timelines (2–6 events) as SVG. The ledger citation is printed in the frame, text is XML-escaped, and labels are clamped to safe edges. Outputs are registered as `original_graphic` assets pending review and are never overwritten.
- **Placeholders** (`visuals placeholders`): red "NOT FOR PUBLICATION" frames for unresolved beats, which are never registered as assets.
- **Contact sheet** (`visuals sheet`): self-contained HTML (inline CSS, light and dark, phone-width friendly, all text escaped) with narration, beats, thumbnails, badges and gaps.
- **Image provider interface** (`providers/image/base.py`), with none enabled. `visuals generate` exits 3 and points to placeholders or manual assets.
- Demo project: `visuals.json` with one original-graphic beat per scene, linked to its claims and sources. It reports 0 gaps and 0 warnings.
- Docs: Phase 6 section in `OPERATIONS.md`, visuals checklist in `EDITORIAL_QA.md`, `SCHEMAS.md` and README updated, JSON Schemas regenerated (`visuals`, `graphic_spec`). `.gitignore` covers placeholder frames.

### Decisions
- No image or video generation provider. Local diffusion isn't viable on an 8 GB Intel Mac; hosted options cost money and send prompts externally (Phase 9, with approval).
- Beat `review_status` is a field in `visuals.json` rather than an approval-log event. Visual review is editorial and iterative, and the rights gate for the underlying assets is already fingerprinted in the log.
- Charts are SVG only for now. Phase 7 rasterizes them with FFmpeg's librsvg (confirmed available).

### Verification
- `pytest`: 248 passed.
- Rendered sample bar chart, timeline and title SVGs to PNG and inspected them. Fixed timeline edge labels that overflowed the safe area.
- Rendered the contact sheet with headless Chrome and inspected it: gaps and warnings at the top, scene cards, thumbnails, the placeholder frame and badges.
- `visuals report examples/demo-project`: 0 gaps, 0 warnings.
- No network or external services used.

### Known issues / limitations
- No map renderer yet; `graphic_kind: map` beats need a manual asset.
- Motion is planned but not rendered until Phase 7.
- Not pushed to GitHub yet: `gh auth login` is still pending.

### Next action
- Done. Phase 6 committed as `bac1068`.

---

## Phase 7 — Timeline compiler and FFmpeg rendering (2026-10-18)

### Implemented
- **Profiles:** `preview` (960×540, veryfast, CRF 28, placeholders allowed, silent scenes allowed) and `master_16x9` (project resolution, medium, CRF 18, needs narration, no placeholders). `vertical_9x16` exits with a Phase 11 message.
- **Timeline compiler** (`timeline/compiler.py`, pure):
  - Narrated scene = 0.25 s lead-in + measured narration + 0.5 s tail; silent scene = planned estimate.
  - Fades sit inside each scene (no overlaps), with dissolves rendered as a dip through black.
  - Beats split evenly or follow explicit offsets.
  - Placeholders fill unresolved or unplanned scenes.
  - Generated and reconstruction labels are carried through.
  - Captions are retimed per scene.
  - Per-scene fingerprints cover all inputs, the profile, the FFmpeg version and a hash of the command builder.
- **Command builder** (`render/commands.py`, pure): argument arrays only. Helper files are referenced by relative names, so no text is interpolated into filtergraphs. It explicitly normalizes size, fps, yuv420p and 48 kHz stereo AAC, and supports slow-push and pan via zoompan, labels via drawtext, and captions via libass with a backing box.
- **Runner** (`render/runner.py`):
  - Re-validates the project including checksums and checks disk space.
  - Pre-decodes every picture input, and gives each FFmpeg call a timeout.
  - Renders each scene to `.partial`, verifies it with ffprobe and promotes it atomically; reuses a scene only on an exact fingerprint match that still probes.
  - Concat-copies the scenes and validates the final file's duration, size, fps, codecs and audio rate.
  - Writes fingerprint-named outputs (never overwritten), sidecar SRT, and `final_duration_seconds` back to scenes.
  - Writes a render report for both success and failure. Logs and intermediates are kept on failure, and a re-run resumes.
- CLI: `timeline build`, `render preview`, `render master` (`--burn-captions`, `--dry-run`), `render vertical` (exits 3).
- Docs: `docs/ARCHITECTURE.md` (new: modules, data flow, provider boundaries, cache and timing model), the Phase 7 section in `OPERATIONS.md`, and updates to `SCHEMAS.md` and the README. JSON Schemas regenerated.

### Issues found and fixed during verification
- **Stale cache after a renderer change:** changing caption styling reused old scene renders. Fixed by hashing `render/commands.py` into every scene fingerprint.
- **Hang on an undecodable image:** FFmpeg's looped-image input spun at 170% CPU for over 9 minutes. Fixed by pre-decoding every input and adding per-call timeouts scaled to scene length. pytest now dumps stacks after 240 s.
- **Frame-rate check:** after concat, the average frame rate (29.992) only just passed; the check now uses the nominal rate.
- **Caption legibility:** burned captions collided with text in a graphic; they now sit on a semi-opaque backing box.
- **Missing source files in git (affects commit `a4b697e`):** the `.gitignore` rule `media/` also matched the source package `src/reckoning_pipeline/media/`, so `media/tools.py` and `media/audio.py` were never committed in Phase 5. A clean checkout of `a4b697e` or `bac1068` won't import. Fixed by anchoring the rule to `/media/` and adding the package in this commit. Verified by exporting the staged tree on its own and running the full suite against it (271 passed).

### Verification
- `pytest`: 271 passed in about 60 s. Tests cover pure compiler and command tests, integration renders at 320×180, caching (one changed scene re-renders only that scene), narrated renders with sidecar and burned captions, master refusals, placeholders, failure logs and resume, and the CLI.
- Demo preview with macOS `say` narration in `tmp/demo-preview/` (git-ignored): 4 scenes, about 36 s, 960×540 H.264/AAC at 30 fps. The first render took about 12 s; the cached re-render took 0.5 s. I inspected frames: slow push on the title, crisp diagrams, readable captions. Audio measures -18 LUFS integrated.
- No network or external services used.

### Known issues / limitations
- No music mix or loudness normalization of the final mix yet.
- `reveal`, `highlight` and `build` motion are shown static.
- AAC padding can add up to about 50 ms per scene join (validated within tolerance).
- The demo preview uses `say`, which isn't publishable. A publishable master needs your recorded narration and approved assets.
- Not pushed to GitHub yet: `gh auth login` is still pending.

### Next action
- User reviews the demo preview and Phase 7. Then Phase 8: automated QA and the human-review report.

---

## Phase 9 (early) — Voicebox TTS adapter (2026-10-18)

The user picked [jamiepine/voicebox](https://github.com/jamiepine/voicebox) from five suggested repos; it's the only voice tool among them. The user installs the app. Phase 8 hasn't started yet.

### Research (from the repo's source, not guessed)
- Licence MIT, actively maintained, ships an Intel Mac build, and runs on CPU when there's no Apple Silicon or CUDA.
- Local REST API at `127.0.0.1:17493`. An OpenAI-compatible `POST /v1/audio/speech` (`model`, `input`, `voice`, `response_format`, `speed`) returns audio directly. `GET /profiles`, `GET /profiles/presets/kokoro`, `POST /profiles` and `GET /` (version) are also available.
- Kokoro-82M model licence: **Apache-2.0**, confirmed on the Hugging Face model card (`hexgrad/Kokoro-82M`) and in voicebox's `kokoro_backend.py`. It has English and Hindi preset voices.
- Voicebox Cloud routes return 404 unless `VOICEBOX_CLOUD_ENABLED` is set, so generation stays local.

### Implemented
- `providers/tts/voicebox.py`:
  - Uses only the standard library's HTTP client (no new dependencies), with clear errors when the app isn't running or a model isn't downloaded.
  - Refuses non-loopback URLs unless network use is approved.
  - `kokoro:<voice_id>` creates or reuses a Voicebox preset profile.
  - Clearance is per voice: Kokoro presets are cleared (Apache-2.0); cloned voices are blocked until consent is recorded; designed voices and unreviewed engines are blocked.
  - The provider version (`voicebox <ver> / <engine>`) is part of the narration cache key.
- Narration build now asks the provider for per-voice clearance (`voice_clearance`). macOS `say` keeps its static, preview-only rule.
- Config: `PIPELINE_VOICEBOX_URL`, `PIPELINE_VOICEBOX_ENGINE`. `narration voices` and `narration build` accept `--provider voicebox`.
- Docs: Voicebox setup in `INSTALL.md`, rules in `OPERATIONS.md`, and the provider table in `ARCHITECTURE.md`.

### Verification
- `pytest`: 282 passed. 11 new tests run against a fake local server that mirrors Voicebox's routes. They cover remote-URL refusal, unreachable-app errors, listing, preset auto-creation (no duplicates), clearance, the request shape, error surfacing, the 10,000-character limit, and full narration builds (Kokoro preset → allowed and pending review; cloned voice → blocked).
- **Not yet verified against the real app.** Voicebox isn't installed on this Mac yet, so the live Kokoro test is pending.

### Live check (2026-10-18)
- Voicebox wasn't on this Mac at first, despite earlier reports. I downloaded the official `Voicebox_0.5.0_x64.dmg` (587 MB, GitHub release v0.5.0) with the user's permission. The image is intact, signed "Developer ID Application: James Pine (YB4V2VA9YY)", and Apple-notarized. At the user's request I copied it into /Applications and launched it.
- The API answered within seconds: `{"version":"0.5.0"}`, health shows `backend_type: pytorch`, `backend_variant: cpu`. `pipeline narration voices --provider voicebox` lists 28 English Kokoro presets from the real app.
- The Kokoro model isn't downloaded yet: `/models/status` still showed `downloaded: false` after 20 minutes of polling. So the live narration build and preview are pending.

### Next action
- User downloads Kokoro 82M in Voicebox → Models. Then build demo narration with `kokoro:af_heart` in `tmp/demo-preview` and render a preview.

---

## Phase 9 (early) — Pexels stock adapter (2026-10-18)

### Implemented
- `providers/stock/` (provider-neutral interface) and `pexels.py`, the official API: video and photo search, fetch by id.
  - The key comes only from `PIPELINE_PEXELS_API_KEY` and goes only in the `Authorization` header. It's never logged, stored or put in errors.
  - Errors are clear for 401, 404 and 429.
- `assets/stock.py`: picks the largest file within the project width; downloads only from Pexels/Vimeo media hosts over HTTPS with a 1.5 GB cap; refuses clips the project already has (the used-footage ledger); registers via normal intake with the Pexels License fields filled in. People and trademarks are left unknown for human review.
- `assets/checklist.py` and `pipeline assets checklist`: record the human rights answers (people, clearance, trademarks, derivatives, platform clearance). Changing them later makes an earlier approval stale.
- `utils/http.py`: verified TLS with the `certifi` CA bundle (new dependency, pinned in `requirements-lock.txt`). The python.org build of Python on this Mac had no root certificates, and verification is never disabled.
- CLI: `stock search`, `stock add`, `assets checklist`. Docs: `RIGHTS_AND_PROVENANCE.md`, `INSTALL.md`, `ARCHITECTURE.md`, README. `.env.example` has a placeholder only.

### Security note
- The user pasted their Pexels key into chat. I didn't use or store it from there, and advised regenerating it. The user then set the key in `~/.zprofile` themselves (length check: 56). The pipeline reads it only from the environment.

### Verification
- `pytest`: 292 passed. 10 new tests run against a fake Pexels API (no network). They cover the key being required and never appearing in errors or URLs, parsing, file choice, refusing other hosts and plain http, the size cap, end-to-end add (pending review), approval blocked until the checklist is done and then allowed, duplicate refusal, dry run downloading nothing, and the CLI.
- **Live:** `stock search "empty office at night"` returned 5 real clips. `stock add … pexels:video:35867210 --dry-run` chose the 1920×1080 MP4 and validated the record. No real download yet; that needs the user's go-ahead.

---

## Phase 9 (early) — AI script drafting with Voicebox's Qwen3 (2026-10-18)

The user chose Voicebox's built-in Qwen3 (local, already installed) over installing Ollama.

### Research (from Voicebox source and the live app)
- `POST /llm/generate` takes `prompt` (≤50k), `system` (≤4k), `model_size` (0.6B/1.7B/4B), `max_tokens` (≤4096) and `temperature`, and returns `{text, model_size}`. If the model isn't cached, it **starts a download** and returns 202.
- Voicebox can forward LLM calls to a custom OpenAI-compatible endpoint (`custom_llm_endpoint` in `GET /settings/captures`). On this Mac it is unset (live check).
- Live `/models/status`: Qwen3 0.6B, 1.7B and 4B are all **not downloaded** yet, and neither is Kokoro.

### Implemented
- `providers/llm/voicebox_llm.py`: a local LLM adapter.
  - Before each call it refuses a remote custom endpoint, and refuses rather than starting a download when the model is missing.
  - It verifies the reply came from a local Qwen3 size and strips `<think>` blocks.
  - It enforces Voicebox's size limits. `get_llm_provider` now supports `voicebox`, and config adds `PIPELINE_LLM_PROVIDER` and `PIPELINE_LLM_MODEL_SIZE`.
- `script/draft.py` and `pipeline script draft`:
  - Drafts section by section (template headings) with an editorial system prompt, from the brief and non-rejected claims only.
  - Deterministic post-checks flag unknown or rejected markers, unverified claims, sentences with numbers or quotes but no marker, `[NEEDS SOURCE]` gaps, and untagged sections. It also writes source and visual notes.
  - Output goes to `script/drafts/` with a provenance header and never overwrites `script.md` or `scenes.json`.
- `pipeline research suggest` now works with `--provider voicebox`, writing unverified suggestions to `research/notes/`.
- Docs: AI section in `EDITORIAL_QA.md`, `ARCHITECTURE.md`, README and `.env.example`.

### Issues found during testing
- Thinking blocks were stripped only in the Voicebox adapter, so another provider's reasoning could have leaked into drafts. The draft builder now strips them itself.

### Verification
- `pytest`: 306 passed. 14 new tests cover the claims block, cleaning, `<think>` stripping, a full draft with a scripted model (file location, header, flags, `script.md` and `scenes.json` untouched, prompt contents), refusals (empty brief, empty reply), and the adapter: happy path, custom-endpoint refusal before any text is sent, undownloaded model, non-local reply, 202, 500, URL and size checks.
- Live: `pipeline script draft examples/demo-project --provider voicebox` reached Voicebox and stopped with "Qwen3 1.7B isn't downloaded", as designed.

### Next action
- User downloads Qwen3 1.7B (and Kokoro 82M) in Voicebox → Models. Then run a live draft on `tmp/demo-preview` and review its quality and flags.

### Live results (2026-10-18)
- Voicebox's own model downloads stalled with 0 bytes, twice. Models were fetched directly into its Hugging Face cache with `huggingface_hub` (in a scratch venv, not a project dependency) with the user's approval: Qwen3 0.6B (1.52 GB), Kokoro-82M (0.36 GB) and Qwen3 1.7B (4.08 GB). A leftover 0-byte `.incomplete` file from Voicebox's stalled attempt hid the finished 1.7B download; I moved it to scratch rather than deleting it.
- **Qwen3 0.6B (Voicebox):** a 2.5 min draft. The checks caught an invented marker (copied from the prompt's example). The text was repetitive and one section was cut off, so I added `repeated` and `cut_off` checks and removed the copyable example marker from the prompt.
- **Qwen3 1.7B (Voicebox):** fails with "LLM generation failed" even with other models unloaded. The checksums are fine, so it's most likely the unquantized CPU load on 8 GB.
- **Voicebox 0.5.0 compatibility:** the installed release lacks `/v1/audio/speech`, which exists in the repo HEAD I first read. The TTS adapter now checks `/openapi.json` and falls back to `POST /generate/stream` (seed 0, nothing saved to Voicebox history).

---

## Phase 9 (early) — Ollama LLM provider (2026-10-18)

- With the user's approval: downloaded `Ollama.dmg` v0.40.6 (214 MB, official GitHub release). It's intact, signed "Developer ID Application: Infra Technologies, Inc (3MU9H2V9Y9)" and notarized. Copied it to /Applications and launched it. The API (0.40.6) listens on 127.0.0.1:11434 only.
- Pulled `qwen3:4b-instruct-2507-q4_K_M` (2.5 GB, Q4_K_M) at about 3.3 MB/s.
- `providers/llm/ollama.py`: `POST /api/chat` (`think: false`, `num_ctx` 8192), loopback-only unless approved, never pulls models (it names the `ollama pull` command instead), strips `<think>`. Config adds `PIPELINE_OLLAMA_URL` and `PIPELINE_OLLAMA_MODEL`.
- Tests: 3 new tests against a fake Ollama (request shape, missing model, load failure, remote refusal, config).
- **Live comparison** (demo, `--minutes 1`): Ollama Qwen3 4B took 1:40, 153 words, 0 repeats, 0 invented markers, and correctly used the ledger's caveats; 3 flags, all "unverified claim". Voicebox 0.6B took 2:31, with 4 repeats, 1 invented marker and 1 cut-off section. Ollama is now the recommended drafting provider.

---

## Phase 10 (rehearsal) — "The Mathematics of Success" (2026-10-18)

The user supplied the topic and a five-principle summary. Project: `projects/mathematics-of-success/` (manifests tracked; media git-ignored).

- **Research:** 6 sources, each confirmed bibliographically (PubMed/Crossref/RePEc/DOI/arXiv) but not yet checked against full text:
  - Salganik, Dodds & Watts 2006, *Science*
  - Merton 1968, *Science*
  - Rosen 1981, *AER*
  - O'Boyle & Aguinis 2012, *Personnel Psychology*
  - Pluchino, Biondo & Rapisarda 2018, *ACS*
  - a computed arithmetic source for the 1%-a-day illustration (1.01^365 ≈ 37.78; 0.99^365 ≈ 0.026)

  8 claims, all `unverified` pending the user's review; 4 are critical.
- **Script:** 7 scenes, 327 words, written by Claude from the summary and ledger. Every fact is tagged. The narration says when something is a model (Rosen) or a simulation (Pluchino), and labels interpretation and speculation.
- **Visuals:** 6 deterministic graphics (title, three cards that cite their source, a zero-based compounding chart labelled as an illustration, closing card) and 5 Pexels clips (with the user's approval). The visual plan has 0 gaps.
- **Preview 1:** macOS voice, 5 placeholders, 2:14. **Preview 2:** Kokoro `af_heart` via Voicebox (7 scenes in 83 s, all at about -19.7 LUFS), stock linked, 2:09, rendered in 36 s, 37 caption cues.
- **Open before a master:**
  - User verifies the 8 claims against their sources.
  - Checklist and review the 5 clips. The train clip shows an "AT" transit logo; the crowd clip shows identifiable people.
  - Review the 6 graphics and 7 narration assets, and approve the script.
  - Two clips are 720p, which a 1080p master would upscale.
- **Cosmetic issues:** burned captions cover the chart's source line; two title cards break lines unevenly; the chart footer shows doubled brackets.

---

## Voice styles and the `annt` preset (2026-10-18)

- The user supplied a reference narration (The Corporate Autopsy, "The Smartphone Autopsy") and asked to fine-tune a model to reproduce that voice. **Declined:** cloning or fine-tuning on a real narrator's voice without consent is impersonation. Offered and built style-matching instead.
- Kept the reference as **ANNT** at `references/ANNT/ANNT.mp3` (read-only, git-ignored, sha256 af01abc3…). It's documented in `references/ANNT/README.md`, together with its measured style: male, about 133 Hz, about 165 wpm, -20.5 LUFS, continuous music bed.
- `narration/styles.py`: a `documentary` voice-processing chain and the `annt` preset (Kokoro am_liam, speed 0.87, documentary). New `--style` and `--preset` options for `narration build`. `normalize_audio` takes `extra_filters`.
- **Issues fixed during tuning:**
  - `aecho` output gain 0.5 made the voice 6 dB quieter, so it's now 0.9.
  - `alimiter`'s default auto-level pushed peaks back to -0.2 dBTP, so it's now `level=disabled` at limit 0.84.
  - Final narration: -20.6 LUFS (ANNT is -20.5), all true peaks at -1.7 dBTP or lower.
- **Option 4** (license the same library voice): a web search found no public information on the channel's voice or service. Next step is to check the channel's About page and video descriptions for credits.
- Episode preview 4 rendered with the `annt` preset (2:07). An A/B file is at `references/ANNT/ANNT-vs-annt-preset.mp3` (git-ignored).

---

## Tone match, music bed and pacing (2026-10-19)

The user asked to reproduce the ANNT voice exactly, first claiming it was their own voice and then that it was AI-generated. **Declined:** ownership couldn't be verified, and cloning from audio with a music bed underneath would be poor quality anyway. Pointed to recovering the voice from the generating service's account, or re-recording if it's their own voice. Built the three legitimate style steps instead:

1. **Tone match:** `annt` style = documentary chain + match EQ derived from long-term spectra (60% applied). Mean band gap went from 5.4 dB to 2.5 dB. A/B: `references/ANNT/ANNT-vs-annt-v2.mp3`.
2. **Music bed:**
   - `media/music.py` synthesizes an original pad (deterministic, no samples). `pipeline music pad|set|clear`.
   - `MusicSettings` on the project manifest (additive); validation checks the music asset type.
   - The music asset counts in the rights report and publication gate.
   - The renderer has a final audio-only pass: loop, fades, sidechain ducking, mix, limiter. Video is copied. The plan fingerprint includes the music, so scene renders are reused.
3. **Pacing:** scene fields `narration_speed` (0.7–1.3, multiplies TTS speed, part of the cache key) and `hold_after_seconds` (0–5, replaces the 0.5 s tail).

**Episode tuning:**
- Pacing: s01 at 0.95 with a 1.0 s hold; s04 at 1.03; s05 at 0.97 with a 1.0 s hold; s07 at 0.93 with a 2.0 s hold; the rest hold 0.8 s.
- Voice rebuilt with the tone-matched `annt` preset.
- Original pad (138 s, key A) at -6 dB, ducked. The bed started at -14 dB, but that put the music about 18 dB under the voice, which was barely audible, so it was raised.
- **Preview 5:** 2:12, -20.5 LUFS integrated, 3.4 LU range (ANNT: -20.5 / 3.7).

Tests: 6 new tests for the music pad (deterministic, registered, loudness), settings validation, rights inclusion, plan fingerprint and scene reuse, a real ducked mix render, mix command shape, and per-scene speed and hold.

## 2026-10-20: "Reckoner" house narrator

- The narration voice is now named **Reckoner**: `--preset reckoner`, which is Kokoro `am_liam` at speed 0.87 with the tone-matched `annt` style.
- `--preset annt` stays as an alias. It gives identical settings, so existing narration caches stay valid.
- The "brain-defends-you" preview used this voice. It is 28 Pexels clips over 14 scenes with no text cards: 3:47 long, -20.6 LUFS.

---

## Phase 8 — Automated QA and human review (2026-10-20)

### Implemented
- **`pipeline qa report`** (`qa/checks.py`): checks the latest successful render of a profile (master by default) and every publication gate. It writes `reports/qa-<profile>.json` (new **QAReport** schema) and `reports/qa-<profile>.md`, the human report with the review checklist. It exits 1 while blockers remain.
  - **Render:** the output exists, isn't empty, still matches its render report checksum, and lives under `renders/<profile>/`. Codec, size, frame rate and duration match the profile. The render isn't stale: the timeline is recompiled and its fingerprint compared, so a project or renderer change is caught. Scene renders exist, and there are no placeholders.
  - **Audio and picture** (`qa/media.py`): one FFmpeg pass (scaled to 320 px for speed) measures integrated loudness, true peak, silences, and black and frozen picture. Clipping and silence are blockers. Loudness, peaks, mid-video silence, black and frozen picture are warnings; the last two are acknowledged heuristics.
  - **Narration:** missing, silent or clipped files are blockers. High peaks, long pauses and an out-of-date report are warnings.
  - **Captions:** parse, order and overlap errors, and cues running past the end, are blockers. Readability notes are a single warning.
  - **Gates:** validation errors, script approval, research blockers, rights blockers, and missing attribution text are blockers. Repeated visuals and low disk space are warnings.
- **Waivers:** `pipeline qa waive` accepts one warning, never a blocker. It records the name and a rationale of 20+ characters as a `qa_warning_waived` event, bound to that check on that rendered file.
- **Sign-off:** `pipeline qa signoff --checklist-done` works only on a clean, fully analysed master report whose project and video are unchanged. It records `qa_signoff` and sets `publication_ready`. `pipeline qa revoke` withdraws it.
  - `project validate` now requires a current sign-off for `publication_ready`, and flags the project invalid as soon as anything changes after QA.
  - Sign-off, revoke and QA still run while those gate errors are present (`STATUS_GATE_CODES`), so the status can always be repaired.
- **Publication stays manual.** Nothing uploads.

### Issues found and fixed
- **Rights gap (affects the publication gate since Phase 4):** assets referenced only by the visual plan were treated as unused, so they never blocked `publication_ready` or appeared in credits. Every Pexels clip in "brain-defends-you" was affected. `extra_used_ids` now adds each beat's rendered asset and the music bed to the rights report, the credits and the gate.
- **The music bed was flagged as unused** by `project validate`; it now counts as used.

### Verification
- `pytest`: **333 passed**, 10 of them new in `tests/test_qa.py`:
  - analysis parsing and thresholds
  - an unprepared project
  - visual-plan rights
  - a full narrated master through waiver, sign-off, stale detection and revoke
  - re-render invalidating waivers
  - tampered or missing output and skipped media
  - real FFmpeg analysis, event rules and the CLI
- Run on both episodes (preview profile):
  - **brain-defends-you:** 44 blockers (43 assets awaiting your rights review, script not approved) and 1 caption readability warning. -20.6 LUFS, true peak -4.6 dBTP, no black, frozen or silent stretches. Analysis took 4 s.
  - **mathematics-of-success:** 25 blockers. Besides rights and research, its preview is now stale because the renderer code changed since 18 Oct. There are also 3 frozen-picture warnings on its still graphic cards (expected) and 1 caption note.

### Next action
- Approve the clips' rights and the script, render the master, then `qa report`, `qa waive` as needed, and `qa signoff`.

---

## 2026-10-20: "sage" voice: Qwen3 Ryan, humanized

The user supplied a second style reference (a calm philosophy-documentary narrator) and asked for that kind of voice, without cloning. See `references/sage/README.md`. The audio was analysed in place and not copied.

- **Measured:** male, about 118 Hz; wide intonation (11.5 semitones); about 14 short pauses per minute; a strong low end; -14 LUFS.
- **Kokoro comparison:** all 13 Kokoro male voices were compared. am_echo matched the pitch but was flat (6 semitones).
- **Humanize pass** (`narration/humanize.py`, `--humanize`): TTS sentence by sentence, deterministic pauses from the measured pattern, a slight tempo drift, and room tone. It's part of the fingerprint only when on, so existing caches stay valid. On am_echo it widened intonation from 6.0 to 10.3 semitones.
- **Qwen3-TTS CustomVoice 0.6B** (Apache-2.0, 2.5 GB) downloaded with approval. The Voicebox adapter now takes the engine from the voice name (`qwen_custom_voice:Ryan`) and sends `model_size` and an `instruct` delivery instruction through `/generate/stream`, with a 1-hour request timeout. The engine licence was added to `REVIEWED_ENGINES`. The voice list includes Qwen voices and skips engines an older Voicebox lacks.
- **`sage` style and preset:** a tone-match EQ fitted to Ryan's raw output (60% of the difference), plus the documentary dynamics, the Ryan voice, humanizing and a calm-narrator instruction. Ryan was chosen by the user from an A/B against am_echo, am_puck and Aiden.
- **Voicebox issue found:** an orphaned `voicebox-server` from 18 Oct still held port 17493 after the app was reopened, so Qwen requests failed with 500 / "Broken pipe". It was stopped, Voicebox was reopened, and the fix is documented in `OPERATIONS.md`.
- **Verification:** a real `--preset sage` build of a demo scene. Intonation 11.7 st vs 11.5, pitch movement 24.7 vs 24.9 st/s, tone gap 2.3 dB, about 12x real time. 7 new tests in `tests/test_humanize.py`.

---

## 2026-10-21: Archival style, steps 1 and 2 (`docs/PILOT_ARCHIVAL_PLAN.md`)

Pilot topic chosen by the user: "Every Philosopher's Answer to Happiness".

### Step 1: public-domain museum images
- `providers/stock/museums.py`: **The Met** and the **Art Institute of Chicago** open-access APIs. Both are free with no key, and both release public-domain works as CC0. Only items flagged public domain *with* an image are ever returned.
  - Requests are paced (about 4 per second) and retried with back-off; the Met dropped connections during rapid lookups.
  - Search index entries that 404 are skipped.
- **Met API change found:** `/public/collection/v1/search` returns `410 Gone` (retired on 2026-10-01). The pipeline uses `/v1.1/search`, which takes `isPublicDomain`, `hasImages`, `limit` and `offset`. Object lookups are unchanged.
- **AIC:** its search endpoint answered `503` throughout testing, though the listing endpoint worked. The adapter is tested against a fake API; live use is still to confirm.
- Stock intake now takes each provider's own `media_hosts`, so museum images download only from `images.metmuseum.org` and `www.artic.edu`. Museum assets are registered as CC0 with museum, object ID, credit line, and title/artist/date (for labels), and stay `pending_review`.
- CLI: `pipeline archive search` and `pipeline archive add`. `stock` also accepts `--provider met|aic`.

### Step 2: compositions on a dark canvas
- `VisualBeat.layers` (new optional **Layer** model): image or text layers with position, size, timing, fades, drift, zoom, edge (`feather`, `oval`, `circle`), feather width and crop. Text styles are `quote` (italic, red highlight), `label` (spaced capitals) and `caption` (dim). A composition's `asset_ids` must match its image layers.
- `render/compose.py`: each layer is prepared once as a transparent PNG (fit, crop, geq alpha mask, or SVG text via librsvg with system Georgia), then one FFmpeg overlay pass animates them on a near-black canvas with alpha fades, drift and frame-evaluated zoom. The runner renders the clip (named by a layer digest) and hands it to the normal scene renderer as a video segment.
- `compose.py` is part of the renderer digest, so scene fingerprints change when it does. Layer images are recorded as `visual:layer` inputs in render reports. `extra_used_ids` counts every layer image for rights, credits and the publication gate.

### Test scene (tmp/archival-test, git-ignored)
Two CC0 Met images (met:248475 "Marble head of Epikouros", met:437394 Rembrandt "Aristotle with a Bust of Homer"), one 24 s scene in two beats: a feathered bust with label, date and a highlighted quote, then a fade through black to a feathered Rembrandt with a caption. Music pad underneath. Rendered at 960×540 in 8 s. Known flaw: the Met's navy studio backdrop shows faintly around the bust (step 3 background removal fixes this). The test quote (Principal Doctrines V, tr. Hicks) is used for layout only and must be verified against the source in step 4 before any real use.

### Verification
`pytest`: **357 passed** (17 new: `test_archive.py`, `test_compose.py`). JSON Schemas regenerated.


---

## 2026-10-22: Archival style, step 4: kinetic quotes (`docs/PILOT_ARCHIVAL_PLAN.md`)

### Word-by-word reveal
- Text layers take `"reveal": "words"`. The quote then appears **phrase by phrase as the narrator reads it**: at most 4 words per phrase, breaking at punctuation, each phrase fading in over 0.45 s.
- **Timing** (`timeline/quotes.py`): the quote is found inside the scene's narration, ignoring case and punctuation. The timeline compiler stores a start time for each word on the layer (`word_times`), relative to the beat.
  - **Humanized narration:** `humanized_tts` now returns where each sentence's speech starts and ends. The build writes this to `narration/<scene>/<id>.timing.json` and to the narration report (`ChunkReport.sentences`). The reveal is accurate to the sentence, with words spread by character count inside it.
  - **Other narration:** words are spread across the measured speech span.
  - **Quote not read in the scene:** words are paced evenly (2.6 per second) and the timeline warns.
  - Timings are used only if the report entry matches the audio the timeline actually uses.
- **Rendering** (`render/compose.py`): `expand_reveals` turns a reveal layer into one layer per phrase. Each phrase layer renders the *whole* quote with the other words transparent (`visible_words`) and shares the parent layer's drift and zoom clock (`motion_start`/`motion_end`). This way nothing shifts as words appear, even while the quote moves.

### Font
- **Cormorant Garamond** (SIL OFL 1.1, roman and italic variable fonts) is bundled in `render/fonts/` and listed as package data in `pyproject.toml`.
- It reaches librsvg through a private fontconfig file per render (`font_env`) that includes the system configuration. Nothing is installed system-wide. Georgia is the fallback.
- Glyph widths and text sizes were retuned for Cormorant.

### Honesty rule for quotes
- A `quote` layer must name a `claim_id`: a ledger **quotation** claim with its source and translation.
- `project validate`:
  - a missing `claim_id` is a warning;
  - a claim that doesn't exist is an error;
  - a claim that isn't a quotation is a warning.
- **QA** blocks publication when a quote has no claim (`visual.quote_unsourced`) or when its claim isn't verified or knowingly excepted (`visual.quote_unverified`).

### Verification
- `pytest`: all tests pass, including 10 new ones in `tests/test_quotes.py`. They cover quote matching, sentence-timed versus evenly paced reveals, phrase expansion, stable layout, font configuration, the validation and QA rules, sentence timings from a humanized build, and an end-to-end render with phrase layers.
- JSON Schemas regenerated.
- In the test scene (`tmp/archival-test`), the humanized sage narration was rebuilt and recorded 4 sentence timings. The quote's sentence runs from 5.54 s to 18.60 s. **The preview still predates the reveal**, so re-render it to review the effect on screen.

### Next action
- Re-render the test scene and review the reveal.
- Then **step 3**: medallions, cut-outs and background removal. This needs a decision on the rembg model download (about 170 MB).

---

## 2026-10-23: Archival style, step 3: cut-outs and medallions; narrator switched to Reckoner

### Narrator
- At the user's request, the pilot now uses **`--preset reckoner --humanize`** instead of `sage`. `--humanize` keeps the per-sentence timings that sync the quote reveal. The plan was updated.
- The test scene was re-narrated (20.6 s) and re-rendered. This was the first real render of the word reveal: the quote's words land between 5.5 s and 14.7 s, in step with the voice.

### Background removal (`assets/cutout.py`, `pipeline archive cutout`)
- **Model:** U²-Net, `u2net.onnx` (Apache-2.0, 176 MB), downloaded with the user's approval to `models/u2net/` (git-ignored, new `PIPELINE_MODELS_DIR`). Its MD5 matches the one rembg publishes, and its SHA-256 is pinned and checked before every use.
- **Why not rembg:** `pip install rembg` failed on this Intel Mac with Python 3.14. llvmlite (pulled in through pymatting and numba) has no wheel, and onnxruntime has no Intel-Mac builds at all. The same model runs through **OpenCV's DNN module** instead, with only NumPy and OpenCV-headless (about 40 MB) as the optional `cutout` extra. One pass takes about 0.8 s.
- **Output:** a transparent PNG trimmed to the object (2% margin), registered as a **derivative** through the existing `plan_derivative`. It inherits the parent's rights, stays `pending_review`, and its notes ask the reviewer to check the edges.
- **Test scene:** `met-epicurus-cut`. The navy backdrop and pedestal are gone. A sliver of the dark mounting post remains, hidden with `crop` plus a small `feather`.

### Medallions and alpha-preserving masks (`render/compose.py`)
- The feather, oval and circle masks now **multiply the image's own alpha**, so a cut-out keeps its shape inside them. Previously a mask replaced the alpha, which would have brought back a cut-out's rectangle.
- **New `ring` on oval and circle image layers:** the portrait fades out at 92.5% of the radius, and a thin, anti-aliased brass ring (`#a8946a`) sits at 96.5%. It's one `geq` pass at prepare time and cached like every layer.
- **Test scene:** the cut-out bust "becomes" an oval ringed medallion at about 13 s, with a 0.2 s overlap, while the name and date labels stay. A longer cross-fade looked like a ghosted double image, so it was shortened.
- **Also fixed in the test layout:** the citation line overlapped the last line of the quote, which is taller since the Cormorant retune. It moved from y 0.66 to 0.73.

### Verification
- `pytest`: **374 passed**, including 7 new tests in `tests/test_cutout.py`. They cover cut-out and trim with a stand-in predictor, the empty-mask refusal, the model checksum, CLI derivative registration, the real model on a test image, the ring rules, and pixel checks of a rendered ring, gap and masked cut-out.
- JSON Schemas regenerated.
- Visual check of the re-rendered test scene: the cut-out bust, the medallion change and the quote reveal.

### Not done in step 3
- The bust-to-medallion change is a quick cross-fade between two layers, not a morph.
- The paper-cutout walking figure is out of scope, as the plan says.

### Next action
- **Step 5:** the chapter map. This needs the decision on the chapter device: iceberg-style levels, stone steps or rock strata.

---

## 2026-10-23: Archival style, step 5: the chapter map (stone steps)

The user chose **stone steps** as the chapter device.

### The graphic (`graphics/chapter_map.py`, `GraphicSpec.kind = "chapter_map"`)
- **Shape:** a tall, transparent SVG, 1920 wide and 1080 + 540 × (levels − 1) tall, with 2-8 levels. It's drawn like the stepped base of a Greek temple seen from the front: each level is a stone course with a lit, chipped tread, and a face with masonry joints, a hairline crack and feTurbulence grain.
- **Inscription:** the level number (spaced capitals with a short red rule), the title in Cormorant italic, and an optional subtitle.
- **Depth:** each lower step is wider and sinks further toward the canvas colour (up to 60%). A faint warm glow sits at the top, with the episode title above level I.
- **Layout rules:** joints and cracks are kept clear of the inscription, and there's room on the right for three medallions.
- **Fixed geometry:** `view_y`, `slab_x`, `marker_anchor` and `map_height` depend only on the level count, which the SVG records as `data-chapter-levels`.
- **Determinism:** the texture is seeded from the spec, so the same spec gives a byte-identical file.
- **First draft rejected:** it looked like stacked drawers, with blotchy grain, so it was redrawn as widening temple steps with finer grain.

### Showing it (`VisualBeat.chapter_map`)
- **ChapterMapView:** `asset_id`, `level`, `from_level` (default: the level above), `pan_start`, `pan_seconds` and `markers` (level, asset, slot, name, crop). There are at most 3 markers per level, and slots are unique.
- **New `graphic_kind: chapter_map`:** structure, not data, unlike `map`, so no sources are required.
- **Compiler output:** the timeline compiler turns the beat into layers that share one camera move:
  - the map, positioned so `from_level` is centred, with a drift to `level`;
  - ringed oval medallions on their steps, with small-capital name labels.

  Earlier levels' medallions show from the start, and the new level's fade in as the camera arrives. Extra beat `layers` go on top.
- **Renderer:** compiled layers may now sit and travel off-frame (`TimelineLayer` widens `y`, `max_height` and `drift_y`; authored layers keep the strict limits). The new `motion_ease` uses smoothstep within the `motion_start`/`motion_end` window, so the camera holds, eases down and settles.
- **Rights:** the map and the medallion images are in the beat's `asset_ids`, so they count for rights, credits and the publication gate.

### Fixed along the way
- `project validate` flagged an asset as "unused" when only a visual beat used it, such as a museum image without `intended_scene_ids`. Beat assets now count as used, and `test_unused_asset_warning` covers both cases.

### Verification
- `pytest`: all tests pass, including 7 new ones in `tests/test_chapter_map.py`. They cover the spec rules, determinism and geometry, view and beat rules, the compiled camera move and medallion timing, the placeholder fallback, the eased-motion expression, and a real render.
- JSON Schemas regenerated.
- **Test scene** (`tmp/archival-test`, new silent scene `s02-map`): a 5-level map. The camera holds on level I with the Epicurus medallion, eases down to level II over 3.6 s, and the Aristotle medallion (cropped from the Rembrandt) fades in. Frames were checked.

### Next action
- **Step 6:** the 3-minute pilot "Every Philosopher's Answer to Happiness". It needs research (sources and verified quotations with public-domain translations), the script, `--preset reckoner --humanize` narration, 6-8 scenes, the preview render and QA.

---

## 2026-10-23: Archival style, step 6: pilot "Every Philosopher's Answer to Happiness" (preview)

Project: `projects/every-philosophers-answer-to-happiness`.

### Research: every quotation checked against a public-domain text
- **Method:** the source texts were downloaded (Project Gutenberg and Wikisource) and each quotation was matched **word for word**. The matched passages and locators are stored as source `excerpts` in the ledger. The ledger has 5 sources and 13 claims: 5 quotations, 4 historical, 4 interpretive.

| Thinker | Quotation (locator) | Translation |
|---|---|---|
| Epicurus | Principal Doctrines V (D.L. X.140) | R. D. Hicks, 1925 |
| Aristotle | "not one swallow or one fine day…" (NE I, 1098a18) | D. P. Chase, 1847 (Everyman 1911) |
| Epictetus | Enchiridion 5 | T. W. Higginson, 1865 |
| Schopenhauer | the pendulum, WWI § 57 | Haldane and Kemp, 1883 |
| Mill | "Ask yourself whether you are happy…" (Autobiography, ch. V) | Mill's own English, 1873 |

- **Rights check:** W. D. Ross's Aristotle (1908) was rejected because Ross died in 1971, so it is not public domain in the UK or EU. Chase died in 1902.
- **Still to confirm:**
  - The Gutenberg edition doesn't name its translator on the title page (attributed to Chase via its bibliography).
  - J. Kemp's death date, for non-US public-domain status of the Schopenhauer translation.
- Claims stay `unverified` for human review. The Epictetus "born a slave" fact comes from the 1948 editor's introduction (secondary).

### Script and narration
- **Scenes:** 7 scenes, 394 words, interpretations phrased as interpretations. Each thinker gets one level of the map.
- **Narration:** `--preset reckoner --humanize`, 134.4 s at about −20 LUFS, with sentence timings recorded for the quote reveals. Total running time **2:24**.

### Visuals
- **Images:** five Met CC0 images: Epicurus head, Rembrandt's *Aristotle with a Bust of Homer*, a Roman head of **Chrysippus** (for the Stoics, labelled as Chrysippus, not Epictetus), Delaunoy's *pendulum clock* (c. 1815–30) for Schopenhauer, and Constable's *Salisbury Cathedral* (c. 1825) for Mill.
- **Cut-outs:** three, of the busts and the clock.
- **Map and music:** a 5-level stone-steps map and a synthesized music bed at −10 dB.
- **Gap:** neither museum has public-domain portraits of **Schopenhauer** or **Mill**, so their levels have no medallion and their scenes use period objects, honestly captioned.
- **Structure:** each thinker scene opens with the map easing down one level (the new medallion arrives with the camera), then a composition with the kinetic quote and its citation. The close climbs back up all five levels.

### Fixes found by watching the preview
- Climbing back up the map (the closing recap) re-faded the top medallion as if it were new. Medallions now fade in only when the camera arrives *downward*; a climb is a recap (new test).
- Two-line image captions overlapped the name labels; captions were widened to one line. The Rembrandt crop was refocused on the face.
- The JSON Schemas were regenerated after a docstring change.

### QA (`qa report --profile preview`): NOT READY, as expected before human review
- **27 blockers, all human gates:** the 5 quotations to verify (`research review`), the script approval, and rights reviews for the 8 images, the map, the music and the 7 narration files.
- **8 warnings:**
  - 6 frozen-picture notes (slow still shots; expected for this style). The cold open holds a static map for 15 s; a slow drift would fix it.
  - the map reused across 6 beats (by design);
  - 2 caption cues with 3 lines.

### Verification
- `pytest`: all tests pass.
- Preview rendered in 92 s. A contact sheet is in `reports/preview-frames.png`.

### Next action
- **The user:** review and verify the 5 quotations, approve the script, and review the asset rights.
- **Decide:** whether to add public-domain portraits of Schopenhauer and Mill from Wikimedia Commons (a new source type for the pipeline).
- **Then:** render the master, run `qa report`, waive the expected warnings, and sign off.

---

## 2026-10-23: Fix: AIC search returned unrelated works when nothing matched

- **Problem:** `AICProvider.search` sent `q=<query>` with a public-domain term filter. When nothing matched (e.g. "schopenhauer"), the API fell back to its default listing (ids 11, 111, 27, 4…, `_score` ~5), so `pipeline archive search "<x>" --source aic` showed unrelated artworks as results.
- **Fix:** search now sends an Elasticsearch bool query: a `cross_fields` `multi_match` with `operator: and` over `title^4`, `artist_title^3`, `subject_titles^2` and `term_titles`, plus a `filter` on `is_public_domain`. The bracket parameters use explicit indices, because a bare `[]` makes each parameter a separate clause (and the API answers 400). Pacing, retries, headers and host limits are unchanged.
- **Checked live:** "philosopher" gives 28 hits (Heraclitus, Democritus, Head of a Philosopher…); "marble head" gives 30 busts and portrait heads; "schopenhauer" and "zzqxv" give 0.
- **Tests:** the fake AIC API in `tests/test_archive.py` now only answers matching words. The search test checks the request shape (no bare `q`, the filter, `operator=and`, the boosted fields), and a new test checks that a miss returns `[]`.
