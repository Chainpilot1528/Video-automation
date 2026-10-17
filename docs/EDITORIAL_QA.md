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

## AI assistance

LLM help is optional, and none is enabled yet (Phase 9). When enabled, `pipeline research suggest` writes suggestions to `research/notes/` and never to the ledger. Every suggested claim starts `unverified`, with no sources and `origin: llm_suggestion`. A person has to find the sources, import the claim and review it. **The model can never mark a claim verified.**

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

Visual and final-video checklists are added in Phases 6 and 8.
