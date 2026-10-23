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
import random
from html import escape
from pathlib import Path

from ..schemas.timeline import RenderProfile, TimelineLayer, layers_key  # noqa: F401  (re-exported)
from .commands import fps_arg

CANVAS = "0x0b0b0d"            # near-black, a touch warm
INK = "#ece6da"                # parchment white for text
ACCENT = "#b3261e"             # muted red for highlighted words
DIM = "#9b9488"                # citations and small captions
SERIF = "'Cormorant Garamond', Georgia, 'Times New Roman', serif"
FONT_DIR = Path(__file__).resolve().parent / "fonts"   # Cormorant Garamond, SIL Open Font License (OFL.txt)
SYSTEM_FONT_CONFS = ("/opt/local/etc/fonts/fonts.conf", "/opt/homebrew/etc/fonts/fonts.conf",
                     "/usr/local/etc/fonts/fonts.conf", "/etc/fonts/fonts.conf")
PHRASE_WORDS = 4               # a word reveal steps through phrases of at most this many words
PHRASE_FADE = 0.45             # each phrase fades in over this long
_PHRASE_END = (",", ".", ";", ":", "!", "?", "—", "–", "…", "”")
FEATHER = 0.09                 # feathered edge, as a fraction of the layer's shorter side
OVAL_SOFTNESS = 0.05           # softness of oval/circle edges, in normalized radius
RING = "#a8946a"               # medallion ring: muted brass
RING_RADIUS = 0.965            # ring centre line, as a fraction of the oval's radius
RING_WIDTH = 0.012             # ring thickness, same units
RING_INNER = 0.925             # the portrait fades out just inside the ring, leaving a dark gap
CHAR_WIDTH = {"quote": 0.42, "label": 0.82, "caption": 0.46, "heading": 0.46, "statement": 0.44}  # average advance / font size (Cormorant)
SIZE = {"quote": 1 / 19, "label": 1 / 38, "caption": 1 / 30, "heading": 1 / 12, "statement": 1 / 21}  # font size as a fraction of frame height
LINE = {"quote": 1.45, "label": 1.3, "caption": 1.35, "heading": 1.2, "statement": 1.4}


def _even(v: float) -> int:
    return max(int(v) // 2 * 2, 2)


def box_px(layer: TimelineLayer, profile: RenderProfile) -> tuple[int, int]:
    """The layer's box in pixels at its largest zoom."""
    z = max(layer.zoom_from, layer.zoom_to)
    return _even(profile.width * layer.width * z), _even(profile.height * layer.max_height * z)


# --- stage 1: prepare each layer as a transparent PNG -------------------------------

def mask_expr(edge: str, feather: float = FEATHER) -> str | None:
    """Alpha expression for geq (X, Y, W, H are the image's pixel coords and size), 0..255.

    It multiplies the image's own alpha, so a cut-out keeps its shape inside the mask.
    """
    if edge == "feather":
        f = f"(min(W,H)*{feather:.4f})"
        d = "min(min(X,W-1-X),min(Y,H-1-Y))"
        return f"alpha(X,Y)*pow(clip({d}/{f},0,1),1.5)"
    if edge in ("oval", "circle"):
        r = "(pow((X-W/2)/(W/2),2)+pow((Y-H/2)/(H/2),2))"
        return f"alpha(X,Y)*clip((1-{r})/{_oval_softness(feather):.4f},0,1)"
    return None


def _oval_softness(feather: float) -> float:
    return max(feather * OVAL_SOFTNESS / FEATHER, 0.005)


def ring_exprs(feather: float = FEATHER) -> dict[str, str]:
    """geq expressions (r, g, b, a) for a medallion: the portrait inside RING_INNER of the oval,
    then a thin anti-aliased ring at RING_RADIUS, transparent beyond."""
    q = "sqrt(pow((X-W/2)/(W/2),2)+pow((Y-H/2)/(H/2),2))"
    half = f"max({RING_WIDTH / 2:.4f},1.2/min(W,H))"          # at least ~1 px each side of the centre line
    ring = f"clip(({half}-abs({q}-{RING_RADIUS:.4f}))*min(W,H)/2+0.5,0,1)"   # 1 px anti-aliasing
    photo = f"clip(({RING_INNER:.4f}-{q})/{_oval_softness(feather) / 2:.4f},0,1)"
    red, green, blue = (int(RING[i:i + 2], 16) for i in (1, 3, 5))
    return {"r": f"{red}*{ring}+r(X,Y)*(1-{ring})", "g": f"{green}*{ring}+g(X,Y)*(1-{ring})",
            "b": f"{blue}*{ring}+b(X,Y)*(1-{ring})", "a": f"max(alpha(X,Y)*{photo},255*{ring})"}


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
    if layer.ring:
        e = ring_exprs(layer.feather)
        chain.append(f"geq=r='{e['r']}':g='{e['g']}':b='{e['b']}':a='{e['a']}'")
    elif alpha := mask_expr(layer.edge, layer.feather):
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


def font_env(work: Path) -> dict[str, str]:
    """Environment that lets the SVG renderer see the bundled fonts, without installing them system-wide."""
    base = next((c for c in SYSTEM_FONT_CONFS if Path(c).is_file()), None)
    include = f'<include ignore_missing="yes">{base}</include>' if base else ""
    conf = work / "fonts.conf"
    conf.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
                    f"<fontconfig>{include}<dir>{escape(str(FONT_DIR))}</dir>"
                    f"<cachedir>{escape(str(work / '.fontcache'))}</cachedir></fontconfig>\n", encoding="utf-8")
    return {"FONTCONFIG_FILE": str(conf), "PANGOCAIRO_BACKEND": "fc"}


