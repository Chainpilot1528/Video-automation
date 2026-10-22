"""Background removal and medallions: cut-out derivatives, alpha-preserving masks, the ring."""

import subprocess

import pytest
from pydantic import ValidationError
from test_narration import HAVE_FFMPEG, tools  # noqa: F401

from reckoning_pipeline.assets import cutout
from reckoning_pipeline.assets.intake import apply_intake, plan_intake
from reckoning_pipeline.config import load_config
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.render.compose import RING, image_prepare_command, mask_expr, ring_exprs
from reckoning_pipeline.schemas.timeline import RenderProfile, TimelineLayer
from reckoning_pipeline.schemas.visual import Layer

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

PROFILE = RenderProfile(name="preview", width=320, height=180, fps=30, video_preset="ultrafast", crf=32,
                        audio_bitrate="96k", audio_sample_rate=48000, allow_placeholders=True,
                        require_narration=False)


def disc_predictor(rgb):
    """A stand-in for U²-Net: the foreground is a disc in the middle of the image."""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    return (((xx - w / 2) ** 2 + (yy - h / 2) ** 2) < (min(w, h) / 4) ** 2).astype(np.float32)


def photo(path, w=200, h=120):
    img = np.full((h, w, 3), (90, 40, 20), np.uint8)
    cv2.circle(img, (w // 2, h // 2), min(w, h) // 4, (220, 220, 220), -1)
    cv2.imwrite(str(path), img)
    return path


def test_cut_out_removes_background_and_trims(tmp_path):
    w, h = cutout.cut_out(photo(tmp_path / "bust.jpg"), tmp_path / "cut.png", disc_predictor)
    out = cv2.imread(str(tmp_path / "cut.png"), cv2.IMREAD_UNCHANGED)
    assert out.shape == (h, w, 4) and 60 <= w <= 66 and 60 <= h <= 66   # disc diameter 60 + small margin
    assert out[0, 0, 3] == 0 and out[h // 2, w // 2, 3] == 255
    full = cutout.cut_out(tmp_path / "bust.jpg", tmp_path / "full.png", disc_predictor, trim=False)
    assert full == (200, 120)


def test_cut_out_refuses_an_empty_mask(tmp_path):
    with pytest.raises(cutout.CutoutError, match="no foreground"):
        cutout.cut_out(photo(tmp_path / "x.jpg"), tmp_path / "o.png", lambda rgb: np.zeros(rgb.shape[:2]))


def test_model_is_checksummed(tmp_path):
    with pytest.raises(cutout.CutoutError, match="model not found.*curl"):
        cutout.check_model(tmp_path / "u2net.onnx")
    (tmp_path / "u2net.onnx").write_bytes(b"not a model")
    with pytest.raises(cutout.CutoutError, match="checksum"):
        cutout.check_model(tmp_path / "u2net.onnx")
    assert load_config({"PIPELINE_MODELS_DIR": "/m"}).models_dir.as_posix() == "/m"


def test_cli_cutout_registers_a_derivative(runner_env, demo, monkeypatch):
    runner, app, cli = runner_env
    monkeypatch.setattr(cli, "u2net_predictor", lambda path: disc_predictor)
    result = validate_project(demo)
    plan = plan_intake(demo, result.registry, photo(demo / "bust.jpg"), {
        "asset_id": "bust", "type": "image", "creation_method": "user_supplied", "license_name": "CC0 1.0",
        "commercial_use": "allowed", "derivatives_allowed": True})
    apply_intake(demo, result.manifest, result.registry, plan)
    parent = plan.asset
    r = runner.invoke(app, ["archive", "cutout", str(demo), parent.asset_id, "--id", "bust-cut"])
    assert r.exit_code == 0, r.output
    a = next(x for x in validate_project(demo).registry.assets if x.asset_id == "bust-cut")
    assert a.derived_from == parent.asset_id and a.path.endswith("bust-cut.png")
    assert a.license_name == parent.license_name and a.publication_status == "pending_review"
    assert "U²-Net" in a.notes and "Check the edges" in a.notes
    r = runner.invoke(app, ["archive", "cutout", str(demo), "no-such-asset", "--id", "x"])
    assert r.exit_code == cli.EXIT_FAILED and "not an image asset" in r.output


@pytest.mark.skipif(not cutout.model_path(load_config().models_dir).is_file(), reason="U²-Net model not downloaded")
def test_real_model_finds_the_disc(tmp_path):
    predict = cutout.u2net_predictor(cutout.model_path(load_config().models_dir))
    mask = predict(cv2.cvtColor(cv2.imread(str(photo(tmp_path / "p.jpg", 320, 320))), cv2.COLOR_BGR2RGB))
    assert mask[160, 160] > 0.5 and mask[5, 5] < 0.5


# --- compositor --------------------------------------------------------------------

def test_ring_rules_and_masks_keep_cutout_alpha():
    Layer(kind="image", asset_id="a", edge="oval", ring=True)
    with pytest.raises(ValidationError, match="ring is for"):
        Layer(kind="image", asset_id="a", edge="feather", ring=True)
    with pytest.raises(ValidationError, match="ring is for"):
        Layer(kind="text", text="x", ring=True)
    assert mask_expr("feather").startswith("alpha(X,Y)*") and mask_expr("oval").startswith("alpha(X,Y)*")
    assert "max(alpha(X,Y)*" in ring_exprs()["a"]


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_medallion_ring_and_cutout_render(tmp_path, tools):  # noqa: F811
    src = photo(tmp_path / "p.jpg", 400, 400)
    medal = TimelineLayer(kind="image", asset_id="a", path=str(src), width=0.5, max_height=1.0, edge="circle",
                          ring=True)
    subprocess.run(image_prepare_command(tools.ffmpeg, str(src), medal, PROFILE, str(tmp_path / "m.png")), check=True)
    m = cv2.imread(str(tmp_path / "m.png"), cv2.IMREAD_UNCHANGED)
    s = m.shape[0]
    ring_px = m[s // 2, round(s / 2 * (1 + 0.965))]                       # on the ring, right of centre
    assert ring_px[3] > 200 and tuple(ring_px[2::-1]) == pytest.approx(
        tuple(int(RING[i:i + 2], 16) for i in (1, 3, 5)), abs=25)
    assert m[s // 2, round(s / 2 * (1 + 0.945)), 3] < 60                  # the dark gap
    assert m[s // 2, s // 2, 3] == 255 and m[0, 0, 3] == 0               # portrait inside, clear outside

    cutout.cut_out(src, tmp_path / "cut.png", disc_predictor, trim=False)
    feathered = TimelineLayer(kind="image", asset_id="a", path="x", width=0.5, max_height=1.0, edge="feather")
    subprocess.run(image_prepare_command(tools.ffmpeg, str(tmp_path / "cut.png"), feathered, PROFILE,
                                         str(tmp_path / "f.png")), check=True)
    f = cv2.imread(str(tmp_path / "f.png"), cv2.IMREAD_UNCHANGED)
    h, w = f.shape[:2]
    assert f[h // 2, w // 2, 3] == 255 and f[h // 2, int(w * 0.15), 3] == 0   # the cut-out's background stays gone
