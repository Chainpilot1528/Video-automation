# Reckoning Self — Documentary Pipeline

A modular, rights-aware pipeline for evidence-led YouTube documentaries. It tracks claims and sources, records asset provenance and licences, builds narration-timed timelines, and renders with FFmpeg. Humans approve scripts, visuals and exports. Nothing is published automatically.

Status: **Phase 7 (timeline compiler, FFmpeg rendering)** complete. See `docs/BUILD_LOG.md`, `docs/OPERATIONS.md`, `docs/SCHEMAS.md`, `docs/EDITORIAL_QA.md` and `docs/RIGHTS_AND_PROVENANCE.md`.

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

Render it (preview voice from macOS `say`, which isn't publishable):

```bash
.venv/bin/pipeline narration build examples/demo-project --provider macos-say --voice Rishi
```

```bash
.venv/bin/pipeline render preview examples/demo-project --burn-captions
```

Full setup, including FFmpeg, is in `docs/INSTALL.md`. The architecture is in `docs/ARCHITECTURE.md`. The manifest formats are in `docs/SCHEMAS.md`.

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
| `pipeline visuals report <path> [--json] [--strict]` | working |
| `pipeline visuals sheet <path>` | working (reports/visuals.html) |
| `pipeline visuals placeholders <path>` | working (preview-only frames) |
| `pipeline visuals generate <path>` | exits 3: no image provider until Phase 9 |
| `pipeline graphics render <path> <spec.json> [--dry-run]` | working (title, bar chart, timeline) |
| `pipeline timeline build <path> [--profile]` | working |
| `pipeline render preview <path> [--burn-captions] [--dry-run]` | working (960×540) |
| `pipeline render master <path> [--burn-captions] [--dry-run]` | working (project resolution; needs narration, no placeholders) |
| `pipeline render vertical <path>` | exits 3 (Phase 11) |

Exit codes: `0` ok, `1` check/validation failure, `2` usage error, `3` not implemented, `4` configuration error.

## Limitations

- FFmpeg is required from Phase 5. On Intel Macs, install it with MacPorts (`docs/INSTALL.md`).
- No music mix yet. `reveal`/`highlight`/`build` motion is shown static.
- Captions are approximately timed until a forced aligner is added.
- No AI providers are wired in. The core route is designed to work free, local and manual.