def expand_reveals(layers: list[TimelineLayer]) -> list[TimelineLayer]:
    """Turn each word-reveal layer into phrase steps. Each step draws only its own words, but in the
    full quote's layout and on the full layer's motion clock, so the phrases line up exactly."""
    out: list[TimelineLayer] = []
    for layer in layers:
        words = layer.text.split()
        if layer.kind != "text" or layer.reveal != "words" or len(layer.word_times) != len(words) or not words:
            out.append(layer)
            continue
        groups: list[list[int]] = [[]]
        for i, word in enumerate(words):
            groups[-1].append(i)
            if len(groups[-1]) >= PHRASE_WORDS or word.endswith(_PHRASE_END):
                groups.append([])
        groups = [g for g in groups if g]
        end = layer.end
        for g in groups:
            start = layer.word_times[g[0]]
            if end is not None:
                start = min(start, end - 0.1)
            out.append(layer.model_copy(update={
                "visible_words": g, "start": round(start, 3), "fade_in": PHRASE_FADE,
                "motion_start": layer.motion_start if layer.motion_start is not None else layer.start,
                "motion_end": layer.motion_end if layer.motion_end is not None else layer.end, "word_times": []}))
    return out


def text_svg(layer: TimelineLayer, profile: RenderProfile) -> str:
    """Transparent SVG for a text layer. Labels are set in letter-spaced capitals (a small-caps look).
    With ``visible_words``, the other words are laid out but transparent, so positions never shift."""
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
    visible = set(layer.visible_words) if layer.visible_words is not None else None
    index = 0
    for n, line in enumerate(lines):
        spans = []
        for k, (word, hl) in enumerate(line):
            fill = ACCENT if hl else base_fill
            hidden = ' fill-opacity="0"' if visible is not None and index not in visible else ""
            spans.append(f'<tspan fill="{fill}"{hidden}>{escape(word)}{" " if k < len(line) - 1 else ""}</tspan>')
            index += 1
        y = size * 1.05 + n * line_h
        rows.append(f'<text x="{bw / 2:.1f}" y="{y:.1f}" text-anchor="middle" font-family="{SERIF}" '
                    f'font-size="{size}"{italic}{spacing} xml:space="preserve">{"".join(spans)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw}" height="{bh}" viewBox="0 0 {bw} {bh}">\n'
            + "\n".join(rows) + "\n</svg>\n")


SHAPE_FILL = {"ink": INK, "dim": DIM, "accent": ACCENT, "stone": "#6f675b"}
PAPER = "#e4d9c3"              # the paper-cutout figures


