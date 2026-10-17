import hashlib
import json
import os
import stat

import pytest
from conftest import edit_json
from pydantic import ValidationError

from reckoning_pipeline.approvals import asset_approval_state
from reckoning_pipeline.assets import (
    AssetReviewError, Decision, IntakeError, apply_intake, build_credits, build_rights_report,
    plan_derivative, plan_intake, review_asset,
)
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.schemas import Asset
from reckoning_pipeline.schemas.asset import AssetRoot

PHOTO = b"\xff\xd8 not really a jpeg, but bytes are bytes \xff\xd9"

# A fully documented CC BY photo with no people or trademarks.
COMPLETE_PHOTO = {
    "type": "image", "creation_method": "downloaded", "source_url": "https://example.org/photo",
    "provider": "Example Archive", "creator": "Jane Doe", "rights_holder": "Jane Doe",
    "license_name": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "commercial_use": "allowed", "attribution_required": True,
    "attribution_text": "Photo: Jane Doe / Example Archive, CC BY 4.0", "derivatives_allowed": True,
    "rights_evidence": "Licence shown on the archive page, checked 2026-10-17.",
    "identifiable_people": False, "trademarks_visible": False,
}


@pytest.fixture
def photo(tmp_path):
    f = tmp_path / "incoming" / "Photo.JPG"
    f.parent.mkdir()
    f.write_bytes(PHOTO)
    return f


def ingest(demo, source, **fields):
    result = validate_project(demo)
    plan = plan_intake(demo, result.registry, source, {"asset_id": "s02-photo", **fields})
    apply_intake(demo, result.manifest, result.registry, plan)
    return plan


# --- schema: rights checklist ------------------------------------------------

def _asset(**kw):
    base = {"asset_id": "a1", "path": "assets/originals/a1.jpg", "sha256": "a" * 64, **COMPLETE_PHOTO,
            "review_status": "approved", "publication_status": "approved"}
    return Asset(**{**base, **kw})


def test_complete_external_photo_is_approvable():
    assert _asset().publication_status == "approved"


@pytest.mark.parametrize("override,reason", [
    ({"derivatives_allowed": None}, "derivatives_allowed"),
    ({"identifiable_people": None}, "identifiable_people"),
    ({"identifiable_people": True}, "people_clearance"),
    ({"trademarks_visible": None}, "trademarks_visible"),
    ({"trademarks_visible": True}, "trademark_notes"),
    ({"license_url": ""}, "license_url"),
])
def test_checklist_gaps_block_approval(override, reason):
    with pytest.raises(ValidationError, match=reason):
        _asset(**override)


def test_cleared_people_and_trademarks_are_fine():
    a = _asset(identifiable_people=True, people_clearance="Model release on file (2026-10-01)",
               trademarks_visible=True, trademark_notes="Incidental storefront; no endorsement implied")
    assert a.publication_status == "approved"


def test_music_needs_platform_clearance():
    music = {**COMPLETE_PHOTO, "type": "music"}
    with pytest.raises(ValidationError, match="platform_cleared"):
        _asset(**music)
    assert _asset(**music, platform_cleared=True).publication_status == "approved"


def test_generated_needs_terms_url():
    gen = {"creation_method": "generated", "source_url": None, "license_name": "",
           "generation": {"provider": "local", "model": "m"}}
    with pytest.raises(ValidationError, match="terms_url"):
        _asset(**gen)
    gen["generation"]["terms_url"] = "https://example.org/terms"
    assert _asset(**gen).publication_status == "approved"


# --- intake ------------------------------------------------------------------

def test_intake_copies_verifies_and_preserves_original(demo, photo):
    before = (photo.read_bytes(), photo.stat().st_mtime)
    plan = ingest(demo, photo, type="image", creation_method="user_supplied")
    stored = demo / "assets/originals/s02-photo.jpg"
    assert plan.asset.path == "assets/originals/s02-photo.jpg"
    assert stored.read_bytes() == PHOTO
    assert plan.asset.sha256 == hashlib.sha256(PHOTO).hexdigest()
    assert (photo.read_bytes(), photo.stat().st_mtime) == before  # source untouched
    assert not os.stat(stored).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)  # read-only
    result = validate_project(demo)
    assert result.ok
    added = next(a for a in result.registry.assets if a.asset_id == "s02-photo")
    assert (added.review_status, added.publication_status) == ("pending", "pending_review")


def test_intake_never_approves_and_blocks_non_commercial(demo, photo):
    with pytest.raises(IntakeError, match="publication_status"):
        plan_intake(demo, validate_project(demo).registry, photo,
                    {"asset_id": "x", "type": "image", "creation_method": "user_supplied",
                     "publication_status": "approved"})
    plan = ingest(demo, photo, type="image", creation_method="user_supplied", commercial_use="not_allowed")
    assert plan.asset.publication_status == "blocked"


