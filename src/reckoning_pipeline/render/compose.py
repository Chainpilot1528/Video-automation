"""Compositions: layered images and text animated on a dark canvas (the "archival" look).

Two stages, both plain FFmpeg:

1. Each layer is prepared once as a transparent PNG: an image fitted into its box
   and masked (feathered edges, oval or circle), or text drawn from SVG with an
   accent-coloured highlight. Prepared at the layer's largest zoom, so motion only
   ever scales down (no blur).
2. One pass animates every layer over the canvas: per-layer fade in/out (alpha),
   linear drift and zoom over the layer's lifetime. The result is a silent clip
   that the scene renderer uses like any video segment.

Everything here builds argument arrays or SVG text; nothing is interpolated into
a filtergraph except numbers and simple relative file names.
"""

from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path

from ..schemas.timeline import RenderProfile, TimelineLayer, layers_key  # noqa: F401  (re-exported)
from .commands import fps_arg

CANVAS = "0x0b0b0d"            # near-black, a touch warm
INK = "#ece6da"                # parchment white for text
ACCENT = "#b3261e"             # muted red for highlighted words
DIM = "#9b9488"                # citations and small captions
SERIF = "Georgia, 'Times New Roman', serif"
FEATHER = 0.09                 # feathered edge, as a fraction of the layer's shorter side
OVAL_SOFTNESS = 0.05           # softness of oval/circle edges, in normalized radius
CHAR_WIDTH = {"quote": 0.47, "label": 0.62, "caption": 0.5}   # average glyph width / font size
SIZE = {"quote": 1 / 22, "label": 1 / 42, "caption": 1 / 34}  # font size as a fraction of frame height
LINE = {"quote": 1.45, "label": 1.3, "caption": 1.35}


def _even(v: float) -> int:
    return max(int(v) // 2 * 2, 2)


def box_px(layer: TimelineLayer, profile: RenderProfile) -> tuple[int, int]:
    """The layer's box in pixels at its largest zoom."""
    z = max(layer.zoom_from, layer.zoom_to)
    return _even(profile.width * layer.width * z), _even(profile.height * layer.max_height * z)


# --- stage 1: prepare each layer as a transparent PNG -------------------------------

def mask_expr(edge: str, feather: float = FEATHER) -> str | None:
    """Alpha expression for geq (X, Y, W, H are the image's pixel coords and size)."""
    if edge == "feather":
        f = f"(min(W,H)*{feather:.4f})"
        d = "min(min(X,W-1-X),min(Y,H-1-Y))"
        return f"255*pow(clip({d}/{f},0,1),1.5)"
    if edge in ("oval", "circle"):
        r = "(pow((X-W/2)/(W/2),2)+pow((Y-H/2)/(H/2),2))"
        return f"255*clip((1-{r})/{max(feather * OVAL_SOFTNESS / FEATHER, 0.005):.4f},0,1)"
    return None


def image_prepare_command(ffmpeg: str, src: str, layer: TimelineLayer, profile: RenderProfile,
                          out: str) -> list[str]:
    bw, bh = box_px(layer, profile)
    chain = []
    if layer.crop is not None:
        left, top, right, bottom = layer.crop
        chain.append(f"crop=iw*{right - left:.4f}:ih*{bottom - top:.4f}:iw*{left:.4f}:ih*{top:.4f}")
    if layer.edge == "circle":  # centre square crop first
        chain.append("crop='min(iw,ih)':'min(iw,ih)'")
    chain.append(f"scale={bw}:{bh}:force_original_aspect_ratio=decrease:flags=lanczos")
    chain.append("format=rgba")
    alpha = mask_expr(layer.edge, layer.feather)
    if alpha:
        chain.append(f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{alpha}'")
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vf", ",".join(chain),
            "-frames:v", "1", "-update", "1", out]


def _wrap(words: list[tuple[str, bool]], max_chars: int) -> list[list[tuple[str, bool]]]:
    lines: list[list[tuple[str, bool]]] = [[]]
    used = 0
    for word, hl in words:
        extra = len(word) + (1 if lines[-1] else 0)
        if lines[-1] and used + extra > max_chars:
            lines.append([])
            used, extra = 0, len(word)
        lines[-1].append((word, hl))
        used += extra
    return [line for line in lines if line]


def _marked_words(text: str, highlight: str) -> list[tuple[str, bool]]:
    """Words of ``text`` with a flag for those inside the (first) highlighted span."""
    start = text.find(highlight) if highlight else -1
    end = start + len(highlight)
    out, pos = [], 0
    for word in text.split():
        i = text.find(word, pos)
        pos = i + len(word)
        out.append((word, start >= 0 and i < end and pos > start))
    return out


def text_svg(layer: TimelineLayer, profile: RenderProfile) -> str:
    """Transparent SVG for a text layer. Labels are set in letter-spaced capitals (a small-caps look)."""
    style = layer.text_style
    bw = _even(profile.width * layer.width * max(layer.zoom_from, layer.zoom_to))
    size = max(round(profile.height * SIZE[style] * max(layer.zoom_from, layer.zoom_to)), 8)
    text = layer.text.upper() if style == "label" else layer.text
    highlight = layer.highlight.upper() if style == "label" else layer.highlight
    max_chars = max(int(bw / (size * CHAR_WIDTH[style])), 4)
    lines = _wrap(_marked_words(text, highlight), max_chars)
    line_h = size * LINE[style]
    bh = _even(line_h * len(lines) + size * 0.6)
    italic = ' font-style="italic"' if style == "quote" else ""
    spacing = f' letter-spacing="{size * 0.18:.1f}"' if style == "label" else ""
    base_fill = DIM if style == "caption" else INK
    rows = []
    for n, line in enumerate(lines):
        spans = []
        for k, (word, hl) in enumerate(line):
            fill = ACCENT if hl else base_fill
            spans.append(f'<tspan fill="{fill}">{escape(word)}{" " if k < len(line) - 1 else ""}</tspan>')
        y = size * 1.05 + n * line_h
        rows.append(f'<text x="{bw / 2:.1f}" y="{y:.1f}" text-anchor="middle" font-family="{SERIF}" '
                    f'font-size="{size}"{italic}{spacing} xml:space="preserve">{"".join(spans)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw}" height="{bh}" viewBox="0 0 {bw} {bh}">\n'
            + "\n".join(rows) + "\n</svg>\n")


def svg_to_png_command(ffmpeg: str, svg: str, out: str) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", svg, "-vf", "format=rgba",
            "-frames:v", "1", "-update", "1", out]


