import json

import pytest
from conftest import edit_json
from test_narration import HAVE_FFMPEG, import_take, tools, words_seconds  # noqa: F401

from reckoning_pipeline.media.video import probe_video
from reckoning_pipeline.narration import BuildOptions, build_narration
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.render import RenderError, render
from reckoning_pipeline.render import runner as runner_mod
from reckoning_pipeline.schemas.timeline import RenderProfile
from reckoning_pipeline.subtitles import parse_srt
from reckoning_pipeline.timeline import TimelineError

pytestmark = pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
SCENES = ("s01-cold-open", "s02-claim-ledger", "s03-asset-record", "s04-review-gates")


@pytest.fixture(autouse=True)
def tiny_profiles(monkeypatch):
    """Render small and fast in tests; the real profiles are covered in test_timeline."""
    def tiny(name, manifest):
        from reckoning_pipeline.render.profiles import get_profile as real
        p = real(name, manifest)
        return p.model_copy(update={"width": 320, "height": 180, "video_preset": "ultrafast", "crf": 32})
    monkeypatch.setattr(runner_mod, "get_profile", tiny)


@pytest.fixture
def short_demo(demo):
    """Demo with short silent scenes, so renders take seconds."""
    edit_json(demo / "scenes.json", lambda d: [s.update(planned_duration_seconds=1.5) for s in d["scenes"]])
    return demo


def run(demo, tools, profile="preview", **kw):
    return render(validate_project(demo, verify_checksums=True), tools, profile, **kw)


def test_preview_renders_a_valid_mp4_with_report(short_demo, tools):
    out = run(short_demo, tools)
    assert out.output.is_file() and out.rendered == list(SCENES) and not out.cached
    info = probe_video(tools, out.output)
    assert (info.width, info.height, info.video_codec, info.audio_codec) == (320, 180, "h264", "aac")
    assert info.frame_rate == 30 and info.pixel_format == "yuv420p" and info.audio_sample_rate == 48000
    assert info.duration_seconds == pytest.approx(6.0, abs=0.25)
    report = json.loads(out.report_path.read_text())
    assert report["status"] == "succeeded" and report["output"]["sha256"]
    assert len(report["inputs"]) == 4 and all(i["role"] == "visual:image" for i in report["inputs"])
    assert report["commands"] and report["commands"][0][0].endswith("ffmpeg")
    assert (short_demo / "reports/timeline-preview.json").is_file()
    assert not list(out.output.parent.glob("*.partial.mp4"))


def test_rerender_reuses_everything_and_one_change_rerenders_one_scene(short_demo, tools):
    first = run(short_demo, tools)
    again = run(short_demo, tools)
    assert again.rendered == [] and again.final_cached and again.output == first.output
    edit_json(short_demo / "visuals.json", lambda d: d["beats"][2].update(asset_ids=["s04-review-gates"]))
    third = run(short_demo, tools)
    assert third.rendered == ["s03-asset-record"] and len(third.cached) == 3
    assert third.output != first.output and first.output.is_file()  # never overwritten


def test_narrated_render_with_sidecar_and_burned_captions(demo, tools, tmp_path):
    for sid in SCENES:
        import_take(demo, tools, sid, words_seconds(demo, sid, wpm=300), lead=0.1, tail=0.1, tmp=tmp_path)
    build_narration(validate_project(demo), tools, BuildOptions())
    out = run(demo, tools, burn_captions=True)
    cues = parse_srt(out.captions.read_text())
    assert cues and cues[-1].end <= out.plan.total_duration
    assert cues[0].start >= 0.25  # lead-in before narration
    scenes = {s.scene_id: s for s in validate_project(demo).scenes.scenes}
    planned = {s.scene_id: s.duration for s in out.plan.scenes}
    assert all(scenes[k].final_duration_seconds == planned[k] for k in SCENES)
    info = probe_video(tools, out.output)
    assert info.duration_seconds == pytest.approx(out.plan.total_duration, abs=0.3)


def test_master_refuses_placeholders_before_rendering(short_demo, tools):
    with pytest.raises(TimelineError, match="no measured audio"):
        run(short_demo, tools, "master_16x9")
    assert not (short_demo / "renders/master_16x9/scenes").exists()


def test_placeholders_render_in_preview(short_demo, tools):
    edit_json(short_demo / "visuals.json", lambda d: d["beats"].append({
        "beat_id": "v-gap", "scene_id": "s01-cold-open", "order": 2, "takeaway": "t",
        "visual_type": "licensed_stock", "requirements": "archive photo"}))
    out = run(short_demo, tools)
    assert out.plan.placeholder_count == 1
    assert (short_demo / "renders/preview/build/placeholders/v-gap.svg").is_file()


def test_failure_keeps_logs_and_writes_failed_report(short_demo, tools):
    # A registered "image" that is not an image: checksum matches, FFmpeg can't decode it.
    bad = short_demo / "assets/graphics/s04_review_gates.svg"
    bad.chmod(0o644)
    bad.write_text("not an svg")
    import hashlib
    sha = hashlib.sha256(b"not an svg").hexdigest()
    edit_json(short_demo / "assets/registry.json",
              lambda d: next(a for a in d["assets"] if a["asset_id"] == "s04-review-gates").update(sha256=sha))
    with pytest.raises(RenderError, match="s04-review-gates"):
        run(short_demo, tools)
    assert (short_demo / "renders/preview/logs/s04-review-gates.log").read_text().startswith("$ ")
    reports = sorted((short_demo / "reports").glob("render-preview-*.json"))
    assert json.loads(reports[-1].read_text())["status"] == "failed"
    # Scenes that succeeded are kept, so the next run resumes from there.
    assert len(list((short_demo / "renders/preview/scenes").glob("*.mp4"))) == 3


def test_changed_asset_file_is_refused_by_checksum(short_demo, tools):
    (short_demo / "assets/graphics/s01_title.svg").chmod(0o644)
    with (short_demo / "assets/graphics/s01_title.svg").open("a") as fh:
        fh.write("<!-- edit -->")
    assert not validate_project(short_demo, verify_checksums=True).ok


def test_dry_run_compiles_only(short_demo, tools):
    out = run(short_demo, tools, dry_run=True)
    assert out.output is None and (short_demo / "reports/timeline-preview.json").is_file()
    assert not (short_demo / "renders/preview/scenes").exists()


def test_cli_render(runner_env, short_demo):
    runner, app, cli = runner_env
    r = runner.invoke(app, ["timeline", "build", str(short_demo)])
    assert r.exit_code == cli.EXIT_OK and "Total 6.00 s" in r.output
    r = runner.invoke(app, ["render", "preview", str(short_demo), "--dry-run"])
    assert r.exit_code == cli.EXIT_OK and "[dry-run] 4 scenes" in r.output
    r = runner.invoke(app, ["render", "master", str(short_demo)])
    assert r.exit_code == cli.EXIT_FAILED and "no measured audio" in r.output
    assert runner.invoke(app, ["render", "vertical", str(short_demo)]).exit_code == cli.EXIT_NOT_IMPLEMENTED