def shape_svg(layer: TimelineLayer, profile: RenderProfile) -> str:
    """Transparent SVG for a shape layer, drawn to fill its box (width x max_height of the frame)."""
    z = max(layer.zoom_from, layer.zoom_to)
    bw, bh = _even(profile.width * layer.width * z), _even(profile.height * layer.max_height * z)
    colour = SHAPE_FILL[layer.color]
    stroke = max(round(min(bw, bh) * 0.02), 2) if layer.shape == "ring" else max(round(profile.height * 0.003 * z), 2)
    if layer.shape == "circle":
        r = min(bw, bh) / 2 - 1
        body = f'<circle cx="{bw / 2:.1f}" cy="{bh / 2:.1f}" r="{r:.1f}" fill="{colour}"/>'
    elif layer.shape == "ring":
        r = min(bw, bh) / 2 - stroke
        body = f'<circle cx="{bw / 2:.1f}" cy="{bh / 2:.1f}" r="{r:.1f}" fill="none" stroke="{colour}" stroke-width="{stroke}"/>'
    elif layer.shape in ("line", "arrow"):
        y = bh / 2
        head = min(bh / 2, stroke * 5) if layer.shape == "arrow" else 0
        body = f'<line x1="0" y1="{y:.1f}" x2="{bw - head * 0.6:.1f}" y2="{y:.1f}" stroke="{colour}" stroke-width="{stroke}"/>'
        if head:
            body += (f'<path d="M{bw - head * 1.4:.1f},{y - head:.1f} L{bw - 1:.1f},{y:.1f} L{bw - head * 1.4:.1f},{y + head:.1f}" '
                     f'fill="none" stroke="{colour}" stroke-width="{stroke}" stroke-linejoin="round" stroke-linecap="round"/>')
    elif layer.shape == "glow":  # a soft radial light
        glow = {"accent": "#ff6a2e", "ink": "#f3e6c8", "dim": DIM, "stone": "#a8946a"}[layer.color]
        body = (f'<defs><radialGradient id="g"><stop offset="0" stop-color="{glow}" stop-opacity="0.75"/>'
                f'<stop offset="0.45" stop-color="{glow}" stop-opacity="0.28"/>'
                f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient></defs>'
                f'<ellipse cx="{bw / 2:.1f}" cy="{bh / 2:.1f}" rx="{bw / 2:.1f}" ry="{bh / 2:.1f}" fill="url(#g)"/>')
    elif layer.shape == "stars":  # a seeded field of small stars
        rng = random.Random(layer.seed)
        dots = []
        for _ in range(int(bw * bh / 9000)):
            r = rng.choice((0.7, 0.9, 1.1, 1.5)) * max(profile.height / 1080, 0.5) * 1.4
            dots.append(f'<circle cx="{rng.uniform(0, bw):.1f}" cy="{rng.uniform(0, bh):.1f}" r="{r:.2f}" '
                        f'fill="#efe9dc" opacity="{rng.uniform(0.35, 0.95):.2f}"/>')
        body = "".join(dots)
    else:  # person: a flat paper-cutout figure, standing
        colour = PAPER if layer.color == "ink" else colour
        body = (f'<svg x="0" y="0" width="{bw}" height="{bh}" viewBox="0 0 100 260" preserveAspectRatio="xMidYMid meet">'
                f'<circle cx="50" cy="27" r="17" fill="{colour}"/>'
                f'<path d="M31,52 Q50,44 69,52 Q76,56 77,66 L82,134 Q82,140 76,140 L71,82 L68,148 L68,252 Q68,258 61,258 '
                f'L55,258 L52,160 L48,160 L45,258 L39,258 Q32,258 32,252 L32,148 L29,82 L24,140 Q18,140 18,134 '
                f'L23,66 Q24,56 31,52 Z" fill="{colour}"/></svg>')
    if layer.flip:
        body = f'<g transform="translate({bw},0) scale(-1,1)">{body}</g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw}" height="{bh}" viewBox="0 0 {bw} {bh}">\n'
            f"{body}\n</svg>\n")


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
        # Drift and zoom follow the parent layer's clock (phrase steps of a reveal share it).
        m_start = min(layer.motion_start if layer.motion_start is not None else start, duration)
        m_end = min(layer.motion_end if layer.motion_end is not None else end, duration)
        m_life = max(m_end - m_start, 0.04)
        zmax = max(layer.zoom_from, layer.zoom_to)
        p = f"clip((t-{_num(m_start)})/{_num(m_life)},0,1)"
        if layer.motion_ease:
            p = f"({p})*({p})*(3-2*({p}))"
        z = f"({_num(layer.zoom_from)}+({_num(layer.zoom_to - layer.zoom_from)})*{p})/{_num(zmax)}"
        chain = f"[{i}:v]format=rgba"
        if layer.zoom_from != layer.zoom_to:
            chain += f",scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame"
        elif zmax != 1:
            chain += f",scale=w='trunc(iw/{_num(zmax)}/2)*2':h='trunc(ih/{_num(zmax)}/2)*2'"
        fin = min(layer.fade_in, life / 2)
        fout = min(layer.fade_out, life / 2)
        if layer.reveal == "draw":  # a line drawing itself on: an alpha wipe over the fade-in time
            wipe = f"clip((T-{_num(start)})/{_num(max(layer.fade_in, 0.3))},0,1)"
            edge = f"gte(X,W*(1-{wipe}))" if layer.flip else f"lte(X,W*{wipe})"
            chain += f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*{edge}'"
            fin = 0
        if layer.pulse > 0:  # breathe: alpha between 55% and 100% on a slow sine
            phase = (layer.seed % 628) / 100
            chain += (f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                      f"a='alpha(X,Y)*(0.775+0.225*sin(2*PI*T/{_num(layer.pulse)}+{phase:.2f}))'")
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
