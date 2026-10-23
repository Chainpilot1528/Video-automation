"""The chapter map: stone-steps graphic, beat schema, compiled camera move and medallions, a real render."""

import json
from pathlib import Path

import pytest
from conftest import edit_json
from pydantic import ValidationError
from test_narration import HAVE_FFMPEG, tools  # noqa: F401
from test_render import short_demo, tiny_profiles  # noqa: F401  (fixtures: short scenes, small renders)

from reckoning_pipeline.graphics import chapter_map as cmap
from reckoning_pipeline.graphics.register import render_graphic
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.project.validate import extra_used_ids
from reckoning_pipeline.render import render
from reckoning_pipeline.render.compose import composition_command
from reckoning_pipeline.schemas.timeline import RenderProfile, TimelineLayer
from reckoning_pipeline.schemas.visual import ChapterMapView, GraphicSpec, VisualBeat
from reckoning_pipeline.timeline import compile_timeline

PROFILE = RenderProfile(name="preview", width=320, height=180, fps=30, video_preset="ultrafast", crf=32,
                        audio_bitrate="96k", audio_sample_rate=48000, allow_placeholders=True,
                        require_narration=False)
LEVELS = [{"title": "Pleasure, Rightly Understood", "subtitle": "Epicurus · Athens"},
          {"title": "Flourishing & Virtue", "subtitle": "Aristotle"},
          {"title": "Happiness Is Not the Point"}]


def spec(**kw):
    return GraphicSpec(**{"asset_id": "chapter-map", "kind": "chapter_map", "title": "Answers to Happiness",
                          "levels": LEVELS, **kw})


# --- the graphic -------------------------------------------------------------------

def test_spec_rules():
    with pytest.raises(ValidationError, match="2-8 levels"):
        spec(levels=LEVELS[:1])
    with pytest.raises(ValidationError, match="only for chapter maps"):
        GraphicSpec(asset_id="t", kind="title", title="T", levels=LEVELS)


def test_svg_is_deterministic_and_carries_its_geometry(tmp_path):
    svg = cmap.render_chapter_map(spec())
    assert svg == cmap.render_chapter_map(spec())
    assert 'data-chapter-levels="3"' in svg and f'height="{cmap.map_height(3)}"' in svg
    assert "LEVEL III" in svg and "Flourishing &amp; Virtue" in svg and "ANSWERS TO HAPPINESS" in svg
    (tmp_path / "m.svg").write_text(svg)
    assert cmap.levels_in(tmp_path / "m.svg") == 3 and cmap.levels_in(tmp_path / "missing.svg") is None
    # Each step down is wider (a temple's stepped base), and every medallion place sits on its own step.
    widths = [r - left for left, r in (cmap.slab_x(lv, 3) for lv in (1, 2, 3))]
    assert widths == sorted(widths) and widths[0] < widths[-1]
    for lv in (1, 2, 3):
        left, right = cmap.slab_x(lv, 3)
        for slot in (1, 2, 3):
            x, y = cmap.marker_anchor(lv, slot, 3)
            assert left < x - cmap.MEDALLION_W / 2 and x + cmap.MEDALLION_W / 2 < right
            assert abs(y - cmap.view_y(lv)) < cmap.PITCH / 2


# --- the beat ----------------------------------------------------------------------

BEAT = dict(beat_id="v1", scene_id="s1", order=1, takeaway="t", visual_type="original_graphic",
            graphic_kind="chapter_map")


def test_view_and_beat_rules():
    with pytest.raises(ValidationError, match="more than 3"):
        ChapterMapView(asset_id="m", level=1, markers=[{"level": 1, "asset_id": f"a{i}"} for i in range(4)])
    with pytest.raises(ValidationError, match="share a slot"):
        ChapterMapView(asset_id="m", level=1, markers=[{"level": 1, "asset_id": "a", "slot": 2},
                                                       {"level": 1, "asset_id": "b", "slot": 2}])
    assert ChapterMapView(asset_id="m", level=3).start_level() == 2
    assert ChapterMapView(asset_id="m", level=1).start_level() == 1
    view = {"asset_id": "m", "level": 2, "markers": [{"level": 1, "asset_id": "a"}]}
    beat = VisualBeat(**BEAT, asset_ids=["m", "a"], chapter_map=view)    # structure, not data: no sources needed
    assert beat.is_composition
    with pytest.raises(ValidationError, match="chapter map"):
        VisualBeat(**BEAT, asset_ids=["m"], chapter_map=view)


