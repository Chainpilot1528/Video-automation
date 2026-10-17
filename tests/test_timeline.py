from pathlib import Path

import pytest
from conftest import DEMO, edit_json

from reckoning_pipeline.project import validate_project
from reckoning_pipeline.render.commands import concat_list, scene_command, segment_filter
from reckoning_pipeline.render.profiles import ProfileError, get_profile
from reckoning_pipeline.schemas.timeline import RenderProfile
from reckoning_pipeline.timeline import LEAD_IN, TAIL_HOLD, TimelineError, compile_timeline

PH = Path("/tmp/placeholders")
SHA = "a" * 64


def plan_for(demo, profile="preview", **kw):
    r = validate_project(demo)
    assert r.ok, [str(i) for i in r.issues]
    return compile_timeline(r, get_profile(profile, r.manifest), ffmpeg_version="test", placeholder_dir=PH, **kw)


def fake_narration(demo, scene_id, seconds):
    """Point a scene at a fake narration asset with a measured duration (no audio needed for compiling)."""
    wav = demo / "narration" / f"{scene_id}.wav"
    wav.parent.mkdir(exist_ok=True)
    wav.write_bytes(b"RIFF")
    import hashlib
    sha = hashlib.sha256(b"RIFF").hexdigest()
    edit_json(demo / "assets/registry.json", lambda d: d["assets"].append({
        "asset_id": f"narr-{scene_id}", "path": f"narration/{scene_id}.wav", "type": "narration",
        "creation_method": "recorded", "sha256": sha, "intended_scene_ids": [scene_id]}))
    edit_json(demo / "scenes.json", lambda d: next(s for s in d["scenes"] if s["scene_id"] == scene_id).update(
        narration_asset_id=f"narr-{scene_id}", actual_narration_duration_seconds=seconds))


# --- profiles ----------------------------------------------------------------

def test_profiles():
    m = validate_project(DEMO).manifest
    assert (get_profile("preview", m).width, get_profile("master_16x9", m).width) == (960, 1920)
    with pytest.raises(ProfileError, match="Phase 11"):
        get_profile("vertical_9x16", m)
    with pytest.raises(ProfileError, match="unknown"):
        get_profile("4k", m)


# --- compiler ----------------------------------------------------------------

def test_silent_preview_uses_planned_estimates_and_warns():
    plan = plan_for(DEMO)
    assert [s.duration for s in plan.scenes] == [10.0, 14.0, 14.0, 10.0]
    assert [s.start for s in plan.scenes] == [0.0, 10.0, 24.0, 38.0]
    assert plan.total_duration == 48.0 and plan.placeholder_count == 0
    assert sum("silent preview" in w for w in plan.warnings) == 4


def test_narrated_scene_duration_comes_from_measured_audio(demo):
    fake_narration(demo, "s02-claim-ledger", 7.25)
    s = next(x for x in plan_for(demo).scenes if x.scene_id == "s02-claim-ledger")
    assert s.duration == pytest.approx(LEAD_IN + 7.25 + TAIL_HOLD)
    assert s.narration.duration == 7.25 and s.lead_in == LEAD_IN


def test_master_refuses_missing_narration_and_placeholders(demo):
    with pytest.raises(TimelineError, match="no measured audio"):
        plan_for(demo, "master_16x9")
    for sid, secs in (("s01-cold-open", 8), ("s02-claim-ledger", 7), ("s03-asset-record", 8),
                      ("s04-review-gates", 6)):
        fake_narration(demo, sid, secs)
    assert plan_for(demo, "master_16x9").placeholder_count == 0
    edit_json(demo / "visuals.json", lambda d: d["beats"].append({
        "beat_id": "v-gap", "scene_id": "s01-cold-open", "order": 2, "takeaway": "t",
        "visual_type": "licensed_stock", "requirements": "archive photo"}))
    with pytest.raises(TimelineError, match="placeholder"):
        plan_for(demo, "master_16x9")
    assert plan_for(demo).placeholder_count == 1  # preview allows it


def test_fades_are_inside_scenes_and_clamped(demo):
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(
        planned_duration_seconds=1.2, transition_out={"type": "dissolve", "duration_seconds": 2.0}))
    plan = plan_for(demo)
    s = plan.scenes[0]
    assert s.fade_out == pytest.approx(0.4)  # at most a third of the scene
    assert any("dip through black" in w for w in plan.warnings)
    assert plan.total_duration == pytest.approx(sum(x.duration for x in plan.scenes))  # no overlaps


