"""Background removal: cut a bust or object out of its museum backdrop.

The cut-out is a transparent PNG trimmed to the object, registered as a *derivative* of the
original (it inherits the original's rights and needs its own review: check the edges).

The model is U²-Net (``u2net.onnx``, Apache-2.0, the file rembg distributes), run through
OpenCV's DNN module. OpenCV is used instead of rembg/onnxruntime because those have no
builds for Intel Macs on current Python. Both are optional: ``pip install -e '.[cutout]'``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

MODEL_FILE = Path("u2net") / "u2net.onnx"
MODEL_SHA256 = "8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
MODEL_NAME = "U²-Net (u2net.onnx, Apache-2.0)"
INPUT_SIZE = 320
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
TRIM_THRESHOLD = 8      # alpha (0-255) below this counts as background when trimming
TRIM_MARGIN = 0.02      # margin kept around the object, as a fraction of its larger side

Predictor = Callable[["object"], "object"]  # RGB uint8 image (H, W, 3) -> mask float32 (H, W) in 0..1


class CutoutError(RuntimeError):
    """Background removal could not run (missing packages or model) or produced nothing."""


def _cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise CutoutError("background removal needs OpenCV and NumPy: pip install -e '.[cutout]'") from exc
    return cv2, np


def model_path(models_dir: Path) -> Path:
    return models_dir / MODEL_FILE


def check_model(path: Path) -> None:
    if not path.is_file():
        raise CutoutError(f"model not found at {path}; download it with: mkdir -p {path.parent} && "
                          f"curl -fL -o {path} {MODEL_URL}  (about 176 MB)")
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != MODEL_SHA256:
        raise CutoutError(f"{path} does not match the expected U²-Net checksum; delete it and download again")


def u2net_predictor(path: Path) -> Predictor:
    """A predictor running the U²-Net model with OpenCV (checksum verified first)."""
    check_model(path)
    cv2, np = _cv()
    net = cv2.dnn.readNetFromONNX(str(path))
    mean, std = np.array(MEAN, np.float32), np.array(STD, np.float32)

    def predict(rgb):
        h, w = rgb.shape[:2]
        x = cv2.resize(rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
        x = (x / max(float(x.max()), 1e-6) - mean) / std
        net.setInput(x.transpose(2, 0, 1)[None])
        m = net.forward()[0, 0]
        m = (m - m.min()) / max(float(m.max() - m.min()), 1e-6)
        return cv2.resize(m, (w, h), interpolation=cv2.INTER_LANCZOS4)

    return predict


def cut_out(src: Path, out: Path, predict: Predictor, *, trim: bool = True) -> tuple[int, int]:
    """Write ``src`` with its background removed to ``out`` (PNG); returns the output size (w, h)."""
    cv2, np = _cv()
    bgr = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if bgr is None:
        raise CutoutError(f"could not read image {src}")
    mask = predict(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    alpha = np.clip(np.asarray(mask, np.float32) * 255.0, 0, 255).astype(np.uint8)
    rgba = np.dstack([bgr, alpha])
    if trim:
        ys, xs = np.nonzero(alpha >= TRIM_THRESHOLD)
        if not len(xs):
            raise CutoutError(f"no foreground object found in {src}")
        h, w = alpha.shape
        pad = int(round(max(xs.max() - xs.min(), ys.max() - ys.min()) * TRIM_MARGIN))
        top, bottom = max(ys.min() - pad, 0), min(ys.max() + pad + 1, h)
        left, right = max(xs.min() - pad, 0), min(xs.max() + pad + 1, w)
        rgba = rgba[top:bottom, left:right]
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), rgba):
        raise CutoutError(f"could not write {out}")
    return rgba.shape[1], rgba.shape[0]
