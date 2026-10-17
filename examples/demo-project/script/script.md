# Script draft: Anatomy of a Traceable Scene

Editorial draft only. Approved narration lives in `scenes.json`, one scene at a time.
Factual statements carry [claim:...] markers that point at the research ledger.

## Cold open / question
Every scene makes a promise: what you see and hear is backed by something real. *(Framing question, not a factual claim.)*

## Stakes and context
A claim is tracked separately from its source. It stays unverified until a named person reviews it. [claim:claim-review-required]

## Investigation
Every visual carries its paperwork: creator, licence, and a checksum that catches a changed file. [claim:claim-checksum-catches-changes]

## Evidence and counter-evidence
- Evidence: the schema and validator code cited in the ledger.
- Limitation: validation can't stop someone entering a false reviewer name. The claim's caveats say so.

## Resolution or honest uncertainty
Nothing publishes itself. People approve the script, the visuals and the final export. [claim:claim-no-auto-publish]
Open question: approval gates are design rules today; QA enforcement arrives in Phase 8.

## Source and visual notes
All four graphics are original SVGs produced by `scripts/build_demo_assets.py`. The sources are files in this repository.
