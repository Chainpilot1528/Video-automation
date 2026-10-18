"""Pexels adapter and stock intake, against a fake API (no network, no real key)."""

import io
import json
import urllib.error

import pytest

from reckoning_pipeline.assets import Decision, review_asset
from reckoning_pipeline.assets.checklist import ChecklistError, record_checklist
from reckoning_pipeline.assets.stock import add_stock_item, choose_file, download, existing_for
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.providers.stock import PexelsProvider, StockError, parse_ref
from reckoning_pipeline.providers.stock.pexels import is_media_host

VIDEO = {
    "id": 123, "url": "https://www.pexels.com/video/city-night-123/", "width": 3840, "height": 2160,
    "duration": 12, "user": {"name": "Asha Rao", "url": "https://www.pexels.com/@asha"},
    "video_files": [
        {"id": 1, "quality": "uhd", "file_type": "video/mp4", "width": 3840, "height": 2160,
         "link": "https://videos.pexels.com/video-files/123/uhd.mp4"},
        {"id": 2, "quality": "hd", "file_type": "video/mp4", "width": 1920, "height": 1080,
         "link": "https://videos.pexels.com/video-files/123/hd.mp4"},
        {"id": 3, "quality": "sd", "file_type": "video/mp4", "width": 960, "height": 540,
         "link": "https://videos.pexels.com/video-files/123/sd.mp4"},
    ],
}
PHOTO = {"id": 77, "url": "https://www.pexels.com/photo/desk-77/", "width": 6000, "height": 4000,
         "photographer": "Ben Lee", "photographer_url": "https://www.pexels.com/@ben", "alt": "A desk",
         "src": {"original": "https://images.pexels.com/photos/77/o.jpeg",
                 "large2x": "https://images.pexels.com/photos/77/l2.jpeg"}}


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakePexels:
    def __init__(self, status: int = 200):
        self.requests = []
        self.status = status

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.requests.append((url, dict(req.header_items())))
        if self.status != 200:
            raise urllib.error.HTTPError(url, self.status, "err", {}, io.BytesIO(b"{}"))
        if url.startswith("https://api.pexels.com/videos/search"):
            return FakeResponse(json.dumps({"videos": [VIDEO]}).encode())
        if url == "https://api.pexels.com/videos/videos/123":
            return FakeResponse(json.dumps(VIDEO).encode())
        if url.startswith("https://api.pexels.com/v1/search"):
            return FakeResponse(json.dumps({"photos": [PHOTO]}).encode())
        if url == "https://api.pexels.com/v1/photos/77":
            return FakeResponse(json.dumps(PHOTO).encode())
        if "pexels.com/video-files" in url or "images.pexels.com" in url:
            return FakeResponse(b"\x00\x00\x00\x18ftypmp42 fake media bytes", {"Content-Length": "33"})
        raise AssertionError(f"unexpected URL {url}")


@pytest.fixture
def api():
    return FakePexels()


def test_key_required_and_never_in_errors(monkeypatch):
    monkeypatch.delenv("PIPELINE_PEXELS_API_KEY", raising=False)
    with pytest.raises(StockError, match="PIPELINE_PEXELS_API_KEY"):
        PexelsProvider()
    secret = "SECRET-KEY-123"
    with pytest.raises(StockError) as exc:
        PexelsProvider(secret, opener=FakePexels(status=401)).search("x", "video")
    assert "rejected" in str(exc.value) and secret not in str(exc.value)


def test_search_sends_key_only_as_header_and_parses(api):
    p = PexelsProvider("KEY-XYZ-987", opener=api)
    items = p.search("city at night", "video", per_page=5)
    url, headers = api.requests[-1]
    assert "query=city+at+night" in url and "per_page=5" in url
    assert "KEY-XYZ-987" not in url and headers["Authorization"] == "KEY-XYZ-987"
    it = items[0]
    assert (it.ref, it.creator, it.duration_seconds, len(it.files)) == ("pexels:video:123", "Asha Rao", 12.0, 3)
    photo = p.search("desk", "photo")[0]
    assert photo.ref == "pexels:photo:77" and photo.files[0].quality == "large2x"


def test_errors_and_validation(api):
    p = PexelsProvider("k", opener=api)
    with pytest.raises(StockError, match="empty"):
        p.search("  ", "video")
    with pytest.raises(StockError, match="numeric"):
        p.get("video", "../x")
    with pytest.raises(StockError, match="rate limit"):
        PexelsProvider("k", opener=FakePexels(status=429)).get("video", "1")


def test_parse_ref():
    assert parse_ref("pexels:video:5") == ("pexels", "video", "5")
    assert parse_ref("pexels:photo:5") == ("pexels", "photo", "5")
    assert parse_ref("pexels:5") == ("pexels", "video", "5")
    with pytest.raises(StockError):
        parse_ref("pexels:gif:5")


