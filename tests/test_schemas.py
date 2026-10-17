from datetime import datetime

import pytest
from pydantic import ValidationError

from reckoning_pipeline.schemas import Asset, Claim, ProjectManifest, Scene, Source
from reckoning_pipeline.schemas.common import SCHEMA_VERSION
from reckoning_pipeline.schemas.scene import Transition

SHA = "a" * 64


def asset(**overrides):
    base = dict(asset_id="a1", path="assets/a.svg", type="graphic", creation_method="original_graphic",
                sha256=SHA)
    return Asset(**{**base, **overrides})


APPROVABLE = dict(review_status="approved", commercial_use="allowed", attribution_required=False,
                  rights_evidence="made in-house", rights_holder="Reckoning Self")


# --- project -----------------------------------------------------------------

def test_project_defaults():
    m = ProjectManifest(project_id="demo", title="Demo")
    assert m.schema_version == SCHEMA_VERSION
    assert m.resolution.width == 1920 and m.audio_sample_rate == 48000


@pytest.mark.parametrize("field,value", [
    ("project_id", "Bad_Slug"), ("project_id", "x" * 65), ("frame_rate", 31), ("audio_sample_rate", 22050),
    ("resolution", {"width": 1921, "height": 1080}), ("target_platforms", ["youtube", "youtube"]),
    ("language", "english"), ("created_at", "2026-10-17T12:00:00"), ("unknown_field", 1),
])
def test_project_rejects(field, value):
    with pytest.raises(ValidationError):
        ProjectManifest(**{"project_id": "demo", "title": "Demo", field: value})


def test_project_updated_before_created_rejected():
    with pytest.raises(ValidationError, match="updated_at"):
        ProjectManifest(project_id="demo", title="Demo",
                        created_at=datetime.fromisoformat("2026-10-17T12:00:00+00:00"),
                        updated_at=datetime.fromisoformat("2026-10-16T12:00:00+00:00"))


@pytest.mark.parametrize("path", ["/etc/passwd", "../x.json", "a/../../x", "~/x", "a\\b", ""])
def test_unsafe_relative_paths_rejected(path):
    with pytest.raises(ValidationError):
        ProjectManifest(project_id="demo", title="Demo", paths={"scenes": path})


# --- scenes ------------------------------------------------------------------

def test_actual_duration_requires_narration_asset():
    with pytest.raises(ValidationError, match="measured"):
        Scene(scene_id="s1", order=1, purpose="p", actual_narration_duration_seconds=4.2)


def test_final_duration_requires_measurement_when_narrated():
    with pytest.raises(ValidationError, match="measure"):
        Scene(scene_id="s1", order=1, purpose="p", narration_asset_id="n1", final_duration_seconds=5)


def test_silent_scene_may_have_final_duration():
    assert Scene(scene_id="s1", order=1, purpose="p", final_duration_seconds=3).final_duration_seconds == 3


def test_captions_require_narration():
    with pytest.raises(ValidationError, match="captions"):
        Scene(scene_id="s1", order=1, purpose="p", caption_status="approximate")


@pytest.mark.parametrize("kwargs", [{"type": "cut", "duration_seconds": 1}, {"type": "fade"}])
def test_transition_rules(kwargs):
    with pytest.raises(ValidationError):
        Transition(**kwargs)


@pytest.mark.parametrize("kwargs", [
    {"scene_id": "S1"}, {"order": 0}, {"purpose": "  "}, {"asset_ids": ["a", "a"]},
    {"planned_duration_seconds": 0}, {"input_fingerprint": "abc"},
])
def test_scene_rejects(kwargs):
    with pytest.raises(ValidationError):
        Scene(**{"scene_id": "s1", "order": 1, "purpose": "p", **kwargs})


# --- research ----------------------------------------------------------------

def src(**overrides):
    base = dict(source_id="src1", title="T", url="https://example.org", source_type="report",
                classification="primary")
    return Source(**{**base, **overrides})


def test_source_needs_a_locator():
    with pytest.raises(ValidationError, match="at least one"):
        src(url=None)


def test_source_url_scheme():
    with pytest.raises(ValidationError, match="https"):
        src(url="ftp://example.org")


def test_excerpt_must_match_supported_claims():
    with pytest.raises(ValidationError, match="excerpts"):
        src(excerpts=[{"claim_id": "c1", "text": "quote"}])


def claim(**overrides):
    base = dict(claim_id="c1", text="X", claim_type="factual", importance="critical")
    return Claim(**{**base, **overrides})


def test_unverified_claim_needs_nothing():
    assert claim().verification_status == "unverified"


@pytest.mark.parametrize("status", ["verified", "partially_verified", "disputed", "rejected"])
def test_reviewed_status_requires_reviewer(status):
    with pytest.raises(ValidationError, match="reviewer"):
        claim(verification_status=status, source_ids=["s"], counter_evidence=["x"])


def test_verified_requires_source():
    with pytest.raises(ValidationError, match="source_id"):
        claim(verification_status="verified", reviewer="R", review_date="2026-10-17")


def test_disputed_requires_counter_evidence():
    with pytest.raises(ValidationError, match="counter_evidence"):
        claim(verification_status="disputed", reviewer="R", review_date="2026-10-17")


def test_verified_with_review_and_source_ok():
    c = claim(verification_status="verified", reviewer="R", review_date="2026-10-17", source_ids=["s"])
    assert c.verification_status == "verified"


# --- assets ------------------------------------------------------------------

def test_unknown_rights_cannot_be_approved():
    with pytest.raises(ValidationError, match="not allowed"):
        asset(publication_status="approved")


def test_complete_original_asset_can_be_approved():
    assert asset(publication_status="approved", **APPROVABLE).publication_status == "approved"


@pytest.mark.parametrize("override,reason", [
    ({"commercial_use": "unknown"}, "commercial_use"),
    ({"attribution_required": None}, "attribution_required is unknown"),
    ({"attribution_required": True}, "attribution_text"),
    ({"rights_evidence": ""}, "rights_evidence"),
    ({"review_status": "pending"}, "review_status"),
])
def test_each_rights_gap_blocks_approval(override, reason):
    with pytest.raises(ValidationError, match=reason):
        asset(publication_status="approved", **{**APPROVABLE, **override})


def test_downloaded_needs_url_and_license_for_approval():
    with pytest.raises(ValidationError, match="source_url"):
        asset(creation_method="downloaded")
    with pytest.raises(ValidationError, match="license_name"):
        asset(creation_method="downloaded", source_url="https://x.org/a", publication_status="approved",
              **APPROVABLE)


def test_generated_assets_record_generation():
    with pytest.raises(ValidationError, match="generation"):
        asset(creation_method="generated")
    a = asset(creation_method="generated", generation={"provider": "local", "model": "m"})
    assert a.generation.model == "m"
    with pytest.raises(ValidationError, match="only allowed"):
        asset(generation={"provider": "local", "model": "m"})


def test_bad_checksum_and_self_derivation():
    with pytest.raises(ValidationError):
        asset(sha256="xyz")
    with pytest.raises(ValidationError, match="itself"):
        asset(derived_from="a1")
