import json

import pytest
from conftest import edit_json
from test_approvals import verify_all
from test_narration import HAVE_FFMPEG, import_take, tools, words_seconds  # noqa: F401
from test_render import SCENES, tiny_profiles  # noqa: F401  (autouse fixture: small, fast renders)

from reckoning_pipeline.assets.review import Decision, review_asset
from reckoning_pipeline.narration import BuildOptions, build_narration
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.project.validate import extra_used_ids
from reckoning_pipeline.qa import (
    QAError, load_report, revoke_signoff, run_qa, sign_off, to_markdown, waive_warning, write_report,
)
from reckoning_pipeline.qa import checks as checks_mod
from reckoning_pipeline.qa.media import parse_analysis
from reckoning_pipeline.render import render
from reckoning_pipeline.schemas.qa import QAMeasurements
from reckoning_pipeline.script import approve_script

pytestmark = pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
MASTER = "master_16x9"


@pytest.fixture(autouse=True)
def tiny_qa_profiles(monkeypatch):
    """QA compares the render against the profile, so it must see the same tiny profile the renderer used."""
    from reckoning_pipeline.render import runner
    monkeypatch.setattr(checks_mod, "get_profile", runner.get_profile)


def quiet(tools, path, duration):
    """Analyser stand-in: a clean measurement, so tests control exactly what media checks see."""
    return QAMeasurements(duration_seconds=duration, integrated_lufs=-20.0, true_peak_dbtp=-3.0,
                          loudness_range_lu=4.0)


def ready_demo(demo, tools, tmp_path):
    """The demo, narrated, approved and rendered at master: everything a person would have done."""
    verify_all(demo)
    for sid in SCENES:
        import_take(demo, tools, sid, words_seconds(demo, sid, wpm=300), lead=0.1, tail=0.1, tmp=tmp_path)
    build_narration(validate_project(demo), tools, BuildOptions())
    result = validate_project(demo)
    approve_script(result, result.approvals, by="Asha")
    result = validate_project(demo)
    for aid in extra_used_ids(result.manifest, result.visuals) + tuple(
            s.narration_asset_id for s in result.scenes.scenes):
        result = validate_project(demo)
        review_asset(demo, result.manifest, result.registry, result.approvals, aid, decision=Decision.APPROVE,
                     by="Asha")
    render(validate_project(demo, verify_checksums=True), tools, MASTER)
    return demo


def qa(demo, tools, profile=MASTER, **kw):
    kw.setdefault("analyser", quiet)
    report = run_qa(validate_project(demo, verify_checksums=True), tools, profile, **kw)
    write_report(demo, report)
    return report


def codes(report, severity=None):
    return [k.code for k in report.checks if severity is None or k.severity == severity]


# --- parsing and thresholds ------------------------------------------------------

def test_parse_analysis_reads_every_detector():
    stderr = """
[blackdetect @ 0x1] black_start:10.5 black_end:12.25 black_duration:1.75
[freezedetect @ 0x2] lavfi.freezedetect.freeze_start: 20
[freezedetect @ 0x2] lavfi.freezedetect.freeze_duration: 5
[freezedetect @ 0x2] lavfi.freezedetect.freeze_end: 25
[freezedetect @ 0x2] lavfi.freezedetect.freeze_start: 50
[silencedetect @ 0x3] silence_start: 30
[silencedetect @ 0x3] silence_end: 34 | silence_duration: 4
[Parsed_ebur128_0 @ 0x4] Summary:

  Integrated loudness:
    I:         -19.8 LUFS
    Threshold: -30.0 LUFS

  Loudness range:
    LRA:         4.1 LU

  True peak:
    Peak:       -2.3 dBFS
"""
    m = parse_analysis(stderr, 55.0)
    assert (m.integrated_lufs, m.loudness_range_lu, m.true_peak_dbtp) == (-19.8, 4.1, -2.3)
    assert m.black_intervals == [(10.5, 1.75)]
    assert m.frozen_intervals == [(20.0, 5.0), (50.0, 5.0)]  # the last freeze runs to the end of the file
    assert m.silent_intervals == [(30.0, 4.0)]


