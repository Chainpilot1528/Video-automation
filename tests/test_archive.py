"""Museum (public-domain) image providers and intake, against fake APIs (no network)."""

import io
import json
import urllib.error

import pytest
from test_stock import FakeResponse

from reckoning_pipeline.assets.stock import add_stock_item, download
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.providers.stock import AICProvider, MetProvider, StockError, parse_ref
from reckoning_pipeline.providers.stock.museums import aic_item, met_item

MET_API = "https://collectionapi.metmuseum.org/public/collection"
EPICURUS = {"objectID": 248475, "isPublicDomain": True, "title": "Marble head of Epikouros",
            "artistDisplayName": "", "culture": "Roman", "objectDate": "2nd century CE",
            "primaryImage": "https://images.metmuseum.org/CRDImages/gr/original/DP-1.jpg",
            "primaryImageSmall": "https://images.metmuseum.org/CRDImages/gr/web-large/DP-1.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/248475", "medium": "Marble",
            "creditLine": "Rogers Fund, 1911"}
NOT_PD = {**EPICURUS, "objectID": 2, "isPublicDomain": False}
NO_IMAGE = {**EPICURUS, "objectID": 3, "primaryImage": ""}
AIC = {"id": 28560, "title": "The Bedroom", "artist_title": "Vincent van Gogh", "date_display": "1889",
       "image_id": "25c31d8d-21a4-9ea1-1d73-6a2eca4dda7e", "is_public_domain": True,
       "thumbnail": {"width": 1000, "height": 800}, "credit_line": "Helen Birch Bartlett Memorial Collection"}


class FakeMuseums:
    """Answers like the Met and AIC APIs; ``drop`` makes the first N requests fail at the network level."""

    def __init__(self, drop: int = 0):
        self.requests = []
        self.drop = drop

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.requests.append((url, dict(req.header_items())))
        if self.drop:
            self.drop -= 1
            raise urllib.error.URLError("connection closed")
        if url.startswith(f"{MET_API}/v1.1/search"):
            return FakeResponse(json.dumps({"total": 4, "objectIDs": [404, 2, 3, 248475]}).encode())
        if url == f"{MET_API}/v1/objects/404":
            raise urllib.error.HTTPError(url, 404, "nf", {}, io.BytesIO(b"{}"))
        objects = {2: NOT_PD, 3: NO_IMAGE, 248475: EPICURUS}
        for oid, obj in objects.items():
            if url == f"{MET_API}/v1/objects/{oid}":
                return FakeResponse(json.dumps(obj).encode())
        if url.startswith("https://api.artic.edu/api/v1/artworks/search"):
            return FakeResponse(json.dumps({"data": [AIC, {**AIC, "id": 9, "is_public_domain": False}],
                                            "config": {"iiif_url": "https://www.artic.edu/iiif/2"}}).encode())
        if url.startswith("https://images.metmuseum.org/"):
            return FakeResponse(b"\xff\xd8\xff fake jpeg bytes", {"Content-Length": "20"})
        raise AssertionError(f"unexpected request {url}")


def met(opener):
    return MetProvider(opener=opener, sleep=lambda s: None)


def test_met_item_only_public_domain_with_image():
    assert met_item(NOT_PD) is None and met_item(NO_IMAGE) is None
    item = met_item(EPICURUS)
    assert item.ref == "met:photo:248475" and item.creator == "Roman"  # culture when no named artist
    assert item.extra["title"] == "Marble head of Epikouros" and item.extra["museum"].startswith("The Metropolitan")
    assert item.files[0].url.endswith("original/DP-1.jpg") and item.description.startswith("Marble head")


def test_aic_item_builds_iiif_url():
    item = aic_item(AIC, "https://www.artic.edu/iiif/2/")
    assert item.files[0].url == "https://www.artic.edu/iiif/2/25c31d8d-21a4-9ea1-1d73-6a2eca4dda7e/full/1686,/0/default.jpg"
    assert (item.width, item.height) == (1686, 1349) and item.page_url == "https://www.artic.edu/artworks/28560"
    assert aic_item({**AIC, "is_public_domain": False}, "x") is None


def test_met_search_skips_missing_and_non_public_domain():
    api = FakeMuseums()
    items = met(api).search("epicurus", "photo", per_page=5)
    assert [i.item_id for i in items] == ["248475"]
    search_url = api.requests[0][0]
    assert "/v1.1/search" in search_url and "isPublicDomain=true" in search_url and "hasImages=true" in search_url
    assert all("api" not in h.get("Authorization", "") for _, h in api.requests)  # no key, no secrets


def test_met_retries_dropped_connections_and_refuses_videos():
    assert met(FakeMuseums(drop=2)).get("photo", "248475").item_id == "248475"
    with pytest.raises(StockError, match="can't reach"):
        met(FakeMuseums(drop=3)).get("photo", "248475")
    with pytest.raises(StockError, match="still images only"):
        met(FakeMuseums()).search("x", "video")
    with pytest.raises(StockError, match="isn't public domain"):
        met(FakeMuseums()).get("photo", "2")


def test_aic_search_filters_and_sends_its_user_agent():
    api = FakeMuseums()
    items = AICProvider(opener=api, sleep=lambda s: None).search("bedroom", "photo")
    assert [i.item_id for i in items] == ["28560"]
    url, headers = api.requests[0]
    assert "is_public_domain" in url and "Aic-user-agent" in headers


def test_download_only_from_the_museum_image_host(tmp_path):
    with pytest.raises(StockError, match="unexpected host"):
        download("https://example.com/x.jpg", tmp_path / "x.jpg", opener=FakeMuseums(), hosts=MetProvider.media_hosts)
    assert download(EPICURUS["primaryImage"], tmp_path / "ok.jpg", opener=FakeMuseums(),
                    hosts=MetProvider.media_hosts) == len(b"\xff\xd8\xff fake jpeg bytes")


def test_add_registers_cc0_artwork_with_label_metadata(demo):
    api = FakeMuseums()
    provider = met(api)
    item = provider.get("photo", "248475")
    result = validate_project(demo)
    add_stock_item(demo, result.manifest, result.registry, provider, item, "met-epicurus", scenes=["s01-cold-open"],
                   target_width=10_000, opener=api)
    a = next(x for x in validate_project(demo).registry.assets if x.asset_id == "met-epicurus")
    assert (a.type, a.license_name, a.commercial_use, a.attribution_required) == (
        "image", "CC0 1.0 (public domain)", "allowed", False)
    assert a.provider == "The Metropolitan Museum of Art" and a.raw_redistribution_allowed
    assert "object 248475" in a.rights_evidence and "Marble head of Epikouros" in a.notes
    assert a.publication_status == "pending_review"  # a person still reviews it


def test_parse_ref_defaults_to_photo_for_archive():
    assert parse_ref("met:248475", default_kind="photo") == ("met", "photo", "248475")


def test_cli_archive_rejects_non_museum_sources(runner_env, demo):
    runner, app, cli = runner_env
    r = runner.invoke(app, ["archive", "search", "bust", "--source", "pexels"])
    assert r.exit_code == cli.EXIT_FAILED and "--source must be one of" in r.output
    r = runner.invoke(app, ["archive", "add", str(demo), "pexels:1", "--id", "x"])
    assert r.exit_code == cli.EXIT_FAILED and "isn't a museum source" in r.output