def add_map_beat(demo, **view):
    result = validate_project(demo)
    render_graphic(demo, result.manifest, result.registry, result.ledger, spec())
    chapter = {"asset_id": "chapter-map", "level": 2, "pan_start": 0.2, "pan_seconds": 0.8, "markers": [
        {"level": 1, "asset_id": "s02-claim-ledger", "name": "Epicurus"},
        {"level": 2, "asset_id": "s03-asset-record", "name": "Aristotle", "crop": [0.1, 0, 0.9, 1]}], **view}
    images = list(dict.fromkeys(["chapter-map", *(m["asset_id"] for m in chapter["markers"])]))

    def mutate(d):
        d["beats"] = [b for b in d["beats"] if b["scene_id"] != "s01-cold-open"]
        d["beats"].append({**BEAT, "beat_id": "v01-map", "scene_id": "s01-cold-open", "asset_ids": images,
                           "chapter_map": chapter})
    edit_json(demo / "visuals.json", mutate)


def compiled(demo):
    plan = compile_timeline(validate_project(demo), PROFILE, ffmpeg_version="t", placeholder_dir=Path("/tmp/ph"))
    return plan, plan.scenes[0].segments[0]


def test_compiler_builds_one_eased_camera_move(short_demo):  # noqa: F811
    add_map_beat(short_demo)
    result = validate_project(short_demo)
    assert result.ok, result.errors
    assert not [w for w in result.warnings if w.code == "asset.unused"]
    assert {"chapter-map", "s02-claim-ledger"} <= set(extra_used_ids(result.manifest, result.visuals))
    _, seg = compiled(short_demo)
    assert seg.kind == "composition"
    mp, old, old_name, new, new_name = seg.layers
    # The map rests on level I (its centre is below the frame centre), then moves up half a frame.
    assert mp.asset_id == "chapter-map" and mp.width == 1.0
    assert mp.y == pytest.approx(0.5 + (cmap.map_height(3) / 2 - cmap.view_y(1)) / 1080, abs=1e-3)
    assert mp.drift_y == pytest.approx(-cmap.PITCH / 1080, abs=1e-3)
    assert (mp.motion_start, mp.motion_end, mp.motion_ease) == (0.2, 1.0, True)
    # Medallions ride along; the earlier one is there from the start, the new one arrives with the camera.
    assert all(x.drift_y == mp.drift_y and x.motion_ease for x in (old, old_name, new, new_name))
    assert old.start == 0 and new.start == pytest.approx(0.7) and new.ring and new.edge == "oval"
    assert new.crop == (0.1, 0, 0.9, 1) and new_name.text == "Aristotle" and new_name.text_style == "label"
    assert old.x == pytest.approx(cmap.marker_anchor(1, 1, 3)[0] / 1920, abs=1e-3)


def test_climbing_back_up_is_a_recap(short_demo):  # noqa: F811
    add_map_beat(short_demo, level=1, from_level=3)
    _, seg = compiled(short_demo)
    medallions = [x for x in seg.layers[1:] if x.kind == "image"]
    assert seg.layers[0].drift_y == pytest.approx(2 * cmap.PITCH / 1080, abs=1e-3)   # the map moves down
    assert all(m.start == 0 for m in medallions)


def test_compiler_falls_back_to_a_placeholder(short_demo):  # noqa: F811
    add_map_beat(short_demo, level=5)
    plan, seg = compiled(short_demo)
    assert seg.kind == "placeholder" and any("only 3 levels" in w for w in plan.warnings)


