"""Provider-neutral stock media search.

Stock adapters only *search* and *describe* items; downloading and
registering go through the normal asset intake (checksums, read-only
originals, rights checklist, human review). They use each site's official
API only: no scraping, no bypassing access controls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

MediaKind = Literal["video", "photo"]


class StockError(RuntimeError):
    """Search or download failed, or the provider isn't configured."""


@dataclass(frozen=True)
class StockFile:
    url: str             # direct media URL from the API
    width: int | None
    height: int | None
    file_type: str       # e.g. video/mp4, image/jpeg
    quality: str = ""


@dataclass(frozen=True)
class StockItem:
    provider: str
    kind: MediaKind
    item_id: str
    page_url: str        # the item's public page (recorded as source_url)
    creator: str
    creator_url: str
    width: int | None
    height: int | None
    duration_seconds: float | None = None
    description: str = ""
    files: list[StockFile] = field(default_factory=list)

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.kind}:{self.item_id}"


@dataclass(frozen=True)
class StockLicense:
    name: str
    url: str
    commercial_use: bool
    attribution_required: bool
    derivatives_allowed: bool
    raw_redistribution_allowed: bool
    notes: str


class StockProvider(Protocol):
    name: str
    license: StockLicense

    def search(self, query: str, kind: MediaKind, *, per_page: int = 10, orientation: str | None = None) -> list[StockItem]:
        ...

    def get(self, kind: MediaKind, item_id: str) -> StockItem:
        ...
