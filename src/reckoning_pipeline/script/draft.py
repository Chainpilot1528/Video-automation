"""AI-assisted script drafting from the brief and the research ledger.

The model is a drafting aid, never a source:

* It sees only the project brief and the ledger's (non-rejected) claims, and
  is told to state facts only from those claims, tagging each with
  ``[claim:<id>]``, and to write ``[NEEDS SOURCE: ...]`` where a fact is missing.
* Its output is checked deterministically afterwards: unknown or rejected
  claim markers, unverified claims, and sentences with numbers or quotes but
  no claim marker are flagged.
* The draft goes to ``script/drafts/`` and never overwrites ``script.md`` or
  ``scenes.json``. A person edits it; approval stays a separate human step.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..project.validate import ValidationResult
from ..providers.llm.base import LLMProvider
from ..providers.llm.voicebox_llm import strip_thinking
from ..schemas.research import Claim, ClaimStatus
from ..utils.fs import safe_resolve, write_text_atomic

DRAFTS_DIR = "script/drafts"
WORDS_PER_MINUTE = 150
CLAIM_MARKER = re.compile(r"\[\s*claim\s*:\s*([A-Za-z0-9_-]+)\s*\]", re.IGNORECASE)
NEEDS_SOURCE = re.compile(r"\[NEEDS SOURCE:\s*([^\]]+)\]", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
FACT_HINT = re.compile(r"\d|[“”\"]")  # numbers, years, percentages, quotes

# (heading, share of the word budget, instruction). Headings match the script template.
SECTIONS = [
    ("Cold open / question", 0.12, "Open with the central question in a few vivid sentences. Raise curiosity; "
                                   "don't answer it yet."),
    ("Stakes and context", 0.20, "Explain why the question matters now and give the background the viewer needs."),
    ("Investigation", 0.28, "Walk through the evidence step by step, one idea per paragraph."),
    ("Evidence and counter-evidence", 0.24, "Give the strongest evidence, then the best counter-evidence and "
                                            "caveats fairly. Disputed claims must show both sides."),
    ("Resolution or honest uncertainty", 0.16, "Say what the evidence supports and what remains unknown. "
                                               "Do not overclaim."),
]

SYSTEM_PROMPT = """You draft narration for an evidence-led documentary. Rules you must follow:
1. State facts ONLY from the CLAIMS list. At the END of every sentence that uses a claim, add that claim's exact marker copied from the CLAIMS list. Never make up a marker.
2. Never invent numbers, dates, names, studies, quotes or sources. If the story needs a fact that is not in CLAIMS, write [NEEDS SOURCE: what is needed] instead.
3. Claims marked UNVERIFIED must be hedged ("early evidence suggests", "reportedly"). Claims marked DISPUTED must mention the counter-evidence.
4. Clearly label interpretation ("this suggests"), speculation ("one possibility is") and open questions.
5. Do not suggest correlation proves causation.
6. Write plain spoken narration: short sentences, no headings, no lists, no stage directions.
7. Do not repeat sentences from the script so far; every section must add something new.
"""


class DraftError(RuntimeError):
    """The draft could not be produced."""


@dataclass
class DraftFlag:
    kind: str  # unknown_claim | rejected_claim | unverified_claim | unsourced_fact | needs_source | no_claims
    #            | repeated | cut_off
    section: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind} ({self.section}): {self.detail}"


@dataclass
class DraftResult:
    path: Path
    sections: dict[str, str] = field(default_factory=dict)
    flags: list[DraftFlag] = field(default_factory=list)
    claims_used: list[str] = field(default_factory=list)
    words: int = 0


def claims_block(claims: list[Claim]) -> str:
    lines = []
    for c in claims:
        if c.verification_status is ClaimStatus.REJECTED:
            continue
        status = {ClaimStatus.VERIFIED: "verified", ClaimStatus.PARTIALLY_VERIFIED: "PARTIALLY VERIFIED - hedge it",
                  ClaimStatus.UNVERIFIED: "UNVERIFIED - hedge it", ClaimStatus.DISPUTED: "DISPUTED - give both sides"
                  }[c.verification_status]
        line = f"[claim:{c.claim_id}] ({status}; {c.claim_type}) {c.text}"
        if c.caveats:
            line += " Caveats: " + "; ".join(c.caveats)
        if c.counter_evidence:
            line += " Counter-evidence: " + "; ".join(c.counter_evidence)
        lines.append(line)
    return "\n".join(lines) or "(no claims yet: write [NEEDS SOURCE: ...] for every fact)"


def section_prompt(brief: str, claims: str, so_far: str, heading: str, instruction: str, words: int) -> str:
    tail = so_far[-1500:] if so_far else "(nothing yet)"
    return (f"BRIEF:\n{brief.strip()[:6000]}\n\nCLAIMS (the only facts you may state):\n{claims}\n\n"
            f"SCRIPT SO FAR (end):\n{tail}\n\n"
            f"Now write the section \"{heading}\" in about {words} words. {instruction} "
            "Output only the narration for this section. /no_think")


def clean_section(text: str, heading: str) -> str:
    text = strip_thinking(text)  # any provider's reasoning blocks must never reach the draft
    lines = [ln for ln in text.strip().splitlines() if not ln.lstrip().startswith("#")]
    out = "\n".join(lines).strip()
    if out.lower().startswith(heading.lower()):
        out = out[len(heading):].lstrip(" :\n")
    # Normalise marker spelling variants to [claim:id].
    return CLAIM_MARKER.sub(lambda m: f"[claim:{m.group(1).lower()}]", out)


def check_draft(sections: dict[str, str], claims: dict[str, Claim]) -> tuple[list[DraftFlag], list[str]]:
    flags: list[DraftFlag] = []
    used: list[str] = []
    for heading, text in sections.items():
        markers = CLAIM_MARKER.findall(text)
        for cid in markers:
            cid = cid.lower()
            claim = claims.get(cid)
            if claim is None:
                flags.append(DraftFlag("unknown_claim", heading, f"[claim:{cid}] is not in the ledger"))
                continue
            if cid not in used:
                used.append(cid)
            if claim.verification_status is ClaimStatus.REJECTED:
                flags.append(DraftFlag("rejected_claim", heading, f"uses rejected claim {cid}"))
        for gap in NEEDS_SOURCE.findall(text):
            flags.append(DraftFlag("needs_source", heading, gap.strip()))
        for sentence in SENTENCE.split(text):
            if FACT_HINT.search(sentence) and not CLAIM_MARKER.search(sentence) and not NEEDS_SOURCE.search(sentence):
                flags.append(DraftFlag("unsourced_fact", heading, sentence.strip()[:160]))
        if heading != SECTIONS[0][0] and text.strip() and not markers and not NEEDS_SOURCE.search(text):
            flags.append(DraftFlag("no_claims", heading, "section states no tagged facts; check it isn't asserting any"))
    flags += _repetition_flags(sections)
    for heading, text in sections.items():
        if text.strip() and text.rstrip()[-1] not in ".!?\"”)]":
            flags.append(DraftFlag("cut_off", heading, "section ends mid-sentence (model hit its length limit)"))
    for cid in used:
        if claims[cid].verification_status is not ClaimStatus.VERIFIED:
            flags.append(DraftFlag("unverified_claim", "-", f"{cid} is {claims[cid].verification_status}; verify before approval"))
    return flags, used


def _normalise(sentence: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", CLAIM_MARKER.sub("", sentence).lower()).split())


def _repetition_flags(sections: dict[str, str]) -> list[DraftFlag]:
    """Sentences (ignoring claim markers and punctuation) that appear more than once in the draft."""
    seen: dict[str, str] = {}
    flags = []
    for heading, text in sections.items():
        for sentence in SENTENCE.split(text):
            key = _normalise(sentence)
            if len(key.split()) < 6:
                continue
            if key in seen:
                flags.append(DraftFlag("repeated", heading, f"repeats a sentence from '{seen[key]}': "
                                                            f"{sentence.strip()[:100]}"))
            else:
                seen[key] = heading
    return flags


def visual_notes(used: list[str], claims: dict[str, Claim]) -> str:
    if not used:
        return "- No claims used yet."
    lines = []
    for cid in used:
        c = claims[cid]
        kind = ("chart from the cited data" if c.claim_type in ("statistical",) else
                "the source document itself" if c.claim_type in ("quotation", "historical") else
                "an explanatory diagram or primary evidence")
        lines.append(f"- [claim:{cid}] sources {', '.join(c.source_ids) or 'NONE'}; suggested visual: {kind}.")
    return "\n".join(lines)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def draft_script(result: ValidationResult, provider: LLMProvider, *, minutes: float = 2.0,
                 progress=None) -> DraftResult:
    if not result.ok:
        raise DraftError("project has validation errors; run 'pipeline project validate'")
    manifest = result.manifest
    brief = safe_resolve(result.project_dir, manifest.paths.brief).read_text(encoding="utf-8")
    if len(brief.split()) < 15:
        raise DraftError("the brief is nearly empty; write the central question and audience in brief.md first")
    claims = {c.claim_id: c for c in result.ledger.claims}
    block = claims_block(list(claims.values()))
    budget = max(int(minutes * WORDS_PER_MINUTE), 60)

    sections: dict[str, str] = {}
    so_far = ""
    for i, (heading, share, instruction) in enumerate(SECTIONS, 1):
        if progress:
            progress(i, len(SECTIONS), heading)
        words = max(int(budget * share), 25)
        raw = provider.complete(section_prompt(brief, block, so_far, heading, instruction, words),
                                system=SYSTEM_PROMPT, max_tokens=min(int(words * 2.2) + 80, 2048))
        text = clean_section(raw, heading)
        if not text:
            raise DraftError(f"the model returned nothing for '{heading}'")
        sections[heading] = text
        so_far += f"\n\n{text}"

    flags, used = check_draft(sections, claims)
    version = provider.version() if hasattr(provider, "version") else provider.name
    stamp = datetime.now(timezone.utc)
    body = [f"<!-- AI DRAFT, NOT APPROVED. {version}; {stamp.isoformat(timespec='seconds')}; "
            f"brief {_digest(brief)}; ledger {_digest(block)} -->",
            f"# Script draft: {manifest.title}", "",
            "> AI-generated draft for a human editor. Check every [claim:...] against its source, resolve every "
            "flag below, then copy what you keep into script/script.md. This file is never approved itself.", ""]
    for heading, text in sections.items():
        body += [f"## {heading}", "", text, ""]
    body += ["## Source and visual notes", "", visual_notes(used, claims), "", "## Review flags", ""]
    body += [f"- {f}" for f in flags] or ["- None found by the automatic checks (still review everything)."]

    rel = f"{DRAFTS_DIR}/draft-{stamp.strftime('%Y%m%dT%H%M%SZ')}.md"
    out = safe_resolve(result.project_dir, rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise DraftError(f"{out} already exists")
    write_text_atomic(out, "\n".join(body) + "\n")
    return DraftResult(out, sections, flags, used, sum(len(t.split()) for t in sections.values()))