def test_intake_refusals(demo, photo, tmp_path):
    registry = validate_project(demo).registry
    with pytest.raises(IntakeError, match="already exists"):
        plan_intake(demo, registry, photo, {"asset_id": "s01-title", "type": "image",
                                            "creation_method": "user_supplied"})
    with pytest.raises(IntakeError, match="not a file"):
        plan_intake(demo, registry, tmp_path / "missing.jpg", {"asset_id": "x"})
    with pytest.raises(IntakeError, match="source_url"):
        plan_intake(demo, registry, photo, {"asset_id": "x", "type": "image", "creation_method": "downloaded"})
    ingest(demo, photo, type="image", creation_method="user_supplied")
    # Same destination path, different record: never overwrite a stored original.
    registry = validate_project(demo).registry
    registry.assets.pop()
    with pytest.raises(IntakeError, match="not overwriting"):
        plan_intake(demo, registry, photo, {"asset_id": "s02-photo", "type": "image",
                                            "creation_method": "user_supplied"})


def test_plan_intake_writes_nothing(demo, photo):
    registry_before = (demo / "assets/registry.json").read_text()
    plan_intake(demo, validate_project(demo).registry, photo,
                {"asset_id": "dry", "type": "image", "creation_method": "user_supplied"})
    assert not (demo / "assets/originals").exists()
    assert (demo / "assets/registry.json").read_text() == registry_before


