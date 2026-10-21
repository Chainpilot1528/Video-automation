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