def test_media_thresholds():
    def run(**kw):
        c = checks_mod._Checks()
        checks_mod._media_checks(c, QAMeasurements(duration_seconds=60, **kw))
        return {(k.code, k.severity) for k in c.items}

    assert run(integrated_lufs=-20, true_peak_dbtp=-2) == set()
    assert run(integrated_lufs=-10, true_peak_dbtp=-0.5) == {("audio.loudness", "warning"),
                                                              ("audio.peak_high", "warning")}
    assert ("audio.clipped", "blocker") in run(integrated_lufs=-14, true_peak_dbtp=0.2)
    assert ("audio.silent", "blocker") in run(integrated_lufs=-70)
    # Black at the very start or end is a fade; in the middle it's worth a look. Frozen always warns.
    edges = run(integrated_lufs=-20, black_intervals=[(0.0, 1.5), (58.0, 2.0)])
    assert edges == set()
    middle = run(integrated_lufs=-20, black_intervals=[(30.0, 1.5)], frozen_intervals=[(10.0, 6.0)],
                 silent_intervals=[(40.0, 4.0)])
    assert middle == {("picture.black", "warning"), ("picture.frozen", "warning"), ("audio.long_silence", "warning")}


# --- whole-project QA ------------------------------------------------------------

def test_unprepared_project_is_not_ready(demo, tools):
    report = qa(demo, tools)
    blockers = codes(report, "blocker")
    assert "render.missing" in blockers and "script.not_approved" in blockers
    assert "research.claim.critical_unreviewed" in blockers
    assert any(c.startswith("rights.") for c in blockers)
    assert report.blocker_count == len(blockers) and not report.media_analysed
    assert "NOT READY" in to_markdown(report)


def test_visual_plan_assets_need_rights_clearance(demo, tools):
    # With scenes listing no assets, the graphics reach the video only through the visual plan,
    # and they must still be cleared.
    edit_json(demo / "scenes.json", lambda d: [s.update(asset_ids=[]) for s in d["scenes"]])
    report = qa(demo, tools)
    assert "s01-title" in {k.subject for k in report.checks if k.code.startswith("rights.")}


def test_clean_master_waiver_signoff_and_gate(demo, tools, tmp_path):
    ready_demo(demo, tools, tmp_path)
    report = qa(demo, tools)
    assert report.blocker_count == 0, [k.check_id for k in report.checks if k.severity == "blocker"]
    assert report.media_analysed and report.output_sha256
    md = (demo / "reports/qa-master_16x9.md").read_text()
    assert "Human review checklist" in md and "- [ ] Narration and visuals are in sync" in md
    assert json.loads((demo / "reports/qa-master_16x9.json").read_text())["schema_version"] == "1.0"

    # Force a warning, so the waiver path is exercised.
    loud = lambda t, p, d: quiet(t, p, d).model_copy(update={"integrated_lufs": -26.0})  # noqa: E731
    report = qa(demo, tools, analyser=loud)
    assert report.open_warning_count >= 1 and "audio.loudness" in codes(report, "warning")
    result = validate_project(demo)
    with pytest.raises(QAError, match="open warning"):
        sign_off(result, report, by="Asha", checklist_done=True, note="", authorized=[])
    with pytest.raises(QAError, match="rationale"):
        waive_warning(result, report, "audio.loudness@video", by="Asha", rationale="ok", authorized=[])
    with pytest.raises(QAError, match="no check"):
        waive_warning(result, report, "nope@video", by="Asha", rationale="x" * 30, authorized=[])
    for k in report.checks:
        if k.open:
            waive_warning(validate_project(demo), report, k.check_id, by="Asha",
                          rationale="Quiet on purpose: a reflective film, checked on headphones.", authorized=[])
    report = qa(demo, tools, analyser=loud)
    assert report.open_warning_count == 0
    waived = next(k for k in report.checks if k.code == "audio.loudness")
    assert waived.waived_by == "Asha" and "headphones" in waived.waiver_rationale

    result = validate_project(demo)
    with pytest.raises(QAError, match="checklist"):
        sign_off(result, report, by="Asha", checklist_done=False, note="", authorized=[])
    with pytest.raises(ValueError, match="AUTHORIZED|not in"):
        sign_off(result, report, by="Mallory", checklist_done=True, note="", authorized=["Asha"])
    sign_off(result, report, by="Asha", checklist_done=True, note="Watched it twice.", authorized=[])
    result = validate_project(demo)
    assert result.manifest.project_status == "publication_ready" and result.ok

    # Any later edit makes the sign-off stale, and validation says so.
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(notes="changed after sign-off"))
    errors = validate_project(demo).errors
    assert "project.qa_signoff_required" in [i.code for i in errors]
    assert "changed after QA" in " ".join(i.message for i in errors)
    # Revoking still works while the gate is failing, and moves the status back.
    revoke_signoff(validate_project(demo), by="Asha", reason="Notes edited; needs another look.", authorized=[])
    assert validate_project(demo).manifest.project_status == "in_review"


