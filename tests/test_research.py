from datetime import date

import pytest

from reckoning_pipeline.research import (
    LedgerError, build_bibliography, build_report, import_records, parse_import, review_claim,
)
from reckoning_pipeline.research.assist import suggest_claims, write_suggestions
from reckoning_pipeline.schemas import ResearchLedger, SceneManifest
from reckoning_pipeline.schemas.research import ClaimOrigin, ClaimStatus


def ledger(claims=(), sources=()):
    return ResearchLedger.model_validate({"sources": list(sources), "claims": list(claims)})


def scenes(*claim_lists, source_lists=None):
    return SceneManifest.model_validate({"scenes": [
        {"scene_id": f"s{i}", "order": i, "purpose": "p", "narration_text": "words here",
         "claim_ids": list(cl), "source_ids": list((source_lists or {}).get(i, []))}
        for i, cl in enumerate(claim_lists, 1)
    ]})


def source(sid="src1", claims=("c1",), status="checked", **kw):
    return {"source_id": sid, "title": f"Title {sid}", "url": f"https://example.org/{sid}",
            "source_type": "report", "classification": "primary", "supported_claim_ids": list(claims),
            "verification_status": status, **kw}


def claim(cid="c1", importance="critical", status="unverified", sources=("src1",), **kw):
    data = {"claim_id": cid, "text": f"Claim {cid}", "claim_type": "factual", "importance": importance,
            "source_ids": list(sources), "verification_status": status, **kw}
    if status != "unverified":
        data.update(reviewer="Reviewer", review_date="2026-10-17")
    return data


def codes(report, severity=None):
    return [f.code for f in report.findings if severity is None or f.severity == severity]


# --- report ------------------------------------------------------------------

def test_critical_unreviewed_claim_in_use_blocks():
    r = build_report(ledger([claim()], [source()]), scenes(["c1"]))
    assert codes(r, "blocker") == ["claim.critical_unreviewed"]
    assert len(r.blockers) == 1


def test_unused_critical_claim_does_not_block():
    r = build_report(ledger([claim()], [source()]), scenes([]))
    assert not r.blockers
    assert "claim.unverified" in codes(r, "info")


def test_claim_without_sources():
    r = build_report(ledger([claim(sources=())]), scenes(["c1"]))
    assert "claim.no_sources" in codes(r, "blocker")
    r = build_report(ledger([claim(importance="supporting", sources=())]), scenes(["c1"]))
    assert "claim.no_sources" in codes(r, "warning")


def test_verified_claim_without_checked_supporting_source():
    r = build_report(ledger([claim(status="verified")], [source(status="unchecked")]), scenes(["c1"]))
    assert "claim.verified_unsupported" in codes(r, "warning")
    r = build_report(ledger([claim(status="verified")], [source()]), scenes(["c1"]))
    assert not r.findings or "claim.verified_unsupported" not in codes(r)
    assert not r.blockers


def test_disputed_and_partial_critical_claims_block():
    r = build_report(ledger([claim(status="disputed", counter_evidence=["x"])], [source()]), scenes(["c1"]))
    assert "claim.disputed" in codes(r, "blocker")
    r = build_report(ledger([claim(status="partially_verified")], [source()]), scenes(["c1"]))
    assert "claim.partially_verified" in codes(r, "blocker")


def test_rejected_claim_in_use_cannot_be_excepted():
    class Exc:
        by = "Editor"
    r = build_report(ledger([claim(status="rejected")], [source()]), scenes(["c1"]), {"c1": Exc()})
    blocker = next(f for f in r.findings if f.code == "claim.rejected_in_use")
    assert blocker.blocking and not blocker.exceptable


def test_exception_clears_exceptable_blocker():
    class Exc:
        by = "Editor"
    r = build_report(ledger([claim()], [source()]), scenes(["c1"]), {"c1": Exc()})
    assert not r.blockers
    assert next(f for f in r.findings if f.code == "claim.critical_unreviewed").excepted_by == "Editor"


def test_retracted_source_blocks_used_claim():
    r = build_report(ledger([claim(status="verified")], [source(status="retracted")]), scenes(["c1"]))
    assert "claim.cites_retracted" in codes(r, "blocker")


def test_quotation_needs_excerpt_with_locator():
    q = claim(importance="supporting", claim_type="quotation")
    r = build_report(ledger([q], [source()]), scenes(["c1"]))
    assert "quotation.no_excerpt" in codes(r, "blocker")
    with_excerpt = source(excerpts=[{"claim_id": "c1", "text": "the quote", "locator": "p. 12"}])
    r = build_report(ledger([q], [with_excerpt]), scenes(["c1"]))
    assert "quotation.no_excerpt" not in codes(r)


def test_causal_claims_need_non_correlational_basis():
    base = dict(importance="supporting", claim_type="causal")
    assert "causal.basis_missing" in codes(build_report(ledger([claim(**base)], [source()]), scenes(["c1"])))
    weak = claim(**base, evidence_basis=["observational", "anecdotal"])
    assert "causal.correlation_only" in codes(build_report(ledger([weak], [source()]), scenes(["c1"])))
    strong = claim(**base, evidence_basis=["observational", "experimental"])
    assert not {"causal.correlation_only", "causal.basis_missing"} & set(
        codes(build_report(ledger([strong], [source()]), scenes(["c1"]))))


