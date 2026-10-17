# Build Log

Phase status, decisions, tests, known issues, and next action. Newest entries at the bottom of each section.

## Phase status

| Phase | Status | Date |
|---|---|---|
| 0 — Discovery | PASS (approved by user) | 2026-10-17 |
| 1 — Python foundation and CLI | PASS (committed 5e6d735) | 2026-10-17 |
| 2 — Data contracts | PASS (committed d060526) | 2026-10-17 |
| 3 — Research, claim ledger, script approval | PASS (awaiting user review) | 2026-10-17 |

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
- User reviews Phase 3. Optionally, they can try reviewing and approving the demo claims themselves. Then Phase 4: asset sourcing, licensing and provenance.
