# Reckoning Self — Documentary Pipeline

A modular, rights-aware pipeline for evidence-led YouTube documentaries. It tracks claims and sources, records asset provenance and licences, builds narration-timed timelines, and renders with FFmpeg. Humans approve scripts, visuals and exports. Nothing is published automatically.

Status: **Phase 3 (research, claim ledger, script approval)** complete. See `docs/BUILD_LOG.md`, `docs/SCHEMAS.md` and `docs/EDITORIAL_QA.md`.

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
| `pipeline render preview <path>` | not implemented, exits 3 (Phase 7) |

Exit codes: `0` ok, `1` check/validation failure, `2` usage error, `3` not implemented, `4` configuration error.

## Limitations

- Nothing renders yet, and FFmpeg is required from Phase 5.
- No AI providers are wired in. The core route is designed to work free, local and manual.
