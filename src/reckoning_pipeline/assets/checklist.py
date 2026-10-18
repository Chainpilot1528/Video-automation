"""Record the rights-checklist answers a person gives after inspecting an asset."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from ..schemas import Asset, AssetRegistry, ProjectManifest
from .intake import save_registry

CHECKLIST_FIELDS = ("identifiable_people", "people_clearance", "trademarks_visible", "trademark_notes",
                    "derivatives_allowed", "platform_cleared", "raw_redistribution_allowed")


class ChecklistError(ValueError):
    """The answers can't be recorded."""


def record_checklist(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry, asset_id: str,
                     answers: dict) -> Asset:
    unknown = set(answers) - set(CHECKLIST_FIELDS)
    if unknown:
        raise ChecklistError(f"not checklist fields: {sorted(unknown)}")
    if not answers:
        raise ChecklistError("give at least one answer (e.g. --people no --trademarks no)")
    current = next((a for a in registry.assets if a.asset_id == asset_id), None)
    if current is None:
        raise ChecklistError(f"unknown asset_id {asset_id!r}")
    try:
        # Changing rights answers is a new decision: any earlier approval becomes stale via its fingerprint.
        updated = Asset.model_validate({**current.model_dump(), **answers})
    except ValidationError as exc:
        raise ChecklistError("; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())) from exc
    save_registry(project_dir, manifest,
                  AssetRegistry(assets=[updated if a.asset_id == asset_id else a for a in registry.assets]))
    return updated