def test_choose_file_prefers_largest_within_target(api):
    item = PexelsProvider("k", opener=api).get("video", "123")
    assert choose_file(item, 1920).width == 1920
    assert choose_file(item, 1000).width == 960
    assert choose_file(item, 500).width == 960  # nothing fits: smallest larger one


def test_download_refuses_other_hosts_and_size_limits(tmp_path, api):
    with pytest.raises(StockError, match="unexpected host"):
        download("https://evil.example.com/x.mp4", tmp_path / "x", opener=api)
    with pytest.raises(StockError, match="unexpected host"):
        download("http://videos.pexels.com/x.mp4", tmp_path / "x", opener=api)  # https only
    with pytest.raises(StockError, match="limit"):
        download("https://videos.pexels.com/video-files/123/hd.mp4", tmp_path / "x", opener=api, max_bytes=10)
    assert is_media_host("https://player.vimeo.com/external/1.hd.mp4")


def test_add_registers_with_licence_and_blocks_until_checklist(demo, api):
    p = PexelsProvider("k", opener=api)
    r = validate_project(demo)
    item = p.get("video", "123")
    added = add_stock_item(demo, r.manifest, r.registry, p, item, "s02-city", scenes=["s02-claim-ledger"],
                           target_width=1920, opener=api)
    assert added.chosen.width == 1920 and added.bytes_downloaded > 0
    r = validate_project(demo)
    assert r.ok, [str(i) for i in r.issues]
    a = next(x for x in r.registry.assets if x.asset_id == "s02-city")
    assert (a.type, a.creation_method, a.license_name, a.commercial_use) == ("video", "downloaded", "Pexels License", "allowed")
    assert a.source_url == VIDEO["url"] and a.creator == "Asha Rao" and a.raw_redistribution_allowed is False
    assert a.path == "assets/originals/s02-city.mp4" and a.publication_status == "pending_review"
    assert "identifiable_people is unknown" in a.approval_blockers()
    assert existing_for(r.registry, item) == "s02-city"

    with pytest.raises(StockError, match="already in this project"):
        add_stock_item(demo, r.manifest, r.registry, p, item, "s02-city-2", scenes=[], target_width=1920, opener=api)

    with pytest.raises(Exception, match="identifiable_people"):
        review_asset(demo, r.manifest, r.registry, r.approvals, "s02-city", decision=Decision.APPROVE, by="Asha")
    record_checklist(demo, r.manifest, r.registry, "s02-city", {"identifiable_people": False,
                                                               "trademarks_visible": False})
    r = validate_project(demo)
    asset, _ = review_asset(demo, r.manifest, r.registry, r.approvals, "s02-city", decision=Decision.APPROVE, by="Asha")
    assert asset.publication_status == "approved"


def test_dry_run_downloads_and_registers_nothing(demo, api):
    p = PexelsProvider("k", opener=api)
    r = validate_project(demo)
    before = (demo / "assets/registry.json").read_text()
    add_stock_item(demo, r.manifest, r.registry, p, p.get("photo", "77"), "s01-desk", scenes=[], target_width=1920,
                   dry_run=True, opener=api)
    assert (demo / "assets/registry.json").read_text() == before
    assert not any("images.pexels.com" in u for u, _ in api.requests)


def test_checklist_validation(demo):
    r = validate_project(demo)
    with pytest.raises(ChecklistError, match="unknown asset"):
        record_checklist(demo, r.manifest, r.registry, "nope", {"identifiable_people": False})
    with pytest.raises(ChecklistError, match="not checklist"):
        record_checklist(demo, r.manifest, r.registry, "s01-title", {"license_name": "x"})
    with pytest.raises(ChecklistError, match="at least one"):
        record_checklist(demo, r.manifest, r.registry, "s01-title", {})


def test_cli_checklist_and_search_without_key(runner_env, demo, monkeypatch):
    runner, app, cli = runner_env
    monkeypatch.delenv("PIPELINE_PEXELS_API_KEY", raising=False)
    r = runner.invoke(app, ["stock", "search", "city"])
    assert r.exit_code == cli.EXIT_FAILED and "PIPELINE_PEXELS_API_KEY" in r.output
    r = runner.invoke(app, ["assets", "checklist", str(demo), "s01-title", "--people", "maybe"])
    assert r.exit_code == cli.EXIT_FAILED and "yes or no" in r.output
    r = runner.invoke(app, ["assets", "checklist", str(demo), "s01-title", "--people", "no"])
    assert r.exit_code == cli.EXIT_OK and "Ready for" in r.output
