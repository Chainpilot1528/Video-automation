"""Render a graphic spec to SVG and register it as an original-graphic asset."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..assets.intake import save_registry
from ..schemas import Asset, AssetRegistry, ProjectManifest, ResearchLedger
from ..schemas.visual import GraphicSpec
from ..utils.fs import safe_resolve, write_text_atomic
from .svg import GraphicError, render_spec

GRAPHICS_DIR = "assets/graphics"
DEFAULT_CREATOR = "Reckoning Self"


@dataclass
class RenderedGraphic:
    asset: Asset
    path: Path
    unchanged: bool


def render_graphic(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry, ledger: ResearchLedger,
                   spec: GraphicSpec, *, spec_name: str = "", creator: str = DEFAULT_CREATOR,
                   dry_run: bool = False) -> RenderedGraphic:
    svg = render_spec(spec, ledger)
    sha = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    rel = f"{GRAPHICS_DIR}/{spec.asset_id}.svg"
    out = safe_resolve(project_dir, rel)
    existing = next((a for a in registry.assets if a.asset_id == spec.asset_id), None)

    if existing is not None or out.exists():
        same_file = out.exists() and hashlib.sha256(out.read_bytes()).hexdigest() == sha
        if existing is not None and existing.sha256 == sha and same_file:
            return RenderedGraphic(existing, out, unchanged=True)
        raise GraphicError(f"{spec.asset_id!r} already exists with different content; never overwritten. "
                           "Give the new version a new asset_id (e.g. add -v2).")

    data_note = ""
    if spec.source_ids:
        data_note = f" Data from {', '.join(spec.source_ids)}" + (f" ({spec.data_locator})" if spec.data_locator else "") + "."
    asset = Asset.model_validate({
        "asset_id": spec.asset_id, "path": rel, "type": "graphic", "creation_method": "original_graphic",
        "provider": "reckoning-pipeline graphics", "creator": creator, "rights_holder": creator,
        "license_name": "Original work, all rights reserved", "commercial_use": "allowed",
        "attribution_required": False, "derivatives_allowed": True,
        "rights_evidence": f"Rendered deterministically by 'pipeline graphics render'{f' from {spec_name}' if spec_name else ''}; "
                           f"no third-party imagery or embedded fonts.{data_note}",
        "sha256": sha, "intended_scene_ids": spec.intended_scene_ids,
        "notes": f"{spec.kind}: {spec.title}",
    })
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(out, svg)
        save_registry(project_dir, manifest, AssetRegistry(assets=[*registry.assets, asset]))
    return RenderedGraphic(asset, out, unchanged=False)
