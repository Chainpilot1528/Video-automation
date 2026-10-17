from datetime import date

import pytest
from conftest import edit_json
from pydantic import ValidationError

from reckoning_pipeline.assets import Decision, review_asset
from reckoning_pipeline.approvals import (
    active_exceptions, append_event, check_reviewer, claim_fingerprint, load_log, script_approval_state,
    script_fingerprint,
)
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.research import review_claim, save_ledger
from reckoning_pipeline.schemas import ApprovalEvent
from reckoning_pipeline.schemas.approval import ApprovalKind
from reckoning_pipeline.schemas.research import ClaimStatus
from reckoning_pipeline.script import ScriptError, approve_script, check_script, revoke_script_approval


def verify_all(demo):
    """Simulate a human reviewer verifying the demo claims (test only)."""
    result = validate_project(demo)
    led = result.ledger
    for c in led.claims:
        led = review_claim(led, c.claim_id, status=ClaimStatus.VERIFIED, by="Test Reviewer",
                           on=date(2026, 10, 17))
    save_ledger(demo, result.manifest, led)
    return validate_project(demo)


def approve_demo_assets(demo):
    for aid in ("s01-title", "s02-claim-ledger", "s03-asset-record", "s04-review-gates"):
        result = validate_project(demo)
        review_asset(demo, result.manifest, result.registry, result.approvals, aid,
                     decision=Decision.APPROVE, by="Test Reviewer")


def test_event_rules():
    base = dict(event_id="evt-0001", by="A", at="2026-10-17T12:00:00+00:00")
    with pytest.raises(ValidationError, match="fingerprint"):
        ApprovalEvent(kind="script_approved", **base)
    with pytest.raises(ValidationError, match="claim_id"):
        ApprovalEvent(kind="claim_exception", fingerprint="a" * 64, rationale="x" * 30, **base)
    with pytest.raises(ValidationError, match="rationale"):
        ApprovalEvent(kind="claim_exception", fingerprint="a" * 64, claim_id="c1", rationale="short", **base)
    with pytest.raises(ValidationError, match="must not"):
        ApprovalEvent(kind="script_approval_revoked", claim_id="c1", **base)


def test_check_reviewer():
    with pytest.raises(ValueError, match="required"):
        check_reviewer("  ", [])
    with pytest.raises(ValueError, match="AUTHORIZED"):
        check_reviewer("Mallory", ["Asha", "Nikhil"])
    check_reviewer("Asha", ["Asha"])
    check_reviewer("Anyone", [])


def test_demo_script_blocked_until_claims_reviewed(demo):
    result = validate_project(demo)
    check = check_script(result, result.approvals)
    assert [f.code for f in check.blockers] == ["claim.critical_unreviewed"]
    with pytest.raises(ScriptError, match="blocker"):
        approve_script(result, result.approvals, by="Asha")


def test_approve_then_edit_makes_approval_stale(demo):
    result = verify_all(demo)
    event = approve_script(result, result.approvals, by="Asha", note="Looks right")
    assert event.kind is ApprovalKind.SCRIPT_APPROVED
    result = validate_project(demo)
    assert result.ok and result.manifest.project_status == "script_approved"
    assert check_script(result, result.approvals).approval.status == "approved"
    with pytest.raises(ScriptError, match="already"):
        approve_script(result, result.approvals, by="Asha")

    edit_json(demo / "scenes.json", lambda d: d["scenes"][1].update(narration_text="Changed wording."))
    result = validate_project(demo)
    assert check_script(result, result.approvals).approval.status == "stale"
    assert "project.status_requires_approval" in [i.code for i in result.errors]


def test_changing_a_used_claim_makes_approval_stale(demo):
    result = verify_all(demo)
    approve_script(result, result.approvals, by="Asha")
    edit_json(demo / "research/ledger.json", lambda d: d["claims"][0].update(text="Reworded claim."))
    result = validate_project(demo)
    assert script_approval_state(result.approvals, script_fingerprint(result.scenes, result.ledger)).status == "stale"


