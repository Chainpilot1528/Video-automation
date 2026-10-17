"""Clearly labelled placeholder frames for unresolved beats.

Placeholders are not assets and are never registered: previews can show
them, and QA (Phase 8) blocks any master render that still contains one.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from ..graphics.svg import FONT, H, W, wrap
from ..schemas.visual import VisualBeat
from ..utils.fs import safe_resolve, write_text_atomic

PLACEHOLDER_DIR = "visuals/placeholders"


def placeholder_svg(beat: VisualBeat) -> str:
    return placeholder_svg_text(f"{beat.scene_id} · {beat.beat_id} · {beat.visual_type.value}", beat.requirements)


def placeholder_svg_text(heading: str, detail: str) -> str:
    lines = wrap(detail, 40, W - 400)[:4]
    body = (f'<rect x="60" y="60" width="{W - 120}" height="{H - 120}" fill="none" stroke="#d9534f" '
            f'stroke-width="8" stroke-dasharray="40 24"/>\n'
            f'<text x="{W // 2}" y="300" font-family="{FONT}" font-size="72" font-weight="700" fill="#d9534f" '
            f'text-anchor="middle">PLACEHOLDER: NOT FOR PUBLICATION</text>\n'
            f'<text x="{W // 2}" y="400" font-family="{FONT}" font-size="44" fill="#f2efe8" '
            f'text-anchor="middle">{escape(heading)}</text>\n')
    for i, line in enumerate(lines):
        body += (f'<text x="{W // 2}" y="{540 + i * 56}" font-family="{FONT}" font-size="40" fill="#9a968d" '
                 f'text-anchor="middle">{escape(line)}</text>\n')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
            f'<rect width="{W}" height="{H}" fill="#1c1416"/>\n{body}</svg>\n')


def write_placeholders(project_dir: Path, beats: list[VisualBeat]) -> list[Path]:
    """Write (or refresh) one placeholder per unresolved beat. These are disposable previews."""
    written = []
    for beat in beats:
        if beat.asset_ids:
            continue
        out = safe_resolve(project_dir, f"{PLACEHOLDER_DIR}/{beat.beat_id}.svg")
        out.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(out, placeholder_svg(beat))
        written.append(out)
    return written
