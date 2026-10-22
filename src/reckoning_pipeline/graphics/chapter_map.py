"""The chapter map: monumental stone steps descending into the dark, one step per chapter.

A tall, transparent SVG (1920 wide), drawn like the stepped base of a Greek temple seen from
the front: each level is a stone course with a lit tread on top and a tall face with the
level's number and title cut into it, and room on the right for up to three portrait
medallions. Each step down is wider than the one above and sinks further into the dark.

The geometry is fixed per level, so the timeline can place medallions and pan the camera
from one level to the next without reading the drawing. Same spec = byte-identical file
(the stone texture is seeded from the spec).
"""

from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path
from xml.sax.saxutils import escape

from ..schemas.visual import GraphicSpec

W = 1920
VIEW_H = 1080                  # one frame of the map at 1920 wide
PITCH = 540                    # vertical distance between levels; a one-level pan moves half a frame
TREAD_TOP, TREAD_FRONT = -250, -190   # tread top/front edges, relative to the level's view centre
INSET_BOTTOM = 60              # side margin of the lowest step
INSET_SPREAD = 300             # how much narrower (each side) the top step is than the lowest
MEDALLION_W, MEDALLION_H = 190, 238   # medallion box on the map, in map pixels
SLOTS = 3                      # medallion places per level
SERIF = "'Cormorant Garamond', Georgia, 'Times New Roman', serif"
INK, DIM = "#ece6da", "#a39b8d"
CANVAS = (0x0B, 0x0B, 0x0D)
TREAD = (0x8E, 0x86, 0x79)
FACE_TOP, FACE_BOTTOM = (0x5C, 0x56, 0x4E), (0x2E, 0x2B, 0x28)
MAX_FOG = 0.6                  # the deepest level is mixed this far toward the canvas colour
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def levels_in(path: Path) -> int | None:
    """How many levels a rendered chapter map has (None if the file isn't one)."""
    try:
        with path.open("rb") as fh:
            head = fh.read(600).decode("utf-8", "replace")
    except OSError:
        return None
    m = re.search(r'data-chapter-levels="(\d+)"', head)
    return int(m.group(1)) if m else None


def map_height(levels: int) -> int:
    return VIEW_H + (levels - 1) * PITCH


def view_y(level: int) -> int:
    """Map y of the frame centre when the camera rests on ``level`` (1-based)."""
    return VIEW_H // 2 + (level - 1) * PITCH


def slab_x(level: int, levels: int) -> tuple[int, int]:
    inset = INSET_BOTTOM + round(INSET_SPREAD * (levels - level) / max(levels - 1, 1))
    return inset, W - inset


def marker_anchor(level: int, slot: int, levels: int) -> tuple[int, int]:
    """Centre of medallion ``slot`` (1-based, right to left) on ``level``'s stone face, in map pixels."""
    _, right = slab_x(level, levels)
    x = right - 150 - (slot - 1) * (MEDALLION_W + 46)
    return x, view_y(level) + 40


def _mix(c: tuple[int, int, int], f: float) -> str:
    r, g, b = (round(a + (z - a) * f) for a, z in zip(c, CANVAS))
    return f"#{r:02x}{g:02x}{b:02x}"


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _wrap(text: str, size: int, width: float) -> list[str]:
    limit = max(int(width / (size * 0.42)), 1)
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > limit:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + ([cur] if cur else [])


def _edge(rng: random.Random, x0: float, x1: float, y: float, rough: float) -> list[tuple[float, float]]:
    """A slightly chipped horizontal edge from x0 to x1."""
    pts, x = [], x0
    while x < x1:
        pts.append((x, y + rng.uniform(-rough, rough) * (0.4 if rng.random() < 0.8 else 2.2)))
        x += rng.uniform(26, 70)
    pts.append((x1, y))
    return pts