def test_revoke_returns_status_to_research(demo):
    result = verify_all(demo)
    approve_script(result, result.approvals, by="Asha")
    result = validate_project(demo)
    with pytest.raises(ScriptError, match="reason"):
        revoke_script_approval(result, result.approvals, by="Asha", reason=" ")
    revoke_script_approval(result, result.approvals, by="Asha", reason="New evidence came in")
    result = validate_project(demo)
    assert result.ok and result.manifest.project_status == "in_research"
    assert check_script(result, result.approvals).approval.status == "revoked"
    with pytest.raises(ScriptError, match="no script approval"):
        revoke_script_approval(result, result.approvals, by="Asha", reason="again")


def test_authorized_reviewers_enforced(demo):
    result = verify_all(demo)
    with pytest.raises(ValueError, match="AUTHORIZED"):
        approve_script(result, result.approvals, by="Mallory", authorized=["Asha"])


def test_exception_unblocks_and_expires_when_claim_changes(demo):
    result = validate_project(demo)
    claim = next(c for c in result.ledger.claims if c.claim_id == "claim-review-required")
    append_event(demo, result.manifest, result.approvals, kind=ApprovalKind.CLAIM_EXCEPTION, by="Editor",
                 rationale="Demo only; internal claim checked by reading the code.",
                 fingerprint=claim_fingerprint(claim), claim_id=claim.claim_id)
    result = validate_project(demo)
    assert "claim-review-required" in active_exceptions(result.approvals, result.ledger)
    assert not check_script(result, result.approvals).blockers

    edit_json(demo / "research/ledger.json", lambda d: d["claims"][0].update(text="Different claim."))
    result = validate_project(demo)
    assert not active_exceptions(result.approvals, result.ledger)


def test_approval_required_statuses_and_publication_gate(demo):
    edit_json(demo / "project.json", lambda d: d.update(project_status="in_production"))
    assert "project.status_requires_approval" in [i.code for i in validate_project(demo).errors]

    edit_json(demo / "project.json", lambda d: d.update(project_status="draft"))
    result = verify_all(demo)
    approve_script(result, result.approvals, by="Asha")
    approve_demo_assets(demo)
    edit_json(demo / "project.json", lambda d: d.update(project_status="publication_ready"))
    assert validate_project(demo).ok


def test_publication_ready_blocked_by_research_blockers(demo):
    # Approve via an exception, then revoke the exception: approval stays current, but the blocker returns.
    result = validate_project(demo)
    claim = result.ledger.claims[0]
    append_event(demo, result.manifest, result.approvals, kind=ApprovalKind.CLAIM_EXCEPTION, by="Editor",
                 rationale="Temporary exception for the purposes of this test.",
                 fingerprint=claim_fingerprint(claim), claim_id=claim.claim_id)
    result = validate_project(demo)
    approve_script(result, result.approvals, by="Asha")
    result = validate_project(demo)
    append_event(demo, result.manifest, result.approvals, kind=ApprovalKind.CLAIM_EXCEPTION_REVOKED,
                 by="Editor", claim_id=claim.claim_id)
    approve_demo_assets(demo)
    edit_json(demo / "project.json", lambda d: d.update(project_status="publication_ready"))
    errors = validate_project(demo).errors
    assert [i.code for i in errors] == ["project.publication_blocked"]
    assert "claim.critical_unreviewed" in errors[0].message


def test_approval_log_integrity(demo):
    result = validate_project(demo)
    log = load_log(demo, result.manifest)
    assert log.events == []
    (demo / "approvals.json").write_text(
        '{"schema_version": "1.0", "events": ['
        '{"event_id": "evt-0002", "kind": "script_approval_revoked", "by": "A", "at": "2026-10-17T12:00:00+00:00"},'
        '{"event_id": "evt-0002", "kind": "script_approval_revoked", "by": "A", "at": "2026-10-16T12:00:00+00:00"},'
        '{"event_id": "evt-0003", "kind": "claim_exception_revoked", "by": "A", "at": "2026-10-18T12:00:00+00:00",'
        ' "claim_id": "ghost"}]}')
    result = validate_project(demo)
    found = [i.code for i in result.issues]
    assert "id.duplicate" in found and "approvals.out_of_order" in found
    assert "approvals.unknown_claim" in found
