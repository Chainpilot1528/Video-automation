# Rights and provenance

**Unknown rights never default to approved.** Every media file has one record in `assets/registry.json` with its source, licence, checksum and a human rights decision. Any asset a scene uses must be approved before the project can reach `publication_ready`.

## Intake (manual only)

The pipeline doesn't download, scrape or search for assets. You obtain the file yourself from a source whose terms allow it, then register it:

```bash
.venv/bin/pipeline assets add projects/my-film ~/Downloads/harbour.jpg --id s03-harbour --type image --method downloaded --source-url "https://example.org/item/123" --creator "Jane Doe" --license "CC BY 4.0" --license-url "https://creativecommons.org/licenses/by/4.0/" --commercial-use allowed --attribution "Photo: Jane Doe, CC BY 4.0" --evidence "Licence stated on item page, checked 2026-10-17" --scene s03-harbour --dry-run
```

Drop `--dry-run` to ingest it. Checklist fields that don't have their own flag (such as `derivatives_allowed`, `identifiable_people` and `trademarks_visible`) go in a JSON file passed with `--metadata`.

What intake guarantees:
- **The original is preserved.** The source file is only read. The stored copy goes to `assets/originals/<id>.<ext>` (or under `PIPELINE_MEDIA_ROOT` with `--media`), is checked against the source's SHA-256, and is made read-only. Existing files are never overwritten.
- **There's a checksum.** The SHA-256 is recorded, and `pipeline project validate` re-checks it, so any later change to the file is caught.
- **Nothing is approved at intake.** Assets start as `pending_review`. If `--commercial-use not_allowed` is given, they start as `blocked`.
- **Disk space is checked first.** Intake refuses if it would leave less than `PIPELINE_MIN_FREE_DISK_GB` free.

## Derivatives

Crops, conversions and edits are separate assets that point back to the original:

```bash
.venv/bin/pipeline assets derive projects/my-film s03-harbour ~/edits/harbour-16x9.jpg --id s03-harbour-crop --notes "16:9 crop"
```

A derivative is stored in `assets/derived/` and inherits the original's rights fields. It still needs its own review. It's refused if the original has `derivatives_allowed: false`. Validation flags derivatives stored under `originals/` and rights fields that differ from the parent.

## Rights checklist

These must be answered before approval. `null` means "not yet checked".

| Question | Field(s) | Applies to |
|---|---|---|
| Commercial use allowed? | `commercial_use` | all |
| Attribution required, and its exact text? | `attribution_required`, `attribution_text` | all |
| Exact licence for this specific asset | `license_name`, `license_url` | downloaded (name also for user-supplied) |
| Editing/derivatives permitted? | `derivatives_allowed` | downloaded, user-supplied, generated |
| Identifiable people, and clearance (release, or why none is needed) | `identifiable_people`, `people_clearance` | images and video, except original graphics |
| Trademarks or logos, and how endorsement is avoided | `trademarks_visible`, `trademark_notes` | external images and video |
| Music/SFX cleared for YouTube/Instagram (Content ID) | `platform_cleared` | external music and SFX |
| May the raw file be redistributed in a public archive? | `raw_redistribution_allowed` | recorded for Phase 11 archives |
| Evidence for the decision | `rights_evidence`, plus `rights_holder` or `creator` | all |
| Generated media: service terms | `generation.terms_url` (plus provider, model, version, prompt, settings) | generated |

Generated output isn't assumed to be copyright-safe. Record the service, model, version, date, prompt and settings, and the terms you relied on.

## Review

```bash
.venv/bin/pipeline assets review projects/my-film s03-harbour --decision approve --by "Your Name" --note "Checked licence page and photo contents"
```

```bash
.venv/bin/pipeline assets review projects/my-film s05-clip --decision block --by "Your Name" --note "Licence is non-commercial"
```

- Approval is refused while any checklist item above is missing, and the error lists exactly what's missing.
- Each decision is appended to `approvals.json` with your name and a fingerprint of the asset's checksum and rights fields. Editing the file or any rights field afterwards makes the approval **stale**, and the asset must be reviewed again.
- An asset set to `approved` by hand-editing the registry, with no recorded review, is flagged as `asset.approval_unrecorded`.
- `PIPELINE_AUTHORIZED_REVIEWERS` optionally limits who may decide.

## Reports

```bash
.venv/bin/pipeline assets report projects/my-film
```

```bash
.venv/bin/pipeline assets credits projects/my-film --write
```

`assets report` groups assets into `approved`, `pending_review` and `blocked`, and lists what each pending asset still needs. These **publication blockers** can't be excepted:

| Code | Meaning |
|---|---|
| `asset.unapproved_in_use` | a scene uses an asset that isn't approved |
| `asset.blocked_in_use` | a scene uses a blocked asset |
| `asset.approval_unrecorded` / `asset.approval_stale` | approval is missing from the log, or out of date |
| `asset.derivative_not_allowed` | derivative of an asset that forbids derivatives |

`assets credits` lists the exact attribution text (once each, in order of first use), licensed material and AI-generated material for assets used in scenes, ready for the video description.

## Stock search (Pexels)

Manual intake proved reliable, so the first stock adapter now uses Pexels' **official API**:

```bash
.venv/bin/pipeline stock search "empty office at night" --type video --project projects/my-film
```

```bash
.venv/bin/pipeline stock add projects/my-film pexels:video:35867210 --id s02-night-city --scene s02-evidence
```

```bash
.venv/bin/pipeline assets checklist projects/my-film s02-night-city --people no --trademarks no
```

```bash
.venv/bin/pipeline assets review projects/my-film s02-night-city --decision approve --by "Your Name"
```

- **`stock search`** sends only your query (plus the API key, in a header) and downloads nothing. With `--project`, it marks clips that project already uses.
- **`stock add`** fetches the item through the API, picks the largest file no wider than the project resolution, downloads it only from Pexels' media hosts over HTTPS (size-capped), and registers it through normal intake: checksum, read-only original. It fills in source URL, creator, Pexels License name and URL, commercial use allowed, attribution not required (a courtesy credit is stored), derivatives allowed, and raw redistribution not allowed. It refuses a clip the project already has (the "used footage" ledger). `--dry-run` downloads nothing.
- **People and trademarks stay unknown** until you've watched the clip and recorded your answers with `assets checklist`. Approval is impossible before that. Changing checklist answers later makes an earlier approval stale.
- The key is read only from `PIPELINE_PEXELS_API_KEY` in your shell profile. It's never written to manifests, logs, reports or error messages.
- HTTPS certificates are verified using the bundled `certifi` CA store.

## Not in the MVP

- Further stock adapters (Pixabay, Wikimedia Commons) come next, each after a licence review. Wikimedia licences vary per file and often require attribution.
- Any scraping, or bypassing of access controls. Never.
