"""Human rights review of an asset: approve for publication, or block it.

Each decision is appended to the approval log with a fingerprint of the
asset's file checksum and rights fields, so a later edit to either makes the
approval stale.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError

from ..approvals import append_event, asset_fingerprint, check_reviewer
from ..schemas import ApprovalEvent, ApprovalLog, Asset, AssetRegistry, ProjectManifest
from ..schemas.approval import ApprovalKind
from ..schemas.asset import PublicationStatus, ReviewStatus
from .intake import save_registry


class Decision(StrEnum):
    APPROVE = "approve"
    BLOCK = "block"


class AssetReviewError(ValueError):
    """The review decision cannot be recorded."""


def review_asset(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry, log: ApprovalLog,
                 asset_id: str, *, decision: Decision, by: str, note: str = "",
                 authorized: list[str] | None = None) -> tuple[Asset, ApprovalEvent]:
    check_reviewer(by, authorized or [])
    assets = {a.asset_id: a for a in registry.assets}
    if asset_id not in assets:
        raise AssetReviewError(f"unknown asset_id {asset_id!r}")
    current = assets[asset_id]

    if decision is Decision.APPROVE:
        update = {"review_status": ReviewStatus.APPROVED, "publication_status": PublicationStatus.APPROVED}
        kind = ApprovalKind.ASSET_APPROVED
    else:
        if not note.strip():
            raise AssetReviewError("blocking an asset needs a reason (--note)")
        update = {"review_status": ReviewStatus.REJECTED, "publication_status": PublicationStatus.BLOCKED}
        kind = ApprovalKind.ASSET_BLOCKED

    try:
        updated = Asset.model_validate({**current.model_dump(), **update})
    except ValidationError as exc:
        reasons = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
        raise AssetReviewError(f"cannot approve {asset_id}: {reasons}") from exc

    event = append_event(project_dir, manifest, log, kind=kind, by=by.strip(), rationale=note,
                         fingerprint=asset_fingerprint(updated) if kind is ApprovalKind.ASSET_APPROVED else None,
                         asset_id=asset_id)
    save_registry(project_dir, manifest, AssetRegistry(
        assets=[updated if a.asset_id == asset_id else a for a in registry.assets]))
    return updated, event
