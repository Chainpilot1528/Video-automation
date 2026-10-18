# Editorial QA

Automated checks raise warnings and blockers. They **don't** promise complete fact-checking. Editorial judgment stays with a person.

## Research workflow (Phase 3)

1. **Collect sources and claims.** Write them in `research/ledger.json`, or prepare a JSON file and import it:
   ```bash
   .venv/bin/pipeline research import projects/my-film new-research.json --dry-run
   ```
2. **Check what needs attention:**
   ```bash
   .venv/bin/pipeline research report projects/my-film
   ```
3. **Review each claim yourself and record the decision:**
   ```bash
   .venv/bin/pipeline research review projects/my-film claim-id --status verified --by "Your Name" --note "Read p. 4 of the 2019 report"
   ```
4. **Tag the script.** Mark factual statements in `script/script.md` with `[claim:<claim-id>]`, and put the canonical narration in `scenes.json` with each scene's `claim_ids`.
5. **Check readiness, then approve:**
   ```bash
   .venv/bin/pipeline script validate projects/my-film
   ```
   ```bash
   .venv/bin/pipeline script approve projects/my-film --by "Your Name"
   ```
6. **Export the source list** for the video description:
   ```bash
   .venv/bin/pipeline research bibliography projects/my-film --write
   ```

## What blocks script approval

