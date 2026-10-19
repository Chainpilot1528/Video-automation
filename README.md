# Reckoning Self — Documentary Pipeline

A modular, rights-aware pipeline for evidence-led YouTube documentaries. It tracks claims and sources, records asset provenance and licences, builds narration-timed timelines, and renders with FFmpeg. Humans approve scripts, visuals and exports. Nothing is published automatically.

Status: **Phase 8 (automated QA and human sign-off)** complete, with early Phase 9 providers (local TTS, local LLM, Pexels). See `docs/BUILD_LOG.md`, `docs/OPERATIONS.md`, `docs/SCHEMAS.md`, `docs/EDITORIAL_QA.md` and `docs/RIGHTS_AND_PROVENANCE.md`.

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
| `pipeline research suggest <path> --provider voicebox` | working (local Qwen3; suggestions only) |
| `pipeline script draft <path> --provider ollama|voicebox [--minutes]` | working (local AI draft to script/drafts/) |
| `pipeline script validate <path>` | working |
| `pipeline script approve / revoke <path> --by NAME` | working (human decision) |
| `pipeline assets report <path> [--json] [--strict]` | working |
| `pipeline assets add <path> <file> --id --type --method ... [--dry-run]` | working (manual intake) |
| `pipeline assets derive <path> <parent> <file> --id` | working |
| `pipeline assets review <path> <asset> --decision approve/block --by NAME` | working (human decision) |
| `pipeline assets credits <path> [--write]` | working |
| `pipeline assets checklist <path> <asset> --people yes/no --trademarks yes/no ...` | working (human answers) |
| `pipeline stock search "<query>" [--type video/photo] [--project]` | working (Pexels API) |
| `pipeline stock add <path> pexels:video:<id> --id --scene [--dry-run]` | working |
| `pipeline narration import <path> <scene> <file> --creator NAME [--take N]` | working |
| `pipeline narration voices [--provider macos-say/voicebox] [--locale]` | working |
| `pipeline narration build <path> [--preset reckoner] [--provider --voice --speed --style] [--dry-run]` | working (per-scene, cached) |
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
| `pipeline music pad <path> [--duration --key]` / `music set <path> <asset>` / `music clear` | working (original bed, ducked) |
| `pipeline qa report <path> [--profile master/preview] [--skip-media]` | working (JSON + Markdown report) |
| `pipeline qa waive <path> "<code>@<subject>" --by NAME --rationale TEXT` | working (human decision) |
| `pipeline qa signoff <path> --by NAME --checklist-done` / `qa revoke` | working (human decision; publishing stays manual) |

Exit codes: `0` ok, `1` check/validation failure, `2` usage error, `3` not implemented, `4` configuration error.

## Limitations

- FFmpeg is required from Phase 5. On Intel Macs, install it with MacPorts (`docs/INSTALL.md`).
- `reveal`/`highlight`/`build` motion is shown static.
- Captions are approximately timed until a forced aligner is added.
- AI providers (Voicebox TTS, Ollama/Voicebox LLM) are optional and local. The core route works free, local and manual.
- Black and frozen picture detection in QA are heuristics and only ever warn.
