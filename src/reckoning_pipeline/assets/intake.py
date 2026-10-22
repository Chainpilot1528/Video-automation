"""Manual asset intake: copy a user-supplied file in and record its provenance.

Originals are preserved: the source file is only read, the stored copy's
checksum must match the source, and the copy is made read-only. Derivatives
(crops, conversions, edits) are registered separately and point back to the
original. Nothing is ever approved at intake.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..schemas import Asset, AssetRegistry, ProjectManifest
from ..schemas.asset import AssetRoot, CommercialUse, PublicationStatus, ReviewStatus
from ..utils.fs import safe_resolve, sha256_file, write_json_atomic

ORIGINALS_DIR = "assets/originals"
DERIVED_DIR = "assets/derived"
GIB = 1024**3
# Fields a derivative inherits from its original: the rights travel with the content.
INHERITED_FIELDS = (
    "type", "creation_method", "provider", "source_url", "creator", "rights_holder", "license_name",
    "license_url", "commercial_use", "attribution_required", "attribution_text", "derivatives_allowed",
    "rights_evidence", "generation", "identifiable_people", "people_clearance", "trademarks_visible",
    "trademark_notes", "raw_redistribution_allowed", "platform_cleared",
)


class IntakeError(ValueError):
    """The asset cannot be ingested as requested."""


@dataclass
class IntakePlan:
    asset: Asset
    source: Path
    destination: Path

    def describe(self) -> list[str]:
        a = self.asset
        return [
            f"Copy {self.source} -> {self.destination}",
            f"Register {a.asset_id}: {a.type}, {a.creation_method}, sha256 {a.sha256[:12]}…",
            f"Status: review {a.review_status}, publication {a.publication_status}",
        ]


def _base_dir(project_dir: Path, root: AssetRoot, media_root: Path | None) -> Path:
    if root is AssetRoot.MEDIA:
        if media_root is None:
            raise IntakeError("--media needs PIPELINE_MEDIA_ROOT to be set")
        return media_root
    return project_dir


def asset_file(project_dir: Path, asset: Asset, media_root: Path | None) -> Path:
    """Where a registered asset's file lives."""
    return safe_resolve(_base_dir(project_dir, asset.root, media_root), asset.path)


def _check_source(source: Path) -> None:
    if not source.is_file():
        raise IntakeError(f"{source} is not a file")


def _check_disk(destination: Path, size: int, min_free_gb: float) -> None:
    probe = destination.parent
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free - size < min_free_gb * GIB:
        raise IntakeError(f"not enough disk space: {free / GIB:.1f} GiB free, need {size / GIB:.2f} GiB "
                          f"plus the {min_free_gb:g} GiB safety margin")


def plan_intake(project_dir: Path, registry: AssetRegistry, source: Path, fields: dict[str, Any], *,
                root: AssetRoot = AssetRoot.PROJECT, media_root: Path | None = None,
                folder: str = ORIGINALS_DIR) -> IntakePlan:
    """Validate everything and compute the record, without writing anything."""
    _check_source(source)
    asset_id = fields.get("asset_id", "")
    if any(a.asset_id == asset_id for a in registry.assets):
        raise IntakeError(f"asset_id {asset_id!r} already exists in the registry")
    for forbidden in ("path", "sha256", "root", "review_status", "publication_status"):
        if forbidden in fields:
            raise IntakeError(f"'{forbidden}' is set by intake and cannot be supplied")

    rel = f"{folder}/{asset_id}{source.suffix.lower()}"
    destination = safe_resolve(_base_dir(project_dir, root, media_root), rel)
    if destination.exists():
        raise IntakeError(f"{destination} already exists; not overwriting it")

    # Never approved at intake. Assets that clearly cannot be used start blocked.
    status = (PublicationStatus.BLOCKED if fields.get("commercial_use") == CommercialUse.NOT_ALLOWED
              else PublicationStatus.PENDING_REVIEW)
    record = {"acquired_date": date.today(), **fields, "path": rel, "root": root,
              "sha256": sha256_file(source), "review_status": ReviewStatus.PENDING,
              "publication_status": status}
    try:
        asset = Asset.model_validate(record)
    except ValidationError as exc:
        raise IntakeError("; ".join(f"{'.'.join(map(str, e['loc'])) or 'record'}: "
                                    f"{e['msg'].removeprefix('Value error, ')}" for e in exc.errors())) from exc
    return IntakePlan(asset, source, destination)


def plan_derivative(project_dir: Path, registry: AssetRegistry, parent_id: str, source: Path,
                    asset_id: str, *, notes: str = "", media_root: Path | None = None) -> IntakePlan:
    parents = {a.asset_id: a for a in registry.assets}
    if parent_id not in parents:
        raise IntakeError(f"unknown parent asset {parent_id!r}")
    parent = parents[parent_id]
    if parent.derivatives_allowed is False:
        raise IntakeError(f"{parent_id!r} does not allow derivatives (derivatives_allowed: false)")
    inherited = {k: getattr(parent, k) for k in INHERITED_FIELDS}
    fields = {**inherited, "asset_id": asset_id, "derived_from": parent_id,
              "intended_scene_ids": list(parent.intended_scene_ids),
              "notes": notes or f"Derived from {parent_id}."}
    return plan_intake(project_dir, registry, source, fields, root=parent.root, media_root=media_root,
                       folder=DERIVED_DIR)


def apply_intake(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry, plan: IntakePlan,
                 *, min_free_gb: float = 0.0) -> AssetRegistry:
    """Copy the file (verifying its checksum), make it read-only, then register it."""
    size = plan.source.stat().st_size
    _check_disk(plan.destination, size, min_free_gb)
    plan.destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = plan.destination.with_name(plan.destination.name + ".partial")
    try:
        shutil.copyfile(plan.source, tmp)
        if sha256_file(tmp) != plan.asset.sha256:
            raise IntakeError("copied file does not match the source checksum; nothing was registered")
        os.chmod(tmp, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.replace(tmp, plan.destination)
    finally:
        if tmp.exists():
            os.chmod(tmp, stat.S_IWUSR | stat.S_IRUSR)
            tmp.unlink()

    updated = AssetRegistry(assets=[*registry.assets, plan.asset])
    save_registry(project_dir, manifest, updated)
    return updated


def save_registry(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry) -> None:
    checked = AssetRegistry.model_validate(registry.model_dump())
    write_json_atomic(safe_resolve(project_dir, manifest.paths.asset_registry), checked.model_dump(mode="json"))
