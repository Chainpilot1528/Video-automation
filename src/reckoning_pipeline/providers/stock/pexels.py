"""Pexels (https://www.pexels.com/api/): free stock photos and videos via the official API.

The API key comes only from ``PIPELINE_PEXELS_API_KEY`` in the environment;
it is sent solely in the ``Authorization`` header to api.pexels.com and is
never logged, stored in manifests, or included in error messages.
What leaves the machine: the search query (or item id) and the key.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from ...utils.http import urlopen as verified_urlopen
from typing import Any, Callable

from .base import MediaKind, StockError, StockFile, StockItem, StockLicense

API_BASE = "https://api.pexels.com"
KEY_ENV = "PIPELINE_PEXELS_API_KEY"
PEXELS_LICENSE = StockLicense(
    name="Pexels License",
    url="https://www.pexels.com/license/",
    commercial_use=True,
    attribution_required=False,
    derivatives_allowed=True,
    raw_redistribution_allowed=False,
    notes=("Free for commercial use, attribution appreciated but not required; modifications allowed. "
           "Not allowed: selling unaltered copies, implying endorsement by people or brands shown, "
           "showing identifiable people in a bad light. Check people and trademarks per clip."),
)
# Hosts Pexels serves media from; anything else is refused rather than downloaded.
MEDIA_HOSTS = ("pexels.com", "player.vimeo.com", "vimeocdn.com")

Opener = Callable[..., Any]


class PexelsProvider:
    name = "pexels"
    display_name = "Pexels"
    license = PEXELS_LICENSE
    media_hosts = MEDIA_HOSTS

    def __init__(self, api_key: str | None = None, *, base_url: str = API_BASE,
                 opener: Opener = verified_urlopen, timeout: float = 30.0) -> None:
        key = api_key if api_key is not None else os.environ.get(KEY_ENV, "")
        if not key.strip():
            raise StockError(f"no Pexels API key: set {KEY_ENV} in your shell profile (never in the repo)")
        self._key = key.strip()
        self.base_url = base_url.rstrip("/")
        self._open = opener
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = self.base_url + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"Authorization": self._key,
                                                   "User-Agent": "reckoning-pipeline"})
        try:
            with self._open(req, timeout=self.timeout) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            hint = {401: "the API key was rejected", 403: "access denied",
                    404: "not found", 429: "rate limit reached; try again later"}.get(exc.code, "")
            raise StockError(f"Pexels API error {exc.code}{': ' + hint if hint else ''}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise StockError(f"can't reach the Pexels API ({getattr(exc, 'reason', exc)})") from exc

    def search(self, query: str, kind: MediaKind, *, per_page: int = 10,
               orientation: str | None = None) -> list[StockItem]:
        if not query.strip():
            raise StockError("empty search query")
        params = {"query": query.strip(), "per_page": max(1, min(per_page, 40))}
        if orientation:
            params["orientation"] = orientation
        if kind == "video":
            data = self._get("/videos/search", params)
            return [_video(v) for v in data.get("videos", [])]
        data = self._get("/v1/search", params)
        return [_photo(p) for p in data.get("photos", [])]

    def get(self, kind: MediaKind, item_id: str) -> StockItem:
        if not item_id.isdigit():
            raise StockError(f"Pexels ids are numeric, got {item_id!r}")
        if kind == "video":
            return _video(self._get(f"/videos/videos/{item_id}"))
        return _photo(self._get(f"/v1/photos/{item_id}"))


def _video(v: dict) -> StockItem:
    user = v.get("user") or {}
    files = [StockFile(f["link"], f.get("width"), f.get("height"), f.get("file_type", ""), f.get("quality") or "")
             for f in v.get("video_files", []) if f.get("link")]
    return StockItem("pexels", "video", str(v["id"]), v.get("url", ""), user.get("name", ""), user.get("url", ""),
                     v.get("width"), v.get("height"), float(v["duration"]) if v.get("duration") else None,
                     "", files)


def _photo(p: dict) -> StockItem:
    src = p.get("src") or {}
    files = [StockFile(src[k], None, None, "image/jpeg", k) for k in ("large2x", "original", "large") if src.get(k)]
    return StockItem("pexels", "photo", str(p["id"]), p.get("url", ""), p.get("photographer", ""),
                     p.get("photographer_url", ""), p.get("width"), p.get("height"), None, p.get("alt") or "", files)


def is_media_host(url: str, hosts: tuple[str, ...] = MEDIA_HOSTS) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in hosts)