def test_unused_source_and_scene_without_claims():
    r = build_report(ledger([], [source(claims=())]), scenes([]))
    assert "source.unused" in codes(r, "warning")
    assert "scene.no_claims" in codes(r, "info")


def test_report_json_shape():
    d = build_report(ledger([claim()], [source()]), scenes(["c1"])).to_dict()
    assert d["blocker_count"] == 1
    assert d["status_counts"]["unverified"] == 1
    assert d["findings"][0]["blocking"] is True


# --- bibliography ------------------------------------------------------------

def test_bibliography_order_and_skips():
    led = ledger(
        [claim("c1", sources=["b"]), claim("c2", sources=["a", "gone"] if False else ["a"])],
        [source("a", claims=["c2"]), source("b", claims=["c1"], citation_text="B, custom citation."),
         source("internal", claims=(), source_type="internal_document"),
         source("old", claims=(), status="retracted")],
    )
    sc = scenes(["c1"], ["c2"], source_lists={2: ["internal", "old"]})
    bib = build_bibliography(led, sc)
    assert bib.entries[0] == "B, custom citation."
    assert bib.entries[1].startswith("Title a")
    assert bib.skipped == {"internal": "internal document", "old": "retracted"}
    assert len(build_bibliography(led, sc, include_internal=True).entries) == 3
    assert bib.to_markdown("T").startswith("# Sources: T\n\n1. B, custom citation.")


# --- ledger edits ------------------------------------------------------------

def test_import_adds_and_refuses_collisions():
    base = ledger([claim()], [source()])
    incoming = parse_import('{"claims": [{"claim_id": "c2", "text": "New", "claim_type": "factual", '
                            '"importance": "contextual"}]}')
    updated, summary = import_records(base, incoming)
    assert summary.added == ["c2"] and len(updated.claims) == 2
    with pytest.raises(LedgerError, match="already exists"):
        import_records(updated, incoming)
    _, summary = import_records(updated, incoming, replace=True)
    assert summary.replaced == ["c2"]


def test_import_rejects_invalid_and_reviewed_ai_claims():
    with pytest.raises(LedgerError, match="invalid"):
        parse_import('{"claims": [{"claim_id": "BAD"}]}')
    incoming = parse_import(
        '{"claims": [{"claim_id": "c9", "text": "x", "claim_type": "factual", "importance": "critical", '
        '"origin": "llm_suggestion", "verification_status": "verified", "source_ids": ["src1"], '
        '"reviewer": "R", "review_date": "2026-10-17"}]}')
    with pytest.raises(LedgerError, match="AI suggestion"):
        import_records(ledger(), incoming)


def test_review_claim_records_reviewer_and_note():
    led = review_claim(ledger([claim()], [source()]), "c1", status=ClaimStatus.VERIFIED, by="Asha",
                       on=date(2026, 10, 18), note="Read p. 4")
    c = led.claims[0]
    assert (c.verification_status, c.reviewer, c.review_date) == ("verified", "Asha", date(2026, 10, 18))
    assert "2026-10-18 Asha: Read p. 4" in c.review_notes
    back = review_claim(led, "c1", status=ClaimStatus.UNVERIFIED, by="Asha", on=date(2026, 10, 19))
    assert back.claims[0].reviewer is None


def test_review_claim_enforces_schema_rules():
    with pytest.raises(LedgerError, match="source_id"):
        review_claim(ledger([claim(sources=())]), "c1", status=ClaimStatus.VERIFIED, by="A", on=date.today())
    with pytest.raises(LedgerError, match="unknown"):
        review_claim(ledger(), "nope", status=ClaimStatus.VERIFIED, by="A", on=date.today())


# --- LLM assist guardrails ---------------------------------------------------

class FakeProvider:
    name = "fake"
    sends_data_externally = False

    def __init__(self, reply):
        self.reply = reply

    def complete(self, prompt, *, system="", max_tokens=1024):
        return self.reply


def test_suggestions_are_forced_unverified_and_unsourced(tmp_path):
    reply = ('Sure! [{"text": "Boredom rose in 2010", "claim_type": "statistical", "importance": "critical", '
             '"verification_status": "verified"}, {"text": ""}, {"text": "Odd type", "claim_type": "weird"}]')
    claims = suggest_claims(FakeProvider(reply), "brief")
    assert len(claims) == 2
    assert all(c.verification_status == "unverified" and not c.source_ids and c.reviewer is None
               and c.origin is ClaimOrigin.LLM_SUGGESTION for c in claims)
    assert claims[1].claim_type == "factual"
    out = write_suggestions(tmp_path / "notes", claims, "fake")
    imported = parse_import(out.read_text())
    assert len(imported.claims) == 2


def test_suggestions_reject_non_json():
    from reckoning_pipeline.research.assist import SuggestionError
    with pytest.raises(SuggestionError):
        suggest_claims(FakeProvider("no json here"), "brief")
