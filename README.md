# Reckoning Self — Documentary Pipeline

A modular, rights-aware pipeline for evidence-led YouTube documentaries. It tracks claims and sources, records asset provenance and licences, builds narration-timed timelines, and renders with FFmpeg. Humans approve scripts, visuals and exports. Nothing is published automatically.

Status: **Phase 5 (narration, timing, captions)** complete. See `docs/BUILD_LOG.md`, `docs/OPERATIONS.md`, `docs/SCHEMAS.md`, `docs/EDITORIAL_QA.md` and `docs/RIGHTS_AND_PROVENANCE.md`.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/pipeline doctor
```

```bash
.venv/bin/pipeline project init why-boredom-disappeared
```

```bash
.venv/bin/pipeline project validate projects/why-boredom-disappeared
```

Try the self-contained demo, which has 4 scenes, original graphics and example data:

```bash
.venv/bin/pipeline project validate examples/demo-project
```

Full setup, including FFmpeg, is in `docs/INSTALL.md`. The manifest formats are in `docs/SCHEMAS.md`.

## Commands

| Command | Status |
|---|---|
| `pipeline doctor` | working |
| `pipeline project init <slug>` | working |
| `pipeline project validate <path> [--strict] [--skip-checksums]` | working |
| `pipeline project migrate <path> [--dry-run]` | working (0.1 → 1.0) |
| `pipeline schema export [dir]` | working |
| `pipeline research report <path> [--json] [--strict]` | working |
| `pipeline research import <path> <file> [--replace] [--dry-run]` | working |
| `pipeline research review <path> <claim> --status S --by NAME` | working (human decision) |
| `pipeline research exception <path> <claim> --by NAME --rationale TEXT [--revoke]` | working |
| `pipeline research bibliography <path> [--write]` | working |
| `pipeline research suggest <path>` | exits 3: no LLM provider until Phase 9 |
| `pipeline script validate <path>` | working |
| `pipeline script approve / revoke <path> --by NAME` | working (human decision) |
| `pipeline assets report <path> [--json] [--strict]` | working |
| `pipeline assets add <path> <file> --id --type --method ... [--dry-run]` | working (manual intake) |
| `pipeline assets derive <path> <parent> <file> --id` | working |
| `pipeline assets review <path> <asset> --decision approve/block --by NAME` | working (human decision) |
| `pipeline assets credits <path> [--write]` | working |
| `pipeline narration import <path> <scene> <file> --creator NAME [--take N]` | working |
| `pipeline narration voices [--provider] [--locale]` | working |
| `pipeline narration build <path> [--provider --voice] [--dry-run]` | working (per-scene, cached) |
| `pipeline captions build <path>` | working (approximate timing) |
| `pipeline captions validate <file.srt>` | working |
| `pipeline render preview <path>` | not implemented, exits 3 (Phase 7) |

Exit codes: `0` ok, `1` check/validation failure, `2` usage error, `3` not implemented, `4` configuration error.

## Limitations

- No video rendering yet (Phase 7). FFmpeg is required from Phase 5. On Intel Macs, install it with MacPorts (`docs/INSTALL.md`).
- Captions are approximately timed until a forced aligner is added.
- No AI providers are wired in. The core route is designed to work free, local and manual.
