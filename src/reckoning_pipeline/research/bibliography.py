"""Source list for the video description, in narration order."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import ResearchLedger, SceneManifest, Source
from ..schemas.research import SourceStatus, SourceType


@dataclass
class Bibliography:
    entries: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # source_id -> reason

    def to_markdown(self, title: str) -> str:
        lines = [f"# Sources: {title}", ""]
        lines += [f"{i}. {e}" for i, e in enumerate(self.entries, 1)] or ["_No public sources._"]
        return "\n".join(lines) + "\n"


def format_citation(s: Source) -> str:
    if s.citation_text:
        return s.citation_text
    parts = []
    if s.authors:
        parts.append(", ".join(s.authors))
    year = f" ({s.published_date.year})" if s.published_date else ""
    parts.append(f"{s.title}{year}")
    if s.publisher:
        parts.append(s.publisher)
    link = s.url or s.identifier or s.archive_id
    if link:
        parts.append(link)
    return ". ".join(parts) + "."


def build_bibliography(ledger: ResearchLedger, scenes: SceneManifest, *,
                       include_internal: bool = False) -> Bibliography:
    """Sources cited by scenes or by claims the scenes use, first appearance first."""
    claims = {c.claim_id: c for c in ledger.claims}
    sources = {s.source_id: s for s in ledger.sources}
    ordered: list[str] = []
    for scene in sorted(scenes.scenes, key=lambda s: s.order):
        ids = list(scene.source_ids)
        for cid in scene.claim_ids:
            ids += claims[cid].source_ids if cid in claims else []
        for sid in ids:
            if sid not in ordered:
                ordered.append(sid)

    bib = Bibliography()
    for sid in ordered:
        s = sources.get(sid)
        if s is None:
            bib.skipped[sid] = "not in ledger"
        elif s.verification_status is SourceStatus.RETRACTED:
            bib.skipped[sid] = "retracted"
        elif s.source_type is SourceType.INTERNAL_DOCUMENT and not include_internal:
            bib.skipped[sid] = "internal document"
        else:
            bib.entries.append(format_citation(s))
    return bib