def test_intake_to_media_root(demo, photo, tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    result = validate_project(demo)
    with pytest.raises(IntakeError, match="PIPELINE_MEDIA_ROOT"):
        plan_intake(demo, result.registry, photo, {"asset_id": "m1", "type": "image",
                                                   "creation_method": "user_supplied"}, root=AssetRoot.MEDIA)
    plan = plan_intake(demo, result.registry, photo, {"asset_id": "m1", "type": "image",
                                                      "creation_method": "user_supplied"},
                       root=AssetRoot.MEDIA, media_root=media)
    apply_intake(demo, result.manifest, result.registry, plan)
    assert (media / "assets/originals/m1.jpg").is_file()
    assert validate_project(demo, media_root=media).ok


def test_intake_refuses_when_disk_margin_too_small(demo, photo):
    result = validate_project(demo)
    plan = plan_intake(demo, result.registry, photo, {"asset_id": "big", "type": "image",
                                                      "creation_method": "user_supplied"})
    with pytest.raises(IntakeError, match="disk space"):
        apply_intake(demo, result.manifest, result.registry, plan, min_free_gb=10**9)
    assert not (demo / "assets/originals/big.jpg").exists()


# --- derivatives -------------------------------------------------------------

def test_derivative_inherits_rights_and_lives_apart(demo, photo, tmp_path):
    ingest(demo, photo, **COMPLETE_PHOTO)
    crop = tmp_path / "crop.jpg"
    crop.write_bytes(PHOTO + b"cropped")
    result = validate_project(demo)
    plan = plan_derivative(demo, result.registry, "s02-photo", crop, "s02-photo-crop", notes="16:9 crop")
    apply_intake(demo, result.manifest, result.registry, plan)
    d = plan.asset
    assert d.path == "assets/derived/s02-photo-crop.jpg"
    assert (d.derived_from, d.license_name, d.attribution_text) == (
        "s02-photo", "CC BY 4.0", COMPLETE_PHOTO["attribution_text"])
    assert d.publication_status == "pending_review"
    assert (demo / "assets/originals/s02-photo.jpg").read_bytes() == PHOTO
    assert validate_project(demo).ok


def test_derivative_refused_when_not_allowed(demo, photo, tmp_path):
    ingest(demo, photo, **{**COMPLETE_PHOTO, "derivatives_allowed": False})
    with pytest.raises(IntakeError, match="does not allow derivatives"):
        plan_derivative(demo, validate_project(demo).registry, "s02-photo", photo, "crop")


def test_validate_flags_derivative_of_no_derivatives_parent(demo, photo, tmp_path):
    ingest(demo, photo, **COMPLETE_PHOTO)
    crop = tmp_path / "crop.jpg"
    crop.write_bytes(b"crop")
    result = validate_project(demo)
    apply_intake(demo, result.manifest, result.registry,
                 plan_derivative(demo, result.registry, "s02-photo", crop, "crop"))
    edit_json(demo / "assets/registry.json",
              lambda d: next(a for a in d["assets"] if a["asset_id"] == "s02-photo").update(
                  derivatives_allowed=False))
    assert "asset.derivative_not_allowed" in [i.code for i in validate_project(demo).errors]


# --- review, staleness, report, credits --------------------------------------

def test_review_refuses_incomplete_rights(demo, photo):
    ingest(demo, photo, type="image", creation_method="user_supplied")
    result = validate_project(demo)
    with pytest.raises(AssetReviewError, match="commercial_use"):
        review_asset(demo, result.manifest, result.registry, result.approvals, "s02-photo",
                     decision=Decision.APPROVE, by="Asha")


def test_approve_records_event_and_goes_stale_on_edit(demo, photo):
    ingest(demo, photo, **COMPLETE_PHOTO)
    result = validate_project(demo)
    asset, event = review_asset(demo, result.manifest, result.registry, result.approvals, "s02-photo",
                                decision=Decision.APPROVE, by="Asha", note="checked licence page")
    assert asset.publication_status == "approved" and event.kind == "asset_approved"
    result = validate_project(demo)
    assert result.ok
    assert asset_approval_state(result.approvals, asset) == "approved"

    edit_json(demo / "assets/registry.json",
              lambda d: next(a for a in d["assets"] if a["asset_id"] == "s02-photo").update(
                  attribution_text="Photo: someone else"))
    result = validate_project(demo)
    a = next(x for x in result.registry.assets if x.asset_id == "s02-photo")
    assert asset_approval_state(result.approvals, a) == "stale"
    codes = [f.code for f in build_rights_report(result.registry, result.scenes, result.approvals).findings]
    assert "asset.approval_stale" in codes


def test_block_requires_reason(demo):
    result = validate_project(demo)
    with pytest.raises(AssetReviewError, match="reason"):
        review_asset(demo, result.manifest, result.registry, result.approvals, "s01-title",
                     decision=Decision.BLOCK, by="Asha")
    asset, _ = review_asset(demo, result.manifest, result.registry, result.approvals, "s01-title",
                            decision=Decision.BLOCK, by="Asha", note="Replacing with a new title card")
    assert asset.publication_status == "blocked"
    result = validate_project(demo)
    codes = [f.code for f in build_rights_report(result.registry, result.scenes, result.approvals).blockers]
    assert "asset.blocked_in_use" in codes


def test_manually_approved_without_review_is_flagged(demo):
    def approve_by_hand(d):
        d["assets"][0].update(review_status="approved", publication_status="approved")
    edit_json(demo / "assets/registry.json", approve_by_hand)
    result = validate_project(demo)
    codes = [f.code for f in build_rights_report(result.registry, result.scenes, result.approvals).blockers]
    assert "asset.approval_unrecorded" in codes


def test_rights_report_groups_and_demo_blockers(demo):
    result = validate_project(demo)
    report = build_rights_report(result.registry, result.scenes, result.approvals)
    assert len(report.groups["pending_review"]) == 4
    assert len(report.blockers) == 4
    assert report.to_dict()["blocker_count"] == 4


def test_publication_ready_requires_approved_assets(demo):
    from datetime import date

    from reckoning_pipeline.research import review_claim, save_ledger
    from reckoning_pipeline.schemas.research import ClaimStatus
    from reckoning_pipeline.script import approve_script

    result = validate_project(demo)
    led = result.ledger
    for c in led.claims:
        led = review_claim(led, c.claim_id, status=ClaimStatus.VERIFIED, by="Test", on=date(2026, 10, 17))
    save_ledger(demo, result.manifest, led)
    result = validate_project(demo)
    approve_script(result, result.approvals, by="Test")
    edit_json(demo / "project.json", lambda d: d.update(project_status="publication_ready"))
    errors = validate_project(demo).errors
    assert {i.code for i in errors} == {"project.publication_blocked"}
    assert len(errors) == 4  # one per unapproved demo graphic

    edit_json(demo / "project.json", lambda d: d.update(project_status="script_approved"))
    for aid in ("s01-title", "s02-claim-ledger", "s03-asset-record", "s04-review-gates"):
        result = validate_project(demo)
        review_asset(demo, result.manifest, result.registry, result.approvals, aid,
                     decision=Decision.APPROVE, by="Test")
    edit_json(demo / "project.json", lambda d: d.update(project_status="publication_ready"))
    assert validate_project(demo).ok


def test_credits_use_exact_attribution_once(demo, photo, tmp_path):
    ingest(demo, photo, **COMPLETE_PHOTO)
    edit_json(demo / "scenes.json", lambda d: (d["scenes"][1]["asset_ids"].append("s02-photo"),
                                               d["scenes"][2]["asset_ids"].append("s02-photo")))
    result = validate_project(demo)
    credits = build_credits(result.registry, result.scenes)
    assert credits.attributions == [COMPLETE_PHOTO["attribution_text"]]
    assert credits.licensed == ["s02-photo: Jane Doe, CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)"]
    md = credits.to_markdown("T")
    assert "## Attribution" in md and COMPLETE_PHOTO["attribution_text"] in md
