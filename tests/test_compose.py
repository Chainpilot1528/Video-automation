"""Compositions: layer schema rules, pure command/SVG builders, and a real layered render."""

import json

import pytest
from conftest import edit_json
from pydantic import ValidationError
from test_narration import HAVE_FFMPEG, tools  # noqa: F401
from test_render import short_demo, tiny_profiles  # noqa: F401  (fixtures: short scenes, small renders)

from reckoning_pipeline.media.video import probe_video
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.project.validate import extra_used_ids
from reckoning_pipeline.render import render
from reckoning_pipeline.render.compose import (
    ACCENT, INK, composition_command, image_prepare_command, mask_expr, text_svg,
)
from reckoning_pipeline.schemas.timeline import RenderProfile, TimelineLayer
from reckoning_pipeline.schemas.visual import Layer, VisualBeat

PROFILE = RenderProfile(name="preview", width=320, height=180, fps=30, video_preset="ultrafast", crf=32,
                        audio_bitrate="96k", audio_sample_rate=48000, allow_placeholders=True,
                        require_narration=False)
BEAT = dict(beat_id="v1", scene_id="s1", order=1, takeaway="t", visual_type="licensed_stock")


# --- schema ------------------------------------------------------------------------

def test_layer_rules():
    with pytest.raises(ValidationError, match="need an asset_id"):
        Layer(kind="image")
    with pytest.raises(ValidationError, match="need text"):
        Layer(kind="text", text="  ")
    with pytest.raises(ValidationError, match="highlight must be part"):
        Layer(kind="text", text="Know thyself", highlight="nothing")
    with pytest.raises(ValidationError, match="end after it starts"):
        Layer(kind="text", text="x", start=3, end=2)
    with pytest.raises(ValidationError, match="crop"):
        Layer(kind="image", asset_id="a", crop=(0.5, 0, 0.4, 1))
    with pytest.raises(ValidationError, match="only image layers"):
        Layer(kind="text", text="x", crop=(0, 0, 1, 1))


def test_composition_beat_rules():
    img = {"kind": "image", "asset_id": "a"}
    VisualBeat(**BEAT, asset_ids=["a"], layers=[img, {"kind": "text", "text": "Epicurus"}])
    VisualBeat(**BEAT, layers=[{"kind": "text", "text": "A text-only card needs no assets"}])
    with pytest.raises(ValidationError, match="exactly the assets"):
        VisualBeat(**BEAT, asset_ids=["a", "b"], layers=[img])
    with pytest.raises(ValidationError, match="move per layer"):
        VisualBeat(**BEAT, asset_ids=["a"], layers=[img], motion="slow_push", motion_purpose="pacing")


# --- pure builders -----------------------------------------------------------------

def test_masks():
    assert mask_expr("none") is None
    assert "min(W,H)*0.2000" in mask_expr("feather", 0.2)
    oval = mask_expr("oval")
    assert "pow((X-W/2)/(W/2),2)" in oval and mask_expr("circle") == oval


def test_text_svg_highlight_label_and_escaping():
    quote = TimelineLayer(kind="text", text="Pleasure & wisdom are one", highlight="wisdom are",
                          text_style="quote", width=0.9)
    svg = text_svg(quote, PROFILE)
    assert 'font-style="italic"' in svg and "&amp;" in svg
    assert f'fill="{ACCENT}">wisdom ' in svg and f'fill="{ACCENT}">are ' in svg and f'fill="{INK}">one' in svg
    label = text_svg(TimelineLayer(kind="text", text="Epicurus", text_style="label"), PROFILE)
    assert "EPICURUS" in label and "letter-spacing" in label


def test_heading_style_is_large_and_upright():
    heading = text_svg(TimelineLayer(kind="text", text="+1.35", text_style="heading"), PROFILE)
    caption = text_svg(TimelineLayer(kind="text", text="+1.35", text_style="caption"), PROFILE)
    size = lambda svg: int(svg.split('font-size="')[1].split('"')[0])
    assert size(heading) > 1.5 * size(caption) and "italic" not in heading and ">+1.35<" in heading


