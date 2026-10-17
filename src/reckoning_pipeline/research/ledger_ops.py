"""Edit the research ledger: import records and record human claim reviews.

Every change is re-validated through the schema before it is written, and
written atomically. Nothing here can mark a claim verified on its own: a
review needs a named person, and imported AI suggestions must stay unverified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from ..schemas import ProjectManifest, ResearchLedger
from ..schemas.common import Record
from ..schemas.research import Claim, ClaimOrigin, ClaimStatus, Source
from ..utils.fs import safe_resolve, write_json_atomic


class LedgerError(ValueError):
    """A ledger edit that cannot be applied."""


class ResearchImport(Record):
    """File format for ``pipeline research import``: sources and/or claims."""

    schema_version: Literal["1.0"] = "1.0"
    note: str = ""
    sources: list[Source] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


@dataclass
class ImportSummary:
    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)


def save_ledger(project_dir: Path, manifest: ProjectManifest, ledger: ResearchLedger) -> None:
    # Round-trip through the model so a cross-field mistake can never be written.
    checked = ResearchLedger.model_validate(ledger.model_dump())
    write_json_atomic(safe_resolve(project_dir, manifest.paths.research_ledger), checked.model_dump(mode="json"))


def parse_import(text: str) -> ResearchImport:
    try:
        return ResearchImport.model_validate_json(text)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:10])
        raise LedgerError(f"import file is invalid: {problems}") from exc


def import_records(ledger: ResearchLedger, incoming: ResearchImport, *,
                   replace: bool = False) -> tuple[ResearchLedger, ImportSummary]:
    for c in incoming.claims:
        if c.origin is ClaimOrigin.LLM_SUGGESTION and c.verification_status is not ClaimStatus.UNVERIFIED:
            raise LedgerError(f"claim {c.claim_id!r} is an AI suggestion and must be imported as 'unverified'")

    summary = ImportSummary()
    sources = {s.source_id: s for s in ledger.sources}
    claims = {c.claim_id: c for c in ledger.claims}
    for pool, records, key in ((sources, incoming.sources, "source_id"), (claims, incoming.claims, "claim_id")):
        for record in records:
            rid = getattr(record, key)
            if rid in pool:
                if not replace:
                    raise LedgerError(f"{key} {rid!r} already exists; use --replace to overwrite it")
                summary.replaced.append(rid)
            else:
                summary.added.append(rid)
            pool[rid] = record
    return ResearchLedger(sources=list(sources.values()), claims=list(claims.values())), summary


def review_claim(ledger: ResearchLedger, claim_id: str, *, status: ClaimStatus, by: str,
                 on: date, note: str = "") -> ResearchLedger:
    """Record a human review decision on one claim."""
    claims = {c.claim_id: c for c in ledger.claims}
    if claim_id not in claims:
        raise LedgerError(f"unknown claim_id {claim_id!r}")
    data = claims[claim_id].model_dump()
    if status is ClaimStatus.UNVERIFIED:
        data.update(verification_status=status, reviewer=None, review_date=None)
    else:
        data.update(verification_status=status, reviewer=by.strip(), review_date=on)
    if note:
        data["review_notes"] = (data["review_notes"] + "\n" if data["review_notes"] else "") + \
            f"{on.isoformat()} {by.strip()}: {note.strip()}"
    try:
        updated = Claim.model_validate(data)
    except ValidationError as exc:
        raise LedgerError("; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())) from exc
    return ResearchLedger(sources=ledger.sources,
                          claims=[updated if c.claim_id == claim_id else c for c in ledger.claims])
