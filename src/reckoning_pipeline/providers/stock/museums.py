"""Public-domain museum images via official open-access APIs (no key needed).

* **The Met** (https://metmuseum.github.io/): objects marked ``isPublicDomain``
  are released under CC0. Search uses ``/public/collection/v1.1/search`` (the
  v1 search was retired on 2026-10-01); each hit is then fetched from
  ``/public/collection/v1/objects/<id>``.
* **Art Institute of Chicago** (https://api.artic.edu/docs/): artworks with
  ``is_public_domain`` are CC0; images come from its IIIF server.

Only public-domain items with an image are ever returned, so nothing else can
be added. What leaves the machine: the search query or object id. Title,
artist and date are kept in ``StockItem.extra`` for on-screen labels.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from ...utils.http import urlopen as verified_urlopen
from .base import MediaKind, StockError, StockFile, StockItem, StockLicense

Opener = Callable[..., Any]
USER_AGENT = "reckoning-pipeline (local documentary tool)"
PACE_SECONDS = 0.25   # at most ~4 requests a second, well under the museums' published limits
RETRIES = 2


def _cc0(museum: str, url: str) -> StockLicense:
    return StockLicense(
        name="CC0 1.0 (public domain)", url=url, commercial_use=True, attribution_required=False,
        derivatives_allowed=True, raw_redistribution_allowed=True,
        notes=(f"{museum} releases images of public-domain works under CC0: free for any use, no permission or "
               "credit needed (credit is appreciated). The work itself is public domain; check the museum page "
               "still says so, and that no trademark or identifiable living person is shown."))


MET_LICENSE = _cc0("The Metropolitan Museum of Art", "https://www.metmuseum.org/policies/image-resources")
AIC_LICENSE = _cc0("The Art Institute of Chicago", "https://www.artic.edu/open-access/open-access-images")


class _MuseumAPI:
    name = ""
    display_name = ""
    media_hosts: tuple[str, ...] = ()
    license: StockLicense

    def __init__(self, *, opener: Opener = verified_urlopen, timeout: float = 30.0, max_lookups: int = 40,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._open = opener
        self._sleep = sleep
        self._last = 0.0
        self.timeout = timeout
        self.max_lookups = max_lookups

    def _get(self, url: str, headers: dict | None = None) -> dict:
        """GET JSON politely: paced requests, and a couple of retries if the server drops the connection."""
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        for attempt in range(RETRIES + 1):
            wait = PACE_SECONDS - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read() or b"{}")
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 502, 503) and attempt < RETRIES:
                    self._sleep(2 ** attempt)
                    continue
                hint = {404: "not found", 410: "this API endpoint was retired", 429: "rate limit reached; try later",
                        503: "the service is temporarily unavailable; try again later"}.get(exc.code, "")
                err = StockError(f"{self.display_name} API error {exc.code}{': ' + hint if hint else ''}")
                err.status = exc.code
                raise err from exc
            except (urllib.error.URLError, OSError) as exc:
                if attempt < RETRIES:
                    self._sleep(2 ** attempt)
                    continue
                raise StockError(f"can't reach the {self.display_name} API "
                                 f"({getattr(exc, 'reason', exc)})") from exc
            except ValueError as exc:
                raise StockError(f"the {self.display_name} API returned something that isn't JSON") from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _photos_only(kind: MediaKind) -> None:
        if kind != "photo":
            raise StockError("museum sources have still images only; use --type photo")


class MetProvider(_MuseumAPI):
    name = "met"
    display_name = "Met"
    media_hosts = ("images.metmuseum.org",)
    license = MET_LICENSE
    API = "https://collectionapi.metmuseum.org/public/collection"

    def search(self, query: str, kind: MediaKind = "photo", *, per_page: int = 10,
               orientation: str | None = None) -> list[StockItem]:
        self._photos_only(kind)
        if not query.strip():
            raise StockError("empty search query")
        params = urllib.parse.urlencode({"q": query.strip(), "hasImages": "true", "isPublicDomain": "true",
                                         "limit": min(max(per_page * 2, 4), self.max_lookups), "offset": 0})
        ids = self._get(f"{self.API}/v1.1/search?{params}").get("objectIDs") or []
        items = []
        for object_id in ids:
            try:
                item = self._object(object_id)
            except StockError as exc:
                if getattr(exc, "status", None) != 404:
                    raise
                continue  # the search index can list objects that are no longer published
            if item is not None:
                items.append(item)
            if len(items) >= per_page:
                break
        return items

    def get(self, kind: MediaKind, item_id: str) -> StockItem:
        self._photos_only(kind)
        if not item_id.isdigit():
            raise StockError(f"Met object ids are numeric, got {item_id!r}")
        item = self._object(int(item_id))
        if item is None:
            raise StockError(f"Met object {item_id} isn't public domain or has no image; it can't be used")
        return item

    def _object(self, object_id: int) -> StockItem | None:
        o = self._get(f"{self.API}/v1/objects/{object_id}")
        return met_item(o)


def met_item(o: dict) -> StockItem | None:
    image = o.get("primaryImage") or ""
    if not o.get("isPublicDomain") or not image:
        return None
    artist = o.get("artistDisplayName") or o.get("culture") or "Unknown maker"
    extra = {"title": o.get("title") or "", "artist": artist, "date": o.get("objectDate") or "",
             "museum": "The Metropolitan Museum of Art", "medium": o.get("medium") or "",
             "credit_line": o.get("creditLine") or "", "object_id": str(o.get("objectID"))}
    files = [StockFile(image, None, None, "image/jpeg", "original")]
    if o.get("primaryImageSmall"):
        files.append(StockFile(o["primaryImageSmall"], None, None, "image/jpeg", "small"))
    return StockItem("met", "photo", str(o.get("objectID")), o.get("objectURL") or "", artist, "", None, None,
                     None, _describe(extra), files, extra)


class AICProvider(_MuseumAPI):
    name = "aic"
    display_name = "Art Institute of Chicago"
    media_hosts = ("www.artic.edu", "artic.edu")
    license = AIC_LICENSE
    API = "https://api.artic.edu/api/v1/artworks"
    FIELDS = "id,title,artist_display,artist_title,date_display,image_id,is_public_domain,thumbnail,credit_line,medium_display"
    IIIF_WIDTH = 1686  # the largest size the museum recommends requesting

    def _headers(self) -> dict:
        return {"AIC-User-Agent": USER_AGENT}

    def search(self, query: str, kind: MediaKind = "photo", *, per_page: int = 10,
               orientation: str | None = None) -> list[StockItem]:
        self._photos_only(kind)
        if not query.strip():
            raise StockError("empty search query")
        params = urllib.parse.urlencode({"q": query.strip(), "query[term][is_public_domain]": "true",
                                         "limit": min(per_page * 2, self.max_lookups), "fields": self.FIELDS})
        data = self._get(f"{self.API}/search?{params}", self._headers())
        iiif = (data.get("config") or {}).get("iiif_url") or "https://www.artic.edu/iiif/2"
        items = [i for i in (aic_item(a, iiif) for a in data.get("data") or []) if i is not None]
        return items[:per_page]

    def get(self, kind: MediaKind, item_id: str) -> StockItem:
        self._photos_only(kind)
        if not item_id.isdigit():
            raise StockError(f"AIC artwork ids are numeric, got {item_id!r}")
        data = self._get(f"{self.API}/{item_id}?fields={self.FIELDS}", self._headers())
        iiif = (data.get("config") or {}).get("iiif_url") or "https://www.artic.edu/iiif/2"
        item = aic_item(data.get("data") or {}, iiif)
        if item is None:
            raise StockError(f"AIC artwork {item_id} isn't public domain or has no image; it can't be used")
        return item


def aic_item(a: dict, iiif_url: str) -> StockItem | None:
    if not a.get("is_public_domain") or not a.get("image_id"):
        return None
    thumb = a.get("thumbnail") or {}
    w, h = thumb.get("width"), thumb.get("height")
    width = AICProvider.IIIF_WIDTH
    height = round(width * h / w) if w and h else None
    artist = a.get("artist_title") or (a.get("artist_display") or "").split("\n")[0] or "Unknown maker"
    extra = {"title": a.get("title") or "", "artist": artist, "date": a.get("date_display") or "",
             "museum": "The Art Institute of Chicago", "medium": a.get("medium_display") or "",
             "credit_line": a.get("credit_line") or "", "object_id": str(a.get("id"))}
    url = f"{iiif_url.rstrip('/')}/{a['image_id']}/full/{width},/0/default.jpg"
    return StockItem("aic", "photo", str(a.get("id")), f"https://www.artic.edu/artworks/{a.get('id')}", artist, "",
                     width, height, None, _describe(extra), [StockFile(url, width, height, "image/jpeg", "iiif")],
                     extra)


def _describe(extra: dict) -> str:
    bits = [extra.get("title"), extra.get("artist"), extra.get("date")]
    return ", ".join(b for b in bits if b)