def test_image_prepare_crops_fits_and_masks():
    layer = TimelineLayer(kind="image", asset_id="a", path="/x.jpg", width=0.5, max_height=0.5, zoom_to=1.2,
                          edge="circle", crop=(0.1, 0, 0.9, 0.8))
    cmd = image_prepare_command("ffmpeg", "/x.jpg", layer, PROFILE, "out.png")
    chain = cmd[cmd.index("-vf") + 1]
    assert chain.index("crop=iw*0.8000:ih*0.8000:iw*0.1000") < chain.index("crop='min(iw,ih)'")
    assert "scale=192:108" in chain and "geq=" in chain  # prepared at the largest zoom (1.2)


def test_composition_command_animates_each_layer():
    layers = [TimelineLayer(kind="image", asset_id="a", path="/a.png", zoom_from=1.0, zoom_to=1.1, drift_x=0.05),
              TimelineLayer(kind="text", text="Hi", start=2, end=6, fade_in=1, fade_out=1)]
    cmd = composition_command("ffmpeg", layers, ["l1.png", "l2.png"], PROFILE, 8.0, "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert cmd.count("-loop") == 2 and "-an" in cmd and "color=c=0x0b0b0d:s=320x180" in " ".join(cmd)
    assert "eval=frame" in graph.split("[l1]")[0]                     # zooming layer rescales per frame
    assert "fade=t=in:st=2:d=1:alpha=1" in graph and "fade=t=out:st=5:d=1:alpha=1" in graph
    assert "enable='between(t,2,6)'" in graph and graph.count("overlay=") == 2


# --- end to end --------------------------------------------------------------------

def make_composition(demo):
    def mutate(d):
        d["beats"] = [b for b in d["beats"] if b["scene_id"] != "s01-cold-open"]
        d["beats"].append({
            "beat_id": "v01-comp", "scene_id": "s01-cold-open", "order": 1, "takeaway": "Layered test",
            "visual_type": "original_graphic", "graphic_kind": "title",
            "asset_ids": ["s01-title", "s02-claim-ledger"],
            "layers": [
                {"kind": "image", "asset_id": "s01-title", "x": 0.3, "width": 0.4, "edge": "feather",
                 "zoom_to": 1.05, "fade_in": 0.3, "fade_out": 0.3},
                {"kind": "image", "asset_id": "s02-claim-ledger", "x": 0.72, "width": 0.3, "edge": "oval",
                 "start": 0.2, "fade_in": 0.3, "fade_out": 0.3},
                {"kind": "text", "text": "A quote, with emphasis", "highlight": "emphasis", "text_style": "quote",
                 "y": 0.85, "width": 0.8, "start": 0.4, "fade_in": 0.3, "fade_out": 0.3}]})
    edit_json(demo / "visuals.json", mutate)


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_composition_renders_and_counts_every_layer_for_rights(short_demo, tools):  # noqa: F811
    make_composition(short_demo)
    result = validate_project(short_demo, verify_checksums=True)
    assert result.ok, result.errors
    assert {"s01-title", "s02-claim-ledger"} <= set(extra_used_ids(result.manifest, result.visuals))
    out = render(result, tools, "preview")
    info = probe_video(tools, out.output)
    assert info.duration_seconds == pytest.approx(6.0, abs=0.3)
    clips = list((short_demo / "renders/preview/build/s01-cold-open").glob("comp-v01-comp-*.mp4"))
    assert len(clips) == 1 and probe_video(tools, clips[0]).duration_seconds == pytest.approx(1.5, abs=0.1)
    roles = [i["role"] for i in json.loads(out.report_path.read_text())["inputs"]]
    assert roles.count("visual:layer") == 2
    seg = next(s for s in out.plan.scenes[0].segments)
    assert seg.kind == "composition" and len(seg.layers) == 3

    # Changing one layer re-renders only that scene, under a new clip name.
    again = render(validate_project(short_demo, verify_checksums=True), tools, "preview")
    assert again.rendered == []
    edit_json(short_demo / "visuals.json",
              lambda d: next(b for b in d["beats"] if b["beat_id"] == "v01-comp")["layers"][2].update(y=0.8))
    third = render(validate_project(short_demo, verify_checksums=True), tools, "preview")
    assert third.rendered == ["s01-cold-open"]
    assert len(list((short_demo / "renders/preview/build/s01-cold-open").glob("comp-v01-comp-*.mp4"))) == 2


def test_unknown_layer_asset_fails_validation(short_demo):  # noqa: F811
    make_composition(short_demo)
    edit_json(short_demo / "visuals.json", lambda d: next(b for b in d["beats"] if b["beat_id"] == "v01-comp")
              .update(asset_ids=["s01-title", "nope"]) or next(
                  b for b in d["beats"] if b["beat_id"] == "v01-comp")["layers"][1].update(asset_id="nope"))
    result = validate_project(short_demo)
    assert "ref.missing_asset" in [i.code for i in result.errors]  # validation catches it first


# --- shapes, statements, slide-ins, draw-on lines ----------------------------------

def test_shape_layer_rules():
    Layer(kind="shape", shape="arrow", reveal="draw", flip=True, motion_start=1, motion_end=2, motion_ease=True)
    with pytest.raises(ValidationError, match="need a shape"):
        Layer(kind="shape")
    with pytest.raises(ValidationError, match="no asset_id or text"):
        Layer(kind="shape", shape="ring", text="x")
    with pytest.raises(ValidationError, match="only for shape layers"):
        Layer(kind="text", text="x", shape="ring")
    with pytest.raises(ValidationError, match="'draw' is for line and arrow"):
        Layer(kind="shape", shape="circle", reveal="draw")
    with pytest.raises(ValidationError, match="'words' is for text"):
        Layer(kind="shape", shape="line", reveal="words")
    with pytest.raises(ValidationError, match="motion_end must be after"):
        Layer(kind="text", text="x", motion_start=3, motion_end=2)


def test_shape_svgs():
    from reckoning_pipeline.render.compose import PAPER, shape_svg
    ring = shape_svg(TimelineLayer(kind="shape", shape="ring", width=0.2, max_height=0.3, color="ink"), PROFILE)
    assert 'fill="none"' in ring and f'stroke="{INK}"' in ring
    circle = shape_svg(TimelineLayer(kind="shape", shape="circle", width=0.2, max_height=0.3, color="stone"), PROFILE)
    assert 'fill="#6f675b"' in circle
    arrow = shape_svg(TimelineLayer(kind="shape", shape="arrow", width=0.3, max_height=0.05, flip=True), PROFILE)
    assert "<path" in arrow and "scale(-1,1)" in arrow
    person = shape_svg(TimelineLayer(kind="shape", shape="person", width=0.1, max_height=0.4), PROFILE)
    assert f'fill="{PAPER}"' in person and 'viewBox="0 0 100 260"' in person


def test_statement_style_is_upright_and_draw_wipes_in():
    st = text_svg(TimelineLayer(kind="text", text="Hard work wins.", text_style="statement", highlight="wins."), PROFILE)
    assert "italic" not in st and f'fill="{ACCENT}">wins.' in st
    line = TimelineLayer(kind="shape", shape="line", path="", reveal="draw", start=1, fade_in=2, width=0.3, max_height=0.02)
    back = line.model_copy(update={"flip": True})
    graph = composition_command("ffmpeg", [line, back], ["l.png", "b.png"], PROFILE, 4.0, "o.mp4")
    graph = graph[graph.index("-filter_complex") + 1]
    assert "lte(X,W*clip((T-1)/2,0,1))" in graph and "gte(X,W*(1-clip((T-1)/2,0,1)))" in graph
    assert "fade=t=in" not in graph.split("[l1]")[0]          # drawing replaces the fade-in


def test_slide_in_uses_its_own_eased_window():
    layer = TimelineLayer(kind="shape", shape="person", path="", start=0, drift_x=-0.2,
                          motion_start=2, motion_end=3, motion_ease=True)
    graph = composition_command("ffmpeg", [layer], ["p.png"], PROFILE, 6.0, "o.mp4")
    assert "clip((t-2)/1,0,1)" in graph[graph.index("-filter_complex") + 1]


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_shapes_render_through_the_compositor(short_demo, tools):  # noqa: F811
    def mutate(d):
        d["beats"] = [b for b in d["beats"] if b["scene_id"] != "s01-cold-open"]
        d["beats"].append({**BEAT, "beat_id": "v01-shapes", "scene_id": "s01-cold-open", "visual_type": "typography",
                           "layers": [
                               {"kind": "shape", "shape": "circle", "color": "stone", "x": 0.3, "width": 0.2, "max_height": 0.3},
                               {"kind": "shape", "shape": "ring", "x": 0.7, "width": 0.2, "max_height": 0.3,
                                "drift_x": -0.1, "motion_start": 0.2, "motion_end": 0.8, "motion_ease": True},
                               {"kind": "shape", "shape": "arrow", "reveal": "draw", "y": 0.8, "width": 0.4,
                                "max_height": 0.06, "fade_in": 0.5},
                               {"kind": "shape", "shape": "person", "x": 0.1, "width": 0.08, "max_height": 0.4},
                               {"kind": "text", "text": "you", "text_style": "statement", "y": 0.2}]})
    edit_json(short_demo / "visuals.json", mutate)
    result = validate_project(short_demo, verify_checksums=True)
    assert result.ok, result.errors
    out = render(result, tools, "preview")
    clips = list((short_demo / "renders/preview/build/s01-cold-open").glob("comp-v01-shapes-*.mp4"))
    assert len(clips) == 1 and probe_video(tools, out.output).duration_seconds > 0


# --- dissolves and entrances ---------------------------------------------------------

def test_scene_command_dissolves_between_segments():
    from reckoning_pipeline.render.commands import scene_command
    from reckoning_pipeline.schemas.timeline import TimelineScene, TimelineSegment
    segs = [TimelineSegment(beat_id="a", kind="image", path="/a.png", sha256=None, start=0, duration=3, overlap=0.7),
            TimelineSegment(beat_id="b", kind="image", path="/b.png", sha256=None, start=3, duration=2, overlap=0.5),
            TimelineSegment(beat_id="c", kind="image", path="/c.png", sha256=None, start=5, duration=2)]
    scene = TimelineScene(scene_id="s1", order=1, start=0, duration=7, segments=segs, lead_in=0, fade_in=0, fade_out=0,
                          fingerprint="0" * 64)
    cmd = scene_command("ffmpeg", scene, PROFILE, "o.mp4", label_files={}, captions_file=None)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.700:offset=3.000" in graph
    assert "xfade=transition=fade:duration=0.500:offset=5.000" in graph
    assert "trim=duration=3.700" in graph and "-t" in cmd and "3.700" in cmd   # the first shot runs into the next


def test_entrances_fill_only_unset_motion():
    from reckoning_pipeline.timeline.compiler import IMAGE_PUSH, RISE, _entered
    text = _entered(TimelineLayer(kind="text", text="Hi", y=0.5, start=2))
    assert text.y == pytest.approx(0.5 + RISE) and text.drift_y == -RISE and (text.motion_start, text.motion_ease) == (2, True)
    drifting = TimelineLayer(kind="text", text="Hi", drift_y=-0.006)
    assert _entered(drifting) == drifting                                      # the author's motion wins
    shape = _entered(TimelineLayer(kind="shape", shape="ring", path=""))
    assert shape.zoom_from < 1.0 == shape.zoom_to
    still = _entered(TimelineLayer(kind="image", asset_id="a", path="/a.png"))
    assert still.zoom_to == IMAGE_PUSH and still.motion_ease                    # never a dead-still picture
    slide = _entered(TimelineLayer(kind="image", asset_id="a", path="/a.png", x=0.6, enter="slide_left"))
    assert slide.x > 0.6 and slide.drift_x < 0
    assert _entered(TimelineLayer(kind="text", text="x", enter="none")).drift_y == 0
