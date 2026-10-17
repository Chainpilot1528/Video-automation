# Data contracts (schema 1.0)

Every production is described by versioned JSON files. **They are the source of truth.** Other files, such as `script.md` and render reports, are either drafts or derived from them.

Machine-readable JSON Schemas live in [`docs/schemas/`](schemas/). Regenerate them after changing a model:

```bash
.venv/bin/pipeline schema export docs/schemas
```

A test fails if the committed schemas are out of date.

## Project layout

```text
<project>/
├── project.json            ProjectManifest: settings and paths to everything below
├── brief.md                central question, audience, risks
├── script/script.md        editorial draft (not canonical narration)
├── research/ledger.json    ResearchLedger: sources and claims
├── scenes.json             SceneManifest: ordered scenes, canonical narration text
├── assets/registry.json    AssetRegistry: one record per media file
├── assets/…                project-local asset files
├── narration/  renders/  reports/
```

All paths in `project.json` are relative to the project folder. Absolute paths, `..` and symlinks that escape the folder are rejected. Asset files can instead live under `PIPELINE_MEDIA_ROOT` by setting `"root": "media"`.

## Rules common to all files

- `schema_version` is required and must be `"1.0"`. Older versions fail validation and point you to `pipeline project migrate`.
- **Unknown fields are errors.** A typo such as `"narraton_text"` is never silently ignored.
- IDs are lowercase letters, digits, `-` and `_`, up to 64 characters. Project IDs are stricter slugs (`why-boredom-disappeared`).
- Timestamps must include a timezone. Dates use `YYYY-MM-DD`.

## `project.json` — ProjectManifest

| Field | Notes |
|---|---|
| `project_id`, `title`, `working_title`, `language` | `language` is BCP-47-like: `en`, `en-IN`, `hi` |
| `target_platforms` | `youtube`, `youtube_shorts`, `instagram_reels`, `instagram`, `substack` |
| `output_profiles` | `preview`, `master_16x9`, `vertical_9x16` |
| `frame_rate` | 23.976, 24, 25, 29.97, 30, 50, 59.94 or 60 |
| `resolution` | `{width, height}`, both even |
| `audio_sample_rate` | 44100 or 48000 |
| `paths` | `brief`, `research_ledger`, `script`, `scenes`, `asset_registry` |
| `project_status` | `draft` → `in_research` → `script_approved` → `in_production` → `in_review` → `publication_ready`, or `archived` |
| `created_at`, `updated_at`, `tool_versions` | `updated_at` ≥ `created_at` |

## `scenes.json` — Scene

| Field | Notes |
|---|---|
| `scene_id`, `order` | both unique; `order` ≥ 1 |
| `purpose`, `narration_text`, `visual_strategy`, `on_screen_text`, `notes` | `narration_text` is the canonical narration |
| `asset_ids`, `source_ids`, `claim_ids` | must exist in the registry or ledger |
| `planned_duration_seconds` | **estimate only**, never used for timing |
| `actual_narration_duration_seconds` | **measured from audio**; only allowed when `narration_asset_id` is set |
| `final_duration_seconds` | timeline length after holds and transitions; needs the measured duration first if the scene is narrated |
| `narration_asset_id` | must be an asset of type `narration` or `audio` |
| `caption_status` | `none`, `approximate`, `word_aligned`, `reviewed`; anything but `none` needs narration |
| `approval_status` | `pending`, `approved`, `changes_requested`, `rejected` |
| `transition_in`, `transition_out` | `{type, duration_seconds}`; `cut` must be 0 s, other types > 0 s |
| `music_cue`, `render_status`, `input_fingerprint` | the fingerprint is a sha256, used by the Phase 7 cache |

## `research/ledger.json` — Source and Claim

A source existing does not prove it supports a claim, so **verification lives on the claim**.

**Source:** `source_id`, `title`, `authors`, `publisher`, at least one of `url`, `archive_id` or `identifier` (DOI, ISBN or repo path), `published_date`, `accessed_date`, `source_type`, `classification` (`primary`, `secondary` or `tertiary`), `supported_claim_ids`, `excerpts` (`{claim_id, text, locator}`), `reliability_notes`, `verification_status` (`unchecked`, `checked`, `inaccessible`, `retracted`), `citation_text`, `usage_notes`.

**Claim:** `claim_id`, `text`, `claim_type` (`factual`, `statistical`, `causal`, `quotation`, `historical`, `interpretive`, `speculative`), `importance` (`critical`, `supporting`, `contextual`), `source_ids`, `verification_status`, `caveats`, `counter_evidence`, `reviewer`, `review_date`.

| Status | Requirements |
|---|---|
| `unverified` | none (default) |
| `partially_verified`, `verified` | reviewer, review_date, and at least one source |
| `disputed` | reviewer, review_date, and `counter_evidence` |
| `rejected` | reviewer and review_date |

The validator warns if a claim cites a source that doesn't list it, or the other way round.

## `assets/registry.json` — Asset

`asset_id`, `path`, `root` (`project` or `media`), `type`, `creation_method` (`downloaded`, `user_supplied`, `generated`, `original_graphic`, `recorded`), `provider`, `source_url`, `creator`, `rights_holder`, `license_name`, `license_url`, `commercial_use` (`allowed`, `not_allowed`, `unknown`), `attribution_required` (`true`, `false`, or `null` for unknown), `attribution_text`, `derivatives_allowed`, `rights_evidence`, `generation` (provider, model, version, date, prompt, settings, terms), `acquired_date`, `sha256`, `derived_from`, `intended_scene_ids`, `review_status`, `publication_status` (`approved`, `pending_review`, `blocked`), `notes`.

**Unknown rights never default to approved.** `publication_status: "approved"` is rejected unless all of these are true:

- `review_status` is `approved`
- `commercial_use` is `allowed`
- `attribution_required` is known, and `attribution_text` is filled in if it's `true`
- `rights_evidence` and `rights_holder` or `creator` are filled in
- downloaded and user-supplied assets also have a `license_name`

Generated assets must record `generation`. Downloaded assets must record `source_url`. Each file has exactly one record, and the validator compares its sha256 against the file on disk.

## Render report

Written to `reports/` from Phase 7 onward. It records the profile, status, timestamps, pipeline and FFmpeg versions, exact commands, settings, input checksums, output metadata and checksum, warnings and errors.

## Validation

```bash
.venv/bin/pipeline project validate examples/demo-project
```

- **Errors** (exit 1): invalid JSON, unsupported schema, schema violations, duplicate IDs or scene orders, missing references, unsafe paths, missing files, checksum mismatches, a `media` root with no `PIPELINE_MEDIA_ROOT`.
- **Warnings** (exit 0, or 1 with `--strict`): folder name differs from `project_id`, asymmetric ledger links, unused assets.
- `--skip-checksums` skips hashing for a quick check.

## Migration

Schema changes ship with an explicit migration. Fields are never silently reinterpreted.

```bash
.venv/bin/pipeline project migrate projects/my-film --dry-run
```

```bash
.venv/bin/pipeline project migrate projects/my-film
```

The migration keeps `project.json.v<old>.bak` and creates missing files without overwriting existing ones. It refuses if any field would be lost or an old value has no clear mapping.
