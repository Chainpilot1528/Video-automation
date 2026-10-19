import pytest
from conftest import edit_json
from test_narration import HAVE_FFMPEG, FakeTTS, tools  # noqa: F401
from test_render import tiny_profiles  # noqa: F401  (autouse fixture: small, fast renders)

from reckoning_pipeline.assets import build_rights_report
from reckoning_pipeline.assets.intake import IntakeError
from reckoning_pipeline.assets.music_bed import create_pad, set_music
from reckoning_pipeline.media.audio import measure_loudness, probe_audio
from reckoning_pipeline.media.music import pad_expression
from reckoning_pipeline.media.video import probe_video
from reckoning_pipeline.narration import BuildOptions, build_narration
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.project.validate import music_ids
from reckoning_pipeline.render import render
from reckoning_pipeline.render.commands import music_mix_command
from reckoning_pipeline.schemas.timeline import RenderProfile, TimelineMusic
from reckoning_pipeline.timeline import LEAD_IN, compile_timeline

pytestmark = pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
PROFILE = RenderProfile(name="preview", width=320, height=180, fps=30, video_preset="ultrafast", crf=32,
                        audio_bitrate="96k", audio_sample_rate=48000, allow_placeholders=True,
                        require_narration=False)


def test_pad_expression_is_a_chord_with_a_pulse():
    expr = pad_expression(110.0)
    assert "sin(2*PI*110.000*t)" in expr and "exp(-2.5*mod(t,4.0))" in expr


def test_pad_is_original_registered_and_deterministic(demo, tools):
    r = validate_project(demo)
    a = create_pad(demo, r.manifest, r.registry, tools, "bed", duration=8)
    assert (a.type, a.creation_method, a.commercial_use, a.platform_cleared) == ("music", "generated", "allowed", True)
    assert "no samples" in a.rights_evidence and a.publication_status == "pending_review"
    info = probe_audio(tools, demo / a.path)
    assert info.channels == 2 and info.duration_seconds == pytest.approx(8, abs=0.3)
    assert -27 < measure_loudness(tools, demo / a.path).integrated_lufs < -21
    r = validate_project(demo)
    b = create_pad(demo, r.manifest, r.registry, tools, "bed-2", duration=8)
    assert b.sha256 == a.sha256  # same settings, same bytes
    with pytest.raises(IntakeError, match="already exists"):
        create_pad(demo, validate_project(demo).manifest, validate_project(demo).registry, tools, "bed", duration=8)


def test_music_settings_validation_and_rights(demo, tools):
    r = validate_project(demo)
    create_pad(demo, r.manifest, r.registry, tools, "bed", duration=6)
    r = validate_project(demo)
    with pytest.raises(IntakeError, match="not a registered music"):
        set_music(demo, r.manifest, r.registry, "s01-title")
    set_music(demo, r.manifest, r.registry, "bed", gain_db=-18)
    r = validate_project(demo)
    assert r.ok and r.manifest.music.gain_db == -18 and music_ids(r.manifest) == ("bed",)
    report = build_rights_report(r.registry, r.scenes, r.approvals, music_ids(r.manifest))
    assert "bed" in report.used_asset_ids and any(f.subject == "bed" for f in report.blockers)
    edit_json(demo / "project.json", lambda d: d["music"].update(asset_id="s01-title"))
    assert "music.wrong_type" in [i.code for i in validate_project(demo).errors]


def test_music_changes_plan_fingerprint_and_is_mixed(demo, tools):
    edit_json(demo / "scenes.json", lambda d: [s.update(planned_duration_seconds=1.5) for s in d["scenes"]])
    r = validate_project(demo)
    from pathlib import Path
    p0 = compile_timeline(r, PROFILE, ffmpeg_version="t", placeholder_dir=Path("/tmp/ph"))
    create_pad(demo, r.manifest, r.registry, tools, "bed", duration=10)
    r = validate_project(demo)
    set_music(demo, r.manifest, r.registry, "bed")
    r = validate_project(demo, verify_checksums=True)
    p1 = compile_timeline(r, PROFILE, ffmpeg_version="t", placeholder_dir=Path("/tmp/ph"))
    assert p1.music and p1.fingerprint != p0.fingerprint
    assert [s.fingerprint for s in p1.scenes] == [s.fingerprint for s in p0.scenes]  # scenes reused

    out = render(r, tools, "preview")
    info = probe_video(tools, out.output)
    assert info.audio_codec == "aac" and info.duration_seconds == pytest.approx(6.0, abs=0.3)
    # Silent demo scenes + music bed: the mix must now actually contain sound.
    assert measure_loudness(tools, out.output).integrated_lufs is not None
    assert any(len(c) and "sidechaincompress" in " ".join(c) for c in __import__("json").loads(
        out.report_path.read_text())["commands"])


def test_music_mix_command_shape():
    m = TimelineMusic(asset_id="bed", path="/m/bed.wav", sha256="a" * 64, gain_db=-14, duck=True, fade_in=2,
                      fade_out=3)
    cmd = music_mix_command("ffmpeg", "in.mp4", m, PROFILE, 30.0, "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "-stream_loop" in cmd and cmd[cmd.index("-c:v") + 1] == "copy"
    assert "sidechaincompress" in graph and "volume=-14" in graph and "afade=t=out:st=27.000:d=3.000" in graph
    flat = music_mix_command("ffmpeg", "in.mp4", m.model_copy(update={"duck": False}), PROFILE, 30.0, "o.mp4")
    assert "sidechaincompress" not in flat[flat.index("-filter_complex") + 1]


def test_scene_speed_and_hold(demo, tools):
    tts = FakeTTS(tools)
    sid = "s04-review-gates"
    base = build_narration(validate_project(demo), tools, BuildOptions(provider=tts, voice="v", scene_ids=[sid]))
    edit_json(demo / "scenes.json", lambda d: next(s for s in d["scenes"] if s["scene_id"] == sid).update(
        narration_speed=0.8, hold_after_seconds=1.5))
    slow = build_narration(validate_project(demo), tools, BuildOptions(provider=tts, voice="v", scene_ids=[sid]))
    assert not slow.report.chunks[0].cached
    assert slow.report.chunks[0].duration_seconds == pytest.approx(base.report.chunks[0].duration_seconds / 0.8,
                                                                   abs=0.1)
    from pathlib import Path
    r = validate_project(demo)
    plan = compile_timeline(r, PROFILE, ffmpeg_version="t", placeholder_dir=Path("/tmp/ph"))
    scene = next(s for s in plan.scenes if s.scene_id == sid)
    assert scene.duration == pytest.approx(LEAD_IN + slow.report.chunks[0].duration_seconds + 1.5, abs=0.01)
