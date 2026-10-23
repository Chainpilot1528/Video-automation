"""The chapter map as "the core": a planet cut open, layer by layer down to a glowing centre.

A transparent SVG wider and taller than a frame. Each level is one band of the planet,
from the grey crust (level I) down through warmer layers to the red core (the last
level). The camera rests on a level's band at the vertical axis and eases down to the
next. Every band carries its number and title on the left of the axis and up to three
empty medallion rings on the right, which the timeline fills with portraits.

Same interface as the stone steps (``chapter_map``): ``map_size``, ``view_center``,
``marker_anchor``, ``MEDALLION_W``/``MEDALLION_H`` and ``SLOTS``, so the timeline can
place everything without reading the drawing. Same spec = byte-identical file.
"""

from __future__ import annotations

import hashlib
import math
import random
from xml.sax.saxutils import escape

from ..schemas.visual import GraphicSpec

STYLE = "core"
VIEW_W, VIEW_H = 1920, 1080    # one frame at zoom 1
MAP_W = 3000
SKY = 420                      # sky above the surface at the axis
BAND = 300                     # thickness of one level's layer (also the pan per level)
MEDALLION_W, MEDALLION_H = 150, 188
SLOTS = 3
SERIF = "'Cormorant Garamond', Georgia, 'Times New Roman', serif"
INK, DIM, ACCENT = "#ece6da", "#b5ac9c", "#b3261e"
CRUST, CORE = (128, 120, 108), (182, 58, 32)     # outer layer colour → innermost layer colour
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def _radius(levels: int) -> int:
    return BAND * (levels + 1)          # bands, plus the core itself (one band wide)


def map_size(levels: int) -> tuple[int, int]:
    return MAP_W, SKY + _radius(levels) + 2 * BAND + 120   # room below the core for the deepest view


def _centre(levels: int) -> tuple[float, float]:
    return MAP_W / 2, SKY + _radius(levels)


def _band_mid(level: int, levels: int) -> float:
    """Radius of the middle of ``level``'s band."""
    return _radius(levels) - (level - 0.5) * BAND


def view_center(level: int, levels: int) -> tuple[float, float]:
    """Map point at the frame centre when the camera rests on ``level``."""
    cx, cy = _centre(levels)
    return cx, cy - _band_mid(level, levels) + 40


def _on_band(level: int, levels: int, dx: float) -> tuple[float, float]:
    cx, cy = _centre(levels)
    r = _band_mid(level, levels)
    dx = max(min(dx, r * 0.95), -r * 0.95)
    return cx + dx, cy - math.sqrt(r * r - dx * dx)


def marker_anchor(level: int, slot: int, levels: int) -> tuple[float, float]:
    """Centre of medallion ``slot`` (1-based, from the axis outwards) on ``level``'s band, right of the axis."""
    x, y = _on_band(level, levels, 170 + (slot - 1) * (MEDALLION_W + 50))
    return round(x, 1), round(y, 1)


def core_center(levels: int) -> tuple[float, float]:
    """Map point at the centre of the core (where the glow sits)."""
    return _centre(levels)


CORE_GLOW = 2.4 * BAND        # diameter of the pulsing glow, in map pixels
FIGURE_H = 200                # the paper figure on the surface, in map pixels
PAPER = "#e4d9c3"


def figure_svg(x: float, foot_y: float, height: float) -> str:
    """Our paper-cutout figure with a lantern, standing with its feet at (x, foot_y)."""
    s = height / 260
    return (f'<g transform="translate({x - 50 * s:.1f},{foot_y - 258 * s:.1f}) scale({s:.4f})">'
            f'<circle cx="50" cy="27" r="17" fill="{PAPER}"/>'
            f'<path d="M31,52 Q50,44 69,52 Q76,56 78,70 L88,170 L80,232 L60,232 L58,256 L51,256 L50,232 L48,232 '
            f'L46,256 L39,256 L38,232 L18,232 L26,170 L23,66 Q24,56 31,52 Z" fill="{PAPER}"/>'
            f'<line x1="80" y1="128" x2="92" y2="150" stroke="{PAPER}" stroke-width="3"/>'
            f'<circle cx="94" cy="160" r="9" fill="#f0c66a"/><circle cx="94" cy="160" r="34" fill="#f0c66a" opacity="0.14"/>'
            f'</g>')


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _hex(c: tuple[int, int, int], k: float = 0.0) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v + k))) for v in c)


