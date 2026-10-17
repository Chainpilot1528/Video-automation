"""Derive approval state from the append-only approval log.

Fingerprints bind each approval to the exact content a person reviewed:
editing narration, claim wording, claim status, or cited sources after an
approval makes it stale rather than silently carrying it over.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .schemas import ApprovalEvent, ApprovalLog, ProjectManifest, ResearchLedger, SceneManifest
from .schemas.approval import ApprovalKind
from .schemas.common import utcnow
from .schemas.asset import Asset
from .schemas.research import Claim
from .utils.fs import safe_resolve, write_json_atomic


def _digest(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def claim_fingerprint(claim: Claim) -> str:
    return _digest({
        "claim_id": claim.claim_id, "text": claim.text, "claim_type": claim.claim_type,
        "importance": claim.importance, "verification_status": claim.verification_status,
        "source_ids": sorted(claim.source_ids),
    })


# Review/publication state is the outcome of a review, not part of what was reviewed.
_ASSET_UNFINGERPRINTED = {"review_status", "publication_status", "notes", "intended_scene_ids"}


def asset_fingerprint(asset: Asset) -> str:
    """Fingerprint of an asset's file checksum and every rights/provenance field."""
    return _digest(asset.model_dump(mode="json", exclude=_ASSET_UNFINGERPRINTED))


def asset_approval_state(log: ApprovalLog, asset: Asset) -> Literal["none", "approved", "stale", "blocked"]:
    events = [e for e in log.events if e.asset_id == asset.asset_id]
    if not events:
        return "none"
    last = events[-1]
    if last.kind is ApprovalKind.ASSET_BLOCKED:
        return "blocked"
    return "approved" if last.fingerprint == asset_fingerprint(asset) else "stale"


def script_fingerprint(scenes: SceneManifest, ledger: ResearchLedger) -> str:
    """Fingerprint of the narration and every claim it relies on."""
    claims = {c.claim_id: c for c in ledger.claims}
    used = sorted({cid for s in scenes.scenes for cid in s.claim_ids})
    return _digest({
        "scenes": [
            {"scene_id": s.scene_id, "order": s.order, "narration_text": s.narration_text,
             "on_screen_text": s.on_screen_text, "claim_ids": sorted(s.claim_ids),
             "source_ids": sorted(s.source_ids)}
            for s in sorted(scenes.scenes, key=lambda s: s.order)
        ],
        "claims": [claim_fingerprint(claims[c]) for c in used if c in claims],
    })


@dataclass(frozen=True)
class ScriptApprovalState:
    status: Literal["none", "approved", "stale", "revoked"]
    event: ApprovalEvent | None = None

    def describe(self) -> str:
        if self.event is None:
            return "not approved"
        when = self.event.at.date().isoformat()
        return {
            "approved": f"approved by {self.event.by} on {when}",
            "stale": f"STALE: approved by {self.event.by} on {when}, but narration or claims changed since",
            "revoked": f"revoked by {self.event.by} on {when}",
        }[self.status]


def script_approval_state(log: ApprovalLog, current_fingerprint: str) -> ScriptApprovalState:
    relevant = [e for e in log.events
                if e.kind in (ApprovalKind.SCRIPT_APPROVED, ApprovalKind.SCRIPT_APPROVAL_REVOKED)]
    if not relevant:
        return ScriptApprovalState("none")
    last = relevant[-1]
    if last.kind is ApprovalKind.SCRIPT_APPROVAL_REVOKED:
        return ScriptApprovalState("revoked", last)
    status = "approved" if last.fingerprint == current_fingerprint else "stale"
    return ScriptApprovalState(status, last)


def active_exceptions(log: ApprovalLog, ledger: ResearchLedger) -> dict[str, ApprovalEvent]:
    """Claim exceptions still in force: not revoked, and the claim is unchanged."""
    claims = {c.claim_id: c for c in ledger.claims}
    latest: dict[str, ApprovalEvent] = {}
    for e in log.events:
        if e.kind in (ApprovalKind.CLAIM_EXCEPTION, ApprovalKind.CLAIM_EXCEPTION_REVOKED):
            latest[e.claim_id] = e
    return {
        cid: e for cid, e in latest.items()
        if e.kind is ApprovalKind.CLAIM_EXCEPTION and cid in claims
        and e.fingerprint == claim_fingerprint(claims[cid])
    }


def load_log(project_dir: Path, manifest: ProjectManifest) -> ApprovalLog:
    path = safe_resolve(project_dir, manifest.paths.approvals)
    if not path.exists():
        return ApprovalLog()
    return ApprovalLog.model_validate_json(path.read_text(encoding="utf-8"))


def append_event(project_dir: Path, manifest: ProjectManifest, log: ApprovalLog, *,
                 kind: ApprovalKind, by: str, rationale: str = "", fingerprint: str | None = None,
                 claim_id: str | None = None, asset_id: str | None = None,
                 at: datetime | None = None) -> ApprovalEvent:
    """Validate and append one event, then write the log atomically."""
    event = ApprovalEvent(
        event_id=f"evt-{len(log.events) + 1:04d}", kind=kind, by=by, at=at or utcnow(),
        rationale=rationale, fingerprint=fingerprint, claim_id=claim_id, asset_id=asset_id,
    )
    updated = ApprovalLog(events=[*log.events, event])
    path = safe_resolve(project_dir, manifest.paths.approvals)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, updated.model_dump(mode="json"))
    return event


def check_reviewer(by: str, authorized: list[str]) -> None:
    """Raise ValueError unless ``by`` is a named, (if configured) authorized reviewer."""
    if not by.strip():
        raise ValueError("a reviewer name is required (--by)")
    if authorized and by.strip() not in authorized:
        raise ValueError(f"{by!r} is not in PIPELINE_AUTHORIZED_REVIEWERS ({', '.join(authorized)})")
