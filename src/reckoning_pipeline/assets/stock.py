"""Add a stock item to a project: pick a file, download it, register it via normal intake.

The licence fields come from the provider's reviewed licence. The questions
only a person can answer by watching the clip (identifiable people,
trademarks) are left unknown, so the asset can't be approved until someone
records them with ``pipeline assets checklist`` and reviews it.
"""

from __future__ import annotations

import shutil
import tempfile
import urllib.error
import urllib.request

from ..utils.http import urlopen as verified_urlopen
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from ..providers.stock import StockError, StockFile, StockItem, StockProvider
from ..providers.stock.pexels import is_media_host
from ..schemas import AssetRegistry, ProjectManifest
from ..schemas.asset import AssetRoot
from .intake import IntakePlan, apply_intake, plan_intake

MAX_DOWNLOAD_BYTES = 1_500_000_000  # refuse anything larger than ~1.5 GB
EXTENSIONS = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm", "image/jpeg": ".jpg",
              "image/png": ".png"}

Opener = Callable[..., Any]


def choose_file(item: StockItem, target_width: int) -> StockFile:
    """Largest file no wider than the target; otherwise the smallest wider one. Prefers MP4/JPEG."""
    preferred = [f for f in item.files if f.file_type in ("video/mp4", "image/jpeg")] or item.files
    if not preferred:
        raise StockError(f"{item.ref} has no downloadable files")
    sized = [f for f in preferred if f.width]
    if not sized:
        return preferred[0]
    fitting = [f for f in sized if f.width <= target_width]
    return max(fitting, key=lambda f: f.width) if fitting else min(sized, key=lambda f: f.width)


def existing_for(registry: AssetRegistry, item: StockItem) -> str | None:
    """asset_id already registered from this stock item, if any (the 'used footage' ledger)."""
    for a in registry.assets:
        if a.source_url and a.source_url.rstrip("/") == item.page_url.rstrip("/"):
            return a.asset_id
    return None


def stock_fields(item: StockItem, provider: StockProvider, asset_id: str, scenes: list[str],
                 chosen: StockFile) -> dict:
    lic = provider.license
    kind_word = "Video" if item.kind == "video" else "Photo"
    size = f"{chosen.width}x{chosen.height}" if chosen.width else chosen.quality
    if item.extra.get("museum"):
        return museum_fields(item, provider, asset_id, scenes, chosen, size)
    return {
        "asset_id": asset_id, "type": "video" if item.kind == "video" else "image",
        "creation_method": "downloaded", "source_url": item.page_url, "provider": provider.name.title(),
        "creator": item.creator, "rights_holder": item.creator,
        "license_name": lic.name, "license_url": lic.url,
        "commercial_use": "allowed" if lic.commercial_use else "not_allowed",
        "attribution_required": lic.attribution_required,
        "attribution_text": f"{kind_word} by {item.creator} on {provider.name.title()}",
        "derivatives_allowed": lic.derivatives_allowed,
        "raw_redistribution_allowed": lic.raw_redistribution_allowed,
        "rights_evidence": (f"{lic.name} ({lic.url}); retrieved via the {provider.name.title()} API on "
                            f"{date.today().isoformat()}; item {item.ref}; creator {item.creator} "
                            f"({item.creator_url}). {lic.notes}"),
        "intended_scene_ids": scenes,
        "notes": f"{item.ref}; file {size} {chosen.file_type}. People/trademarks not yet checked.",
    }