def test_beats_split_evenly_or_follow_offsets(demo):
    def two_beats(d):
        d["beats"].append({"beat_id": "v01b", "scene_id": "s01-cold-open", "order": 2, "takeaway": "t",
                           "visual_type": "original_graphic", "graphic_kind": "diagram",
                           "asset_ids": ["s02-claim-ledger"]})
    edit_json(demo / "visuals.json", two_beats)
    s = plan_for(demo).scenes[0]
    assert [(g.start, g.duration) for g in s.segments] == [(0.0, 5.0), (5.0, 5.0)]

    def offsets(d):
        d["beats"][0]["offset_seconds"] = 0
        d["beats"][-1]["offset_seconds"] = 7.5
    edit_json(demo / "visuals.json", offsets)
    s = plan_for(demo).scenes[0]
    assert [(g.start, g.duration) for g in s.segments] == [(0.0, 7.5), (7.5, 2.5)]


def test_unresolved_and_unplanned_scenes_get_placeholders(demo):
    edit_json(demo / "visuals.json", lambda d: d.update(beats=[b for b in d["beats"]
                                                                if b["scene_id"] != "s03-asset-record"]))
    edit_json(demo / "scenes.json", lambda d: d["scenes"][2].update(asset_ids=[]))
    s = next(x for x in plan_for(demo).scenes if x.scene_id == "s03-asset-record")
    assert s.segments[0].kind == "placeholder" and "No visual plan" in s.segments[0].placeholder_text
    assert s.segments[0].path == str(PH / "s03-asset-record-no-plan.svg")


def test_unrendered_motion_and_extra_assets_warn(demo):
    edit_json(demo / "visuals.json", lambda d: d["beats"][0]["asset_ids"].append("s04-review-gates"))
    warnings = " ".join(plan_for(demo).warnings)
    assert "'build' motion is not rendered" in warnings and "only the first of 2 assets" in warnings


def test_labels_flow_to_segments_for_generated_beats(demo):
    edit_json(demo / "visuals.json", lambda d: d["beats"][3].update(
        visual_type="generated", graphic_kind=None, label="AI illustration", generation={"prompt": "p"}))
    s = plan_for(demo).scenes[3]
    assert s.segments[0].label == "AI illustration"


def test_fingerprints_change_only_for_the_changed_scene(demo):
    before = {s.scene_id: s.fingerprint for s in plan_for(demo).scenes}
    edit_json(demo / "visuals.json", lambda d: d["beats"][2].update(asset_ids=["s04-review-gates"]))
    after = {s.scene_id: s.fingerprint for s in plan_for(demo).scenes}
    changed = [k for k in before if before[k] != after[k]]
    assert changed == ["s03-asset-record"]


def test_fingerprint_covers_profile_and_caption_burn(demo):
    a = plan_for(demo).scenes[0].fingerprint
    b = plan_for(demo, burn_captions=True).scenes[0].fingerprint  # no cues yet, but the flag still counts
    assert a != b


def test_invalid_project_refused(demo):
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(asset_ids=["ghost"]))
    r = validate_project(demo)
    with pytest.raises(TimelineError, match="validation errors"):
        compile_timeline(r, get_profile("preview", r.manifest), ffmpeg_version="t", placeholder_dir=PH)


# --- command construction ----------------------------------------------------

PROFILE = RenderProfile(name="preview", width=320, height=180, fps=30, video_preset="ultrafast", crf=30,
                        audio_bitrate="96k", audio_sample_rate=48000, allow_placeholders=True,
                        require_narration=False)


def test_scene_command_is_an_argument_array_with_expected_graph():
    scene = plan_for(DEMO).scenes[0]
    cmd = scene_command("/usr/bin/ffmpeg", scene, PROFILE, "out.mp4", label_files={}, captions_file=None)
    assert isinstance(cmd, list) and all(isinstance(a, str) for a in cmd)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "zoompan" in graph and "fade=t=out" in graph and "anullsrc" in " ".join(cmd)
    assert cmd[-1] == "out.mp4" and "-pix_fmt" in cmd and "yuv420p" in cmd
    assert cmd[cmd.index("-t", len(cmd) - 12) + 1] == f"{scene.duration:.3f}"


def test_labels_and_captions_use_relative_helper_files():
    scene = plan_for(DEMO).scenes[1]
    seg = scene.segments[0]
    f = segment_filter(0, seg, PROFILE, "label-x.txt")
    assert "textfile=label-x.txt" in f and "drawtext" in f
    cmd = scene_command("ffmpeg", scene, PROFILE, "o.mp4", label_files={}, captions_file="captions.srt")
    assert "subtitles=captions.srt" in cmd[cmd.index("-filter_complex") + 1]


def test_concat_list_quotes_paths():
    text = concat_list([Path("/a/b c.mp4"), Path("/a/it's.mp4")])
    assert text == "file '/a/b c.mp4'\nfile '/a/it'\\''s.mp4'\n"
