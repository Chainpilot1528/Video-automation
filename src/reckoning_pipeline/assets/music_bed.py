"""Create, register and attach music beds."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .. import __version__
from ..media.audio import Tools
from ..media.music import KEYS, PAD_VERSION, generate_pad
from ..schemas import Asset, AssetRegistry, ProjectManifest
from ..schemas.project import MusicSettings
from ..utils.fs import safe_resolve, sha256_file, write_json_atomic
from .intake import IntakeError, save_registry

MUSIC_DIR = "assets/music"


def create_pad(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry, tools: Tools, asset_id: str, *,
               duration: float, key: str = "A") -> Asset:
    """Synthesize an original ambient pad and register it (pending human review, rights fully documented)."""
    if any(a.asset_id == asset_id for a in registry.assets):
        raise IntakeError(f"asset_id {asset_id!r} already exists")
    rel = f"{MUSIC_DIR}/{asset_id}.wav"
    out = safe_resolve(project_dir, rel)
    if out.exists():
        raise IntakeError(f"{out} already exists; not overwriting it")
    generate_pad(tools, out, duration=duration, key=key)
    asset = Asset.model_validate({
        "asset_id": asset_id, "path": rel, "type": "music", "creation_method": "generated",
        "provider": "reckoning-pipeline", "creator": "Reckoning Self", "rights_holder": "Reckoning Self",
        "commercial_use": "allowed", "attribution_required": False, "derivatives_allowed": True,
        "raw_redistribution_allowed": True, "platform_cleared": True,
        "rights_evidence": ("Synthesized from sine oscillators and filtered noise by 'pipeline music pad' "
                            f"(pad v{PAD_VERSION}); no samples, loops or third-party recordings, so no Content ID "
                            "match is possible."),
        "generation": {"provider": "reckoning-pipeline", "model": f"ambient-pad-v{PAD_VERSION}",
                       "model_version": __version__, "generated_on": date.today(),
                       "settings": {"key": key, "root_hz": KEYS[key], "duration": duration},
                       "terms_url": "https://ffmpeg.org/legal.html"},
        "sha256": sha256_file(out), "acquired_date": date.today(),
        "notes": "Original ambient bed (minor add9 chord, slow breathing, soft low pulse).",
    })
    save_registry(project_dir, manifest, AssetRegistry(assets=[*registry.assets, asset]))
    return asset


def set_music(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry, asset_id: str | None, *,
              gain_db: float = -14.0, duck: bool = True) -> ProjectManifest:
    """Attach (or with ``asset_id=None`` remove) the project's music bed."""
    if asset_id is not None:
        asset = next((a for a in registry.assets if a.asset_id == asset_id), None)
        if asset is None or asset.type != "music":
            raise IntakeError(f"{asset_id!r} is not a registered music asset")
        music = MusicSettings(asset_id=asset_id, gain_db=gain_db, duck=duck)
    else:
        music = None
    updated = manifest.model_copy(update={"music": music})
    write_json_atomic(safe_resolve(project_dir, "project.json"), updated.model_dump(mode="json"))
    return updated