def museum_fields(item: StockItem, provider: StockProvider, asset_id: str, scenes: list[str], chosen: StockFile,
                  size: str) -> dict:
    """A public-domain artwork: the museum's CC0 release, with title/artist/date kept for labels."""
    lic, x = provider.license, item.extra
    label = "; ".join(f"{k}: {x[k]}" for k in ("title", "artist", "date", "medium") if x.get(k))
    return {
        "asset_id": asset_id, "type": "image", "creation_method": "downloaded", "source_url": item.page_url,
        "provider": x["museum"], "creator": item.creator, "rights_holder": f"Public domain ({x['museum']}, CC0)",
        "license_name": lic.name, "license_url": lic.url, "commercial_use": "allowed",
        "attribution_required": False,
        "attribution_text": f"{x.get('title') or 'Image'}, {item.creator}. {x['museum']}, CC0",
        "derivatives_allowed": True, "raw_redistribution_allowed": True,
        "rights_evidence": (f"{lic.name} ({lic.url}); marked public domain by the {x['museum']} API on "
                            f"{date.today().isoformat()}; object {x.get('object_id')} ({item.page_url}). "
                            f"Credit line: {x.get('credit_line') or 'n/a'}. {lic.notes}"),
        "intended_scene_ids": scenes,
        "notes": f"{item.ref}; {label}; file {size} {chosen.file_type}. People/trademarks not yet checked.",
    }


def download(url: str, dest: Path, *, opener: Opener = verified_urlopen, timeout: float = 120.0,
             max_bytes: int = MAX_DOWNLOAD_BYTES, hosts: tuple[str, ...] | None = None) -> int:
    if not is_media_host(url, *(() if hosts is None else (hosts,))):
        raise StockError(f"refusing to download from an unexpected host: {url[:80]}")
    req = urllib.request.Request(url, headers={"User-Agent": "reckoning-pipeline"})
    written = 0
    try:
        with opener(req, timeout=timeout) as resp, dest.open("wb") as out:
            length = resp.headers.get("Content-Length") if hasattr(resp, "headers") else None
            if length and int(length) > max_bytes:
                raise StockError(f"file is {int(length) / 1e9:.2f} GB; the limit is {max_bytes / 1e9:.1f} GB")
            while chunk := resp.read(1 << 20):
                written += len(chunk)
                if written > max_bytes:
                    raise StockError(f"download exceeded {max_bytes / 1e9:.1f} GB; stopped")
                out.write(chunk)
    except urllib.error.URLError as exc:
        raise StockError(f"download failed ({getattr(exc, 'reason', exc)})") from exc
    if written == 0:
        raise StockError("downloaded file is empty")
    return written


@dataclass
class StockAddResult:
    plan: IntakePlan
    item: StockItem
    chosen: StockFile
    bytes_downloaded: int


def add_stock_item(project_dir: Path, manifest: ProjectManifest, registry: AssetRegistry, provider: StockProvider,
                   item: StockItem, asset_id: str, *, scenes: list[str], target_width: int,
                   media_root: Path | None = None, use_media_root: bool = False, min_free_gb: float = 0.0,
                   dry_run: bool = False, opener: Opener = verified_urlopen) -> StockAddResult:
    used = existing_for(registry, item)
    if used:
        raise StockError(f"{item.ref} is already in this project as {used!r}; reuse that asset instead")
    chosen = choose_file(item, target_width)
    fields = stock_fields(item, provider, asset_id, scenes, chosen)
    ext = EXTENSIONS.get(chosen.file_type, ".mp4" if item.kind == "video" else ".jpg")
    root = AssetRoot.MEDIA if use_media_root else AssetRoot.PROJECT

    tmp_dir = Path(tempfile.mkdtemp(prefix="stock-"))
    try:
        tmp = tmp_dir / f"{asset_id}{ext}"
        if dry_run:
            tmp.write_bytes(b"dry-run placeholder")  # lets intake validate the record; never registered
            size = 0
        else:
            size = download(chosen.url, tmp, opener=opener, hosts=getattr(provider, "media_hosts", None))
        plan = plan_intake(project_dir, registry, tmp, fields, root=root, media_root=media_root)
        if not dry_run:
            apply_intake(project_dir, manifest, registry, plan, min_free_gb=min_free_gb)
        return StockAddResult(plan, item, chosen, size)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