def render_chapter_core(spec: GraphicSpec) -> str:
    n = len(spec.levels)
    w, h = map_size(n)
    cx, cy = _centre(n)
    rng = random.Random(hashlib.sha256(spec.model_dump_json().encode()).hexdigest())
    out = [f'<defs><radialGradient id="glow"><stop offset="0" stop-color="#ff7a3a" stop-opacity="0.55"/>'
           f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient></defs>']
    # stars wherever the planet isn't
    for _ in range(420):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        if math.hypot(x - cx, y - cy) > _radius(n) + 8:
            out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.choice((0.8, 1, 1.3, 1.8))}" fill="#e8e2d6" '
                       f'opacity="{rng.uniform(.2, .75):.2f}"/>')
    # bands, outermost first, as faceted wedges (each wedge split into triangles around its middle)
    for i in range(n + 1):
        r_out, r_in = _radius(n) - i * BAND, max(_radius(n) - (i + 1) * BAND, 0)
        colour = _mix(CRUST, CORE, i / n)
        step = 5   # the same facet angles in every band, so neighbouring bands meet without seams
        for a0 in range(0, 360, step):
            a1 = a0 + step
            ra, rb = math.radians(a0), math.radians(a1)
            if i == n:   # the core: a fan of triangles
                tri = [(cx, cy), (cx + r_out * math.cos(ra), cy + r_out * math.sin(ra)),
                       (cx + r_out * math.cos(rb), cy + r_out * math.sin(rb))]
                out.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in tri)}" '
                           f'fill="{_hex(colour, rng.uniform(-10, 10))}"/>')
                continue
            mid_r = (r_out + r_in) / 2 + rng.uniform(-BAND * .15, BAND * .15)
            rm = math.radians((a0 + a1) / 2 + rng.uniform(-step * .25, step * .25))
            m = (cx + mid_r * math.cos(rm), cy + mid_r * math.sin(rm))
            ring_pts = [(cx + r_out * math.cos(ra), cy + r_out * math.sin(ra)), (cx + r_out * math.cos(rb), cy + r_out * math.sin(rb)),
                        (cx + r_in * math.cos(rb), cy + r_in * math.sin(rb)), (cx + r_in * math.cos(ra), cy + r_in * math.sin(ra))]
            for j in range(4):
                tri = [ring_pts[j], ring_pts[(j + 1) % 4], m]
                out.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in tri)}" '
                           f'fill="{_hex(colour, rng.uniform(-11, 11))}" stroke="#efe6d6" stroke-opacity="0.08" stroke-width="1"/>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r_out:.0f}" fill="none" stroke="#efe6d6" stroke-opacity="0.18" '
                   f'stroke-width="2"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{BAND * 2.2:.0f}" fill="url(#glow)"/>')
    # the surface line, a little brighter
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{_radius(n)}" fill="none" stroke="#efe6d6" stroke-opacity="0.45" stroke-width="3"/>')
    fx = cx - 300
    out.append(figure_svg(fx, cy - math.sqrt(_radius(n) ** 2 - 300 ** 2) + 4, FIGURE_H))
    # inscriptions (left of the axis) and empty medallion rings (right of it)
    for lv in range(1, n + 1):
        level = spec.levels[lv - 1]
        x, y = _on_band(lv, n, -min(520, 0.5 * _band_mid(lv, n)))   # deep bands curve tightly: stay near the axis
        out.append(f'<text x="{x:.0f}" y="{y - 30:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="24" '
                   f'letter-spacing="6" fill="{DIM}">LEVEL {ROMAN[lv - 1]}</text>')
        out.append(f'<text x="{x:.0f}" y="{y + 22:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="46" '
                   f'font-style="italic" fill="{INK}">{escape(level.title)}</text>')
        if level.subtitle:
            out.append(f'<text x="{x:.0f}" y="{y + 62:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="24" '
                       f'fill="{DIM}">{escape(level.subtitle)}</text>')
        for slot in (1,):   # one waiting place per level; extra medallions bring their own ring
            mx, my = marker_anchor(lv, slot, n)
            out.append(f'<ellipse cx="{mx}" cy="{my}" rx="{MEDALLION_W / 2 - 4}" ry="{MEDALLION_H / 2 - 4}" fill="#0b0b0d" '
                       f'fill-opacity="0.18" stroke="#efe6d6" stroke-opacity="0.35" stroke-width="2"/>')
    # the episode title in the sky
    out.append(f'<text x="{cx}" y="{SKY * 0.42:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="34" '
               f'letter-spacing="10" fill="{DIM}">{escape(spec.title.upper())}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'data-chapter-levels="{n}" data-chapter-style="{STYLE}">\n' + "\n".join(out) + "\n</svg>\n")


OVERVIEW_MARGIN = 60


def overview_scale(levels: int) -> float:
    """Map pixels → overview pixels: the whole dome fits a 1920x1080 frame."""
    return min((VIEW_W - 2 * OVERVIEW_MARGIN) / (2 * _radius(levels)), (VIEW_H - 2.5 * OVERVIEW_MARGIN) / _radius(levels))


def overview_surface(levels: int) -> tuple[float, float]:
    """Overview point at the top of the planet (where the pull-back starts)."""
    k = overview_scale(levels)
    return VIEW_W / 2, VIEW_H - OVERVIEW_MARGIN - _radius(levels) * k


def render_chapter_core_overview(spec: GraphicSpec) -> str:
    """The whole planet in one 1920x1080 frame, for the opening pull-back: the same bands and colours,
    the figure on top, no inscriptions (they'd be too small to read)."""
    n = len(spec.levels)
    k = overview_scale(n)
    cx, cy = VIEW_W / 2, VIEW_H - OVERVIEW_MARGIN
    rng = random.Random(hashlib.sha256((spec.model_dump_json() + "overview").encode()).hexdigest())
    out = [f'<defs><radialGradient id="glow"><stop offset="0" stop-color="#ff7a3a" stop-opacity="0.55"/>'
           f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient>'
           f'<clipPath id="half"><rect x="0" y="0" width="{VIEW_W}" height="{cy:.1f}"/></clipPath></defs>',
           '<g clip-path="url(#half)">']
    for i in range(n + 1):
        r_out = (_radius(n) - i * BAND) * k
        colour = _mix(CRUST, CORE, i / n)
        for a0 in range(180, 360, 5):
            ra, rb = math.radians(a0), math.radians(a0 + 5)
            tri = [(cx, cy), (cx + r_out * math.cos(ra), cy + r_out * math.sin(ra)), (cx + r_out * math.cos(rb), cy + r_out * math.sin(rb))]
            out.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in tri)}" fill="{_hex(colour, rng.uniform(-10, 10))}"/>')
        out.append(f'<circle cx="{cx}" cy="{cy:.1f}" r="{r_out:.1f}" fill="none" stroke="#efe6d6" stroke-opacity="0.22" stroke-width="1.5"/>')
    out.append(f'<circle cx="{cx}" cy="{cy:.1f}" r="{BAND * 2.2 * k:.1f}" fill="url(#glow)"/></g>')
    out.append(f'<line x1="{cx - _radius(n) * k - 40:.1f}" y1="{cy:.1f}" x2="{cx + _radius(n) * k + 40:.1f}" y2="{cy:.1f}" '
               f'stroke="#efe6d6" stroke-opacity="0.3" stroke-width="1.5"/>')
    fx = cx - 300 * k
    out.append(figure_svg(fx, cy - math.sqrt((_radius(n) * k) ** 2 - (300 * k) ** 2) + 2, FIGURE_H * k * 1.6))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{VIEW_W}" height="{VIEW_H}" viewBox="0 0 {VIEW_W} {VIEW_H}" '
            f'data-chapter-levels="{n}" data-chapter-style="core-overview">\n' + "\n".join(out) + "\n</svg>\n")