def test_rerender_invalidates_waivers_and_signoff_needs_master(demo, tools, tmp_path):
    ready_demo(demo, tools, tmp_path)
    loud = lambda t, p, d: quiet(t, p, d).model_copy(update={"integrated_lufs": -26.0})  # noqa: E731
    report = qa(demo, tools, analyser=loud)
    waive_warning(validate_project(demo), report, "audio.loudness@video", by="Asha",
                  rationale="Quiet on purpose; checked on phone speakers.", authorized=[])
    assert qa(demo, tools, analyser=loud).open_warning_count == report.open_warning_count - 1

    # A changed project makes the render stale: a blocker, not something to waive.
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(hold_after_seconds=1.0))
    stale = qa(demo, tools, analyser=loud)
    assert "render.stale" in codes(stale, "blocker")
    render(validate_project(demo, verify_checksums=True), tools, MASTER)
    fresh = qa(demo, tools, analyser=loud)
    assert "render.stale" not in codes(fresh)
    assert next(k for k in fresh.checks if k.code == "audio.loudness").waived_by is None  # new file, new waiver

    preview = qa(demo, tools, "preview")
    with pytest.raises(QAError, match="master"):
        sign_off(validate_project(demo), preview, by="Asha", checklist_done=True, note="", authorized=[])


def test_output_tampering_and_skipped_media_block(demo, tools, tmp_path):
    ready_demo(demo, tools, tmp_path)
    skipped = qa(demo, tools, analyse_media=False)
    assert "media.not_analysed" in codes(skipped, "blocker")
    video = next((demo / "renders/master_16x9").glob("*.mp4"))
    video.chmod(0o644)
    with video.open("ab") as fh:
        fh.write(b"tamper")
    assert "output.changed" in codes(qa(demo, tools), "blocker")
    video.unlink()
    assert "output.missing" in codes(qa(demo, tools), "blocker")


def test_real_analysis_on_a_render(demo, tools, tmp_path):
    ready_demo(demo, tools, tmp_path)
    report = qa(demo, tools, analyser=checks_mod.analyse)
    m = report.measurements
    assert report.media_analysed and m.integrated_lufs is not None and m.duration_seconds > 0
    # The demo is still graphics, so frozen-picture warnings are expected (and waivable).
    assert all(k.waivable for k in report.checks if k.code == "picture.frozen")


def test_waiver_and_signoff_event_rules():
    from pydantic import ValidationError

    from reckoning_pipeline.schemas import ApprovalEvent
    base = dict(event_id="evt-0001", by="A", at="2026-10-20T12:00:00+00:00", fingerprint="a" * 64)
    with pytest.raises(ValidationError, match="qa_check"):
        ApprovalEvent(kind="qa_warning_waived", rationale="x" * 30, **base)
    with pytest.raises(ValidationError, match="rationale"):
        ApprovalEvent(kind="qa_warning_waived", qa_check="a@b", rationale="short", **base)
    with pytest.raises(ValidationError, match="qa_check"):
        ApprovalEvent(kind="qa_signoff", qa_check="a@b", **base)
    with pytest.raises(ValidationError, match="fingerprint"):
        ApprovalEvent(kind="qa_signoff", event_id="evt-0002", by="A", at="2026-10-20T12:00:00+00:00")


def test_cli_qa_report_and_signoff_errors(runner_env, demo):
    runner, app, cli = runner_env
    r = runner.invoke(app, ["qa", "report", str(demo), "--skip-media"])
    assert r.exit_code == cli.EXIT_FAILED and "NOT READY" in r.output and "render.missing" in r.output
    assert load_report(demo, MASTER) is not None and (demo / "reports/qa-master_16x9.md").is_file()
    r = runner.invoke(app, ["qa", "signoff", str(demo), "--by", "Asha", "--checklist-done"])
    assert r.exit_code == cli.EXIT_FAILED and "blocker" in r.output
    r = runner.invoke(app, ["qa", "waive", str(demo), "render.missing@master_16x9", "--by", "Asha",
                            "--rationale", "x" * 30])
    assert r.exit_code == cli.EXIT_FAILED and "only warnings can be waived" in r.output
    r = runner.invoke(app, ["qa", "report", str(demo), "--profile", "vertical"])
    assert r.exit_code == cli.EXIT_FAILED and "unknown profile" in r.output
