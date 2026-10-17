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
| 7 — Timeline compiler and FFmpeg rendering | PASS (awaiting user review) | 2026-10-18 |

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