Blockers apply only to claims the narration actually uses (a scene's `claim_ids`).

| Code | Meaning | Can a reviewer except it? |
|---|---|---|
| `claim.critical_unreviewed` | critical claim is still `unverified` | yes |
| `claim.no_sources` | critical claim cites no sources | yes |
| `claim.partially_verified` / `claim.disputed` | critical claim isn't settled | yes |
| `quotation.no_excerpt` | quotation has no source excerpt with a page or timestamp | yes |
| `claim.rejected_in_use` | narration still uses a rejected claim | **no**: remove it |
| `claim.cites_retracted` | claim relies on a retracted source | **no**: replace the source |
| `script.unknown_claim` | `[claim:…]` marker points at a missing claim | **no** |
| `script.no_scenes` | nothing to approve | **no** |

The report also warns about these: verified claims whose sources aren't `checked`, unverified supporting claims, causal claims resting only on observational, anecdotal or opinion evidence (`evidence_basis`), unused sources, scenes that list no claims, and AI-suggested claims that nobody has reviewed yet.

## Exceptions

When a blocker must be accepted knowingly (for example, a claim presented explicitly as unresolved), an authorized reviewer records an exception with a written rationale:

```bash
.venv/bin/pipeline research exception projects/my-film claim-id --by "Editor" --rationale "Presented as an open question; narration says the evidence is mixed."
```

Exceptions are bound to the claim's current text, status and sources, so editing the claim cancels the exception. Withdraw one with `--revoke`.

## Approvals are auditable

- Every approval, revocation and exception is appended to `approvals.json` with the person's name and a timestamp. Nothing is ever edited in place.
- A script approval is bound to a fingerprint of the narration and the claims it uses. If either changes afterwards, the approval shows as **STALE** and must be given again.
- To limit who may approve, set `PIPELINE_AUTHORIZED_REVIEWERS="Name One, Name Two"`. Otherwise any named person may approve, and their name is always recorded.
- Project statuses from `script_approved` onward require a current approval, and `publication_ready` also requires zero research blockers. `pipeline project validate` enforces both.

## AI assistance (local models: Ollama recommended)

**Recommended on this Mac: Ollama with Qwen3 4B (4-bit).** It's quantized to 2.5 GB, so it fits in 8 GB of RAM:

```bash
.venv/bin/pipeline script draft projects/my-film --provider ollama --minutes 2
```

Measured on the demo with the same prompt: Qwen3 4B via Ollama took 1 min 40 s with 0 repeated sentences, 0 invented claim markers and 3 flags (all "claim not yet verified"). Qwen3 0.6B via Voicebox took 2.5 min, repeated itself, and invented a marker. Voicebox couldn't run Qwen3 1.7B on this Mac (it loads the model unquantized). Both providers are local; the Voicebox details below still apply when you use `--provider voicebox`.

### Voicebox Qwen3 (alternative)

AI help is optional and local. It uses the Qwen3 model built into the Voicebox app (Apache-2.0), so nothing leaves your Mac. Download a size in Voicebox → **Models**: **Qwen3 1.7B** is the default; 4B writes better but is slower on this CPU; 0.6B is fastest but weakest.

**Draft a script:**

```bash
.venv/bin/pipeline script draft projects/my-film --provider voicebox --minutes 3
```

- The AI sees only `brief.md` and the ledger's claims (rejected claims excluded). It's told to state facts only from those claims and tag each with `[claim:<id>]`, to hedge unverified claims, to show both sides of disputed ones, and to write `[NEEDS SOURCE: …]` where a fact is missing.
- It writes section by section, following the script template's headings, and adds generated source and visual notes.
- The draft goes to `script/drafts/draft-<time>.md`, which starts with an "AI DRAFT, NOT APPROVED" header recording the model and the brief and ledger fingerprints. It **never overwrites** `script.md` or `scenes.json`.
- **Automatic checks flag:** unknown or rejected claim markers, unverified claims used, sentences with numbers or quotes but no claim marker (likely invented), `[NEEDS SOURCE]` gaps, and sections that state no tagged facts.
- **Then you:** check every marked sentence against its source, resolve every flag, rewrite in your own voice, copy what you keep into `script/script.md`, run `pipeline script validate`, and approve as usual. A draft is never approved itself.

**Suggest claims to research:**

```bash
.venv/bin/pipeline research suggest projects/my-film --provider voicebox
```

Suggestions go to `research/notes/` and never to the ledger. Each starts `unverified`, with no sources and `origin: llm_suggestion`. **The model can never mark a claim verified.**

**Safety checks on the Voicebox LLM:**
- Before every call, the adapter reads Voicebox's settings and refuses if a custom remote LLM endpoint is configured.
- It refuses, rather than starting a download, if the chosen Qwen3 size isn't downloaded.
- It discards any reply that didn't come from a local Qwen3 size.
- Qwen3's `<think>` reasoning is stripped from all output.

Set `PIPELINE_LLM_PROVIDER=voicebox` and `PIPELINE_LLM_MODEL_SIZE=1.7B` to skip `--provider`.

## Editorial rules

- Distinguish evidence, interpretation, speculation and open questions in the script.
- Prefer primary sources and high-quality original research for important claims.
- Never invent citations, expert quotes, dialogue or historical artifacts.
- Present counter-evidence for disputed claims, and use correlational wording when the evidence is correlational.

## Human review checklist for the script

- [ ] Compelling central question and a clear thesis
- [ ] Every factual statement is tagged with a claim, and its sources have been read
- [ ] Counter-evidence and caveats are presented fairly
- [ ] Uncertainty is stated honestly, with no overclaiming from correlation
- [ ] Every section advances the argument
- [ ] Names, dates and numbers are checked against the sources

## Human review checklist for visuals

Run `pipeline visuals sheet` and review `reports/visuals.html`:

- [ ] Each visual communicates its beat's takeaway
- [ ] No visual implies evidence that doesn't exist; precise claims use evidence or an explanatory graphic, not generic montage
- [ ] Charts match their cited source, start at zero, and show the source on screen
- [ ] Reconstructions and AI illustrations are labelled on screen
- [ ] On-screen text is readable on a phone
- [ ] Motion has a purpose; no gratuitous transitions
- [ ] Every asset's rights are recorded (`pipeline assets report`)

Mark a beat reviewed by setting its `review_status` to `approved` in `visuals.json`, or `changes_requested` with notes.

The final-video checklist is added in Phase 8.