def test_eased_motion_uses_smoothstep():
    layer = TimelineLayer(kind="image", asset_id="m", path="/m.png", y=2.4, max_height=2.6, drift_y=-0.5,
                          motion_start=1, motion_end=3, motion_ease=True)
    graph = composition_command("ffmpeg", [layer], ["m.png"], PROFILE, 5.0, "o.mp4")
    graph = graph[graph.index("-filter_complex") + 1]
    assert "*(3-2*(clip((t-1)/2,0,1)))" in graph


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_map_beat_renders(short_demo, tools):  # noqa: F811
    add_map_beat(short_demo)
    out = render(validate_project(short_demo, verify_checksums=True), tools, "preview")
    clips = list((short_demo / "renders/preview/build/s01-cold-open").glob("comp-v01-map-*.mp4"))
    assert len(clips) == 1
    roles = [i["role"] for i in json.loads(out.report_path.read_text())["inputs"]]
    assert roles.count("visual:layer") == 3     # the map and both medallions count for rights and credits


# --- the core style -----------------------------------------------------------------

def test_core_style_svg_and_geometry(tmp_path):
    from reckoning_pipeline.graphics import chapter_core as core
    from reckoning_pipeline.graphics.maps import map_info
    from reckoning_pipeline.graphics.svg import render_spec
    s = spec(style="core")
    svg = render_spec(s, None)
    assert svg == render_spec(s, None) and 'data-chapter-style="core"' in svg and "LEVEL III" in svg
    (tmp_path / "c.svg").write_text(svg)
    module, n = map_info(tmp_path / "c.svg")
    assert module is core and n == 3
    (tmp_path / "s.svg").write_text(cmap.render_chapter_map(spec()))
    assert map_info(tmp_path / "s.svg")[0] is cmap
    # each level sits one band deeper, and its medallion place is on its own band
    ys = [core.view_center(lv, 3)[1] for lv in (1, 2, 3)]
    assert [b - a for a, b in zip(ys, ys[1:])] == [core.BAND, core.BAND]
    for lv in (1, 2, 3):
        x, y = core.marker_anchor(lv, 1, 3)
        assert x > core.view_center(lv, 3)[0] and abs(y - core.view_center(lv, 3)[1]) < core.BAND
    with pytest.raises(ValidationError, match="only for chapter maps"):
        GraphicSpec(asset_id="t", kind="title", title="T", style="core")


def test_compiler_places_the_core_camera_and_medallions(short_demo):  # noqa: F811
    from reckoning_pipeline.graphics import chapter_core as core
    result = validate_project(short_demo)
    render_graphic(short_demo, result.manifest, result.registry, result.ledger,
                   spec(asset_id="chapter-core", style="core"))
    add_map_beat(short_demo, asset_id="chapter-core")

    def retarget(d):
        b = next(x for x in d["beats"] if x["beat_id"] == "v01-map")
        b["asset_ids"] = ["chapter-core" if a == "chapter-map" else a for a in b["asset_ids"]]
    edit_json(short_demo / "visuals.json", retarget)
    _, seg = compiled(short_demo)
    stars = [x for x in seg.layers if x.shape == "stars"]
    glow = next(x for x in seg.layers if x.shape == "glow")
    assert len(stars) == 2 and all(x.pulse > 0 for x in stars) and seg.layers[:2] == stars   # behind the planet
    assert glow.pulse > 0 and glow.drift_y == pytest.approx(-core.BAND / 1080, abs=1e-3)       # rides with the core
    mp, old, _, new, _ = [x for x in seg.layers if x.kind != "shape"]
    w, h = core.map_size(3)
    assert mp.width == pytest.approx(w / 1920, abs=1e-3) and mp.drift_y == pytest.approx(-core.BAND / 1080, abs=1e-3)
    assert new.start == pytest.approx(0.7) and new.width == pytest.approx(core.MEDALLION_W / 1920, abs=1e-3)


def test_core_overview_and_pulse():
    from reckoning_pipeline.graphics.chapter_core import overview_surface, render_chapter_core_overview
    svg = render_chapter_core_overview(spec(style="core", variant="overview"))
    assert 'width="1920" height="1080"' in svg and "core-overview" in svg and "LEVEL" not in svg
    x, y = overview_surface(3)
    assert x == 960 and 0 < y < 1080
    with pytest.raises(ValidationError, match="overview variant"):
        spec(variant="overview")
    layer = TimelineLayer(kind="shape", shape="glow", path="", pulse=4.0, seed=0)
    graph = composition_command("ffmpeg", [layer], ["g.png"], PROFILE, 6.0, "o.mp4")
    assert "sin(2*PI*T/4" in graph[graph.index("-filter_complex") + 1]