# --- stage 2: animate the prepared layers on the canvas -----------------------------

def _num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def composition_command(ffmpeg: str, layers: list[TimelineLayer], pngs: list[str], profile: RenderProfile,
                        duration: float, out: str) -> list[str]:
    """Animate prepared layer PNGs over a dark canvas into a silent H.264 clip of ``duration`` seconds."""
    w, h, fps = profile.width, profile.height, fps_arg(profile.fps)
    d = f"{duration:.3f}"
    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "lavfi", "-i", f"color=c={CANVAS}:s={w}x{h}:r={fps}:d={d}"]
    for png in pngs:
        args += ["-loop", "1", "-framerate", fps, "-t", d, "-i", png]
    parts, last = [], "[0:v]"
    for i, layer in enumerate(layers, 1):
        start = min(layer.start, duration)
        end = min(layer.end if layer.end is not None else duration, duration)
        life = max(end - start, 0.04)
        zmax = max(layer.zoom_from, layer.zoom_to)
        p = f"clip((t-{_num(start)})/{_num(life)},0,1)"
        z = f"({_num(layer.zoom_from)}+({_num(layer.zoom_to - layer.zoom_from)})*{p})/{_num(zmax)}"
        chain = f"[{i}:v]format=rgba"
        if layer.zoom_from != layer.zoom_to:
            chain += f",scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame"
        elif zmax != 1:
            chain += f",scale=w='trunc(iw/{_num(zmax)}/2)*2':h='trunc(ih/{_num(zmax)}/2)*2'"
        fin = min(layer.fade_in, life / 2)
        fout = min(layer.fade_out, life / 2)
        if fin > 0:
            chain += f",fade=t=in:st={_num(start)}:d={_num(fin)}:alpha=1"
        if fout > 0:
            chain += f",fade=t=out:st={_num(end - fout)}:d={_num(fout)}:alpha=1"
        parts.append(chain + f"[l{i}]")
        cx = f"({_num(layer.x)}+({_num(layer.drift_x)})*{p})*{w}"
        cy = f"({_num(layer.y)}+({_num(layer.drift_y)})*{p})*{h}"
        target = f"[c{i}]"
        parts.append(f"{last}[l{i}]overlay=x='{cx}-w/2':y='{cy}-h/2':eval=frame:format=auto:"
                     f"enable='between(t,{_num(start)},{_num(end)})'{target}")
        last = target
    parts.append(f"{last}format=yuv420p,trim=duration={d},setpts=PTS-STARTPTS[vout]")
    args += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-an",
             "-c:v", "libx264", "-preset", profile.video_preset, "-crf", str(max(profile.crf - 2, 0)),
             "-pix_fmt", "yuv420p", "-r", fps, "-t", d, out]
    return args


def prepare_layer_files(layers: list[TimelineLayer], profile: RenderProfile,
                        work: Path) -> list[tuple[TimelineLayer, Path]]:
    """Where each layer's prepared PNG goes: named by content and frame size, so a changed layer
    (or profile) never reuses a stale file."""
    out = []
    for layer in layers:
        payload = {"layer": layer.model_dump(mode="json", exclude={"path"}), "size": [profile.width, profile.height]}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        out.append((layer, work / f"layer-{key}.png"))
    return out