def _level(spec: GraphicSpec, n: int, level: int, rng: random.Random) -> str:
    lv = spec.levels[level - 1]
    fog = MAX_FOG * (level - 1) / max(n - 1, 1)
    cy = view_y(level)
    left, right = slab_x(level, n)
    t_top, t_front = cy + TREAD_TOP, cy + TREAD_FRONT
    bottom = cy + PITCH + TREAD_TOP          # the next level's tread starts here
    if level == n:
        bottom = map_height(n) - 40
    back = 34                                # tread recedes this far at each side (perspective)
    out = [f'<g id="level-{level}">']

    # Tread: the lit top surface, slightly narrower at the back.
    front = _edge(rng, left, right, t_front, 3)
    tread = [(left + back, t_top), (right - back, t_top), (right, t_front)] + front[::-1][1:]
    out.append(f'<polygon points="{" ".join(f"{_f(x)},{_f(y)}" for x, y in tread)}" fill="url(#tread{level})"/>')
    # Front face with grain, a dark band under the lip, and masonry joints.
    face = front + [(right, bottom), (left, bottom)]
    pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in face)
    out.append(f'<polygon points="{pts}" fill="url(#face{level})"/>')
    out.append(f'<polygon points="{pts}" fill="#000" opacity="0.5" filter="url(#grain)"/>')
    out.append(f'<rect x="{left}" y="{t_front}" width="{right - left}" height="16" fill="#000" opacity="0.35"/>')
    course = t_front + (bottom - t_front) * rng.uniform(0.7, 0.76)   # below the inscription
    tx = left + 110
    titles = _wrap(lv.title, 66, (right - left) * 0.5)[:2]
    subtitles = _wrap(lv.subtitle, 32, (right - left) * 0.5)[:2] if lv.subtitle else []
    text_end = tx + max([len(t) * 66 * 0.42 for t in titles] + [len(t) * 32 * 0.42 for t in subtitles]) + 70
    slots_start = marker_anchor(level, SLOTS, n)[0] - MEDALLION_W / 2 - 30
    joint = _mix((0x1A, 0x18, 0x16), fog)
    light = _mix((0x6E, 0x67, 0x5D), fog)
    out.append(f'<line x1="{left}" y1="{_f(course)}" x2="{right}" y2="{_f(course)}" stroke="{joint}" stroke-width="3"/>')
    out.append(f'<line x1="{left}" y1="{_f(course + 3)}" x2="{right}" y2="{_f(course + 3)}" stroke="{light}" '
               f'stroke-width="1" opacity="0.5"/>')
    for top, bot in ((t_front + 14, course), (course + 3, bottom)):
        x = left + rng.uniform(160, 420)
        while x < right - 120:
            if top < course and x < text_end:   # keep the inscription's stone whole
                x = text_end + rng.uniform(20, 160)
                continue
            out.append(f'<line x1="{_f(x)}" y1="{_f(top)}" x2="{_f(x)}" y2="{_f(bot)}" stroke="{joint}" stroke-width="3"/>')
            x += rng.uniform(380, 620)
    # A hairline crack or two.
    for _ in range(rng.randint(1, 2) if slots_start - text_end > 120 else 0):
        x, y = rng.uniform(text_end + 40, slots_start - 40), t_front + rng.uniform(20, 120)
        path = [f"M{_f(x)},{_f(y)}"]
        for _ in range(rng.randint(4, 7)):
            x += rng.uniform(-28, 28)
            y += rng.uniform(16, 40)
            path.append(f"L{_f(x)},{_f(y)}")
        out.append(f'<path d="{"".join(path)}" fill="none" stroke="{joint}" stroke-width="1.6" opacity="0.8"/>')

    # Depth: everything on this level sinks toward the canvas colour (the inscription less so).
    if fog:
        for poly in (tread, face):
            out.append(f'<polygon points="{" ".join(f"{_f(x)},{_f(y)}" for x, y in poly)}" '
                       f'fill="{_mix(CANVAS, 0)}" opacity="{fog:.2f}"/>')
    out.append(f'<g opacity="{1 - fog * 0.45:.2f}">')
    # The inscription: level number in spaced capitals, title in italics, subtitle dimmed.
    ty = cy - 70
    out.append(f'<text x="{tx}" y="{ty}" font-family="{SERIF}" font-size="30" letter-spacing="7" fill="{DIM}">'
               f'LEVEL {ROMAN[level - 1]}</text>')
    ty += 74
    for line in titles:
        out.append(f'<text x="{tx}" y="{ty}" font-family="{SERIF}" font-size="66" font-style="italic" '
                   f'fill="{INK}">{escape(line)}</text>')
        ty += 74
    for line in subtitles:
        out.append(f'<text x="{tx}" y="{ty - 12}" font-family="{SERIF}" font-size="32" fill="{DIM}">'
                   f'{escape(line)}</text>')
        ty += 40
    out.append(f'<line x1="{tx}" y1="{cy - 118}" x2="{tx + 70}" y2="{cy - 118}" stroke="#b3261e" stroke-width="2"/>')
    out.append("</g></g>")
    return "\n".join(out)


def _defs(n: int) -> str:
    grads = []
    for level in range(1, n + 1):
        fog = 0.0  # depth fog is an overlay per level (see _level), so all levels share one stone colour
        grads.append(f'<linearGradient id="tread{level}" x1="0" y1="0" x2="0" y2="1">'
                     f'<stop offset="0" stop-color="{_mix(TREAD, fog + 0.25)}"/>'
                     f'<stop offset="1" stop-color="{_mix(TREAD, fog)}"/></linearGradient>')
        grads.append(f'<linearGradient id="face{level}" x1="0" y1="0" x2="0" y2="1">'
                     f'<stop offset="0" stop-color="{_mix(FACE_TOP, fog)}"/>'
                     f'<stop offset="1" stop-color="{_mix(FACE_BOTTOM, min(fog + 0.2, 1))}"/></linearGradient>')
    return ("<defs>\n" + "\n".join(grads) + "\n"
            '<filter id="grain" x="0" y="0" width="100%" height="100%">'
            '<feTurbulence type="fractalNoise" baseFrequency="0.05 0.11" numOctaves="3" seed="7"/>'
            '<feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -0.9 0.62"/>'
            '<feComposite in2="SourceGraphic" operator="in"/></filter>\n'
            '<radialGradient id="glow" cx="0.5" cy="0" r="0.75">'
            '<stop offset="0" stop-color="#d9c9a6" stop-opacity="0.22"/>'
            '<stop offset="1" stop-color="#d9c9a6" stop-opacity="0"/></radialGradient>\n'
            "</defs>")


def render_chapter_map(spec: GraphicSpec) -> str:
    n = len(spec.levels)
    h = map_height(n)
    seed = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
    rng = random.Random(seed)
    body = [_defs(n), f'<rect x="0" y="0" width="{W}" height="{VIEW_H}" fill="url(#glow)"/>',
            f'<text x="{W // 2}" y="150" text-anchor="middle" font-family="{SERIF}" font-size="34" '
            f'letter-spacing="9" fill="{DIM}">{escape(spec.title.upper())}</text>']
    if spec.subtitle:
        body.append(f'<text x="{W // 2}" y="200" text-anchor="middle" font-family="{SERIF}" font-size="30" '
                    f'font-style="italic" fill="{DIM}">{escape(spec.subtitle)}</text>')
    # Draw from the bottom up, so each tread's lip overlaps the face below it.
    for level in range(n, 0, -1):
        body.append(_level(spec, n, level, rng))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
            f'data-chapter-levels="{n}">\n' + "\n".join(body) + "\n</svg>\n")
