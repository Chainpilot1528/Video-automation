"""Deterministic original graphics (SVG, 1920x1080).

Same spec + same sources = byte-identical file, so checksums stay valid.
Charts always start at zero and print their source citation in the frame.
Type sizes are chosen to stay legible on a phone (body text >= 34 px at 1080p).
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from ..research.bibliography import format_citation
from ..schemas import ResearchLedger
from ..schemas.visual import GraphicSpec

W, H = 1920, 1080
MARGIN = 160
BG, FG, MUTED, ACCENT, LINE = "#14161a", "#f2efe8", "#9a968d", "#e0a33a", "#3a3d44"
FONT = "Helvetica, Arial, sans-serif"
CHAR_WIDTH = 0.55  # average glyph width as a fraction of font size (Helvetica)


class GraphicError(ValueError):
    """The spec cannot be rendered honestly."""


def wrap(text: str, size: int, max_width: float) -> list[str]:
    limit = max(int(max_width / (size * CHAR_WIDTH)), 1)
    lines, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > limit:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    return lines + ([current] if current else [])


def _text(x: float, y: float, s: str, size: int, fill: str = FG, weight: int = 400, anchor: str = "start") -> str:
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>\n')


def _svg(body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
            f'<rect width="{W}" height="{H}" fill="{BG}"/>\n{body}</svg>\n')


def _header(spec: GraphicSpec) -> tuple[str, float]:
    body, y = "", 170
    for line in wrap(spec.title, 64, W - 2 * MARGIN)[:2]:
        body += _text(MARGIN, y, line, 64, FG, 700)
        y += 76
    if spec.subtitle:
        body += _text(MARGIN, y, spec.subtitle, 38, MUTED)
        y += 50
    return body, y + 30


def _footer(spec: GraphicSpec, ledger: ResearchLedger) -> str:
    sources = {s.source_id: s for s in ledger.sources}
    missing = [sid for sid in spec.source_ids if sid not in sources]
    if missing:
        raise GraphicError(f"spec cites sources not in the ledger: {missing}")
    if not spec.source_ids:
        return ""
    cited = "; ".join(format_citation(sources[sid]) for sid in spec.source_ids)
    text = f"Source: {cited}" + (f" ({spec.data_locator})" if spec.data_locator else "")
    lines = wrap(text, 28, W - 2 * MARGIN)
    if len(lines) > 2:
        lines = lines[:2]
        lines[-1] = lines[-1][: max(len(lines[-1]) - 1, 0)] + "…"
    y0 = H - 60 - 36 * (len(lines) - 1)
    return "".join(_text(MARGIN, y0 + i * 36, line, 28, MUTED) for i, line in enumerate(lines))


def _fmt(value: float, units: str) -> str:
    number = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{number}{units}" if units in ("%", "×") else (f"{number} {units}" if units else number)


def render_title(spec: GraphicSpec) -> str:
    body = ""
    lines = wrap(spec.title, 120, W - 2 * MARGIN)[:3]
    y = H / 2 - (len(lines) - 1) * 70
    for line in lines:
        body += _text(W / 2, y, line, 120, FG, 700, "middle")
        y += 140
    body += f'<line x1="{W/2 - 200:.0f}" y1="{y - 60:.0f}" x2="{W/2 + 200:.0f}" y2="{y - 60:.0f}" stroke="{ACCENT}" stroke-width="6"/>\n'
    if spec.subtitle:
        body += _text(W / 2, y + 20, spec.subtitle, 44, MUTED, 400, "middle")
    return _svg(body)


def render_bar_chart(spec: GraphicSpec, ledger: ResearchLedger) -> str:
    header, top = _header(spec)
    bottom = H - 170
    n = len(spec.bars)
    label_w = 520
    x0, x1 = MARGIN + label_w, W - MARGIN - 220
    row = (bottom - top) / n
    bar_h = min(row * 0.62, 110)
    peak = max(b.value for b in spec.bars) or 1.0
    body = header
    body += f'<line x1="{x0}" y1="{top - 10:.0f}" x2="{x0}" y2="{bottom:.0f}" stroke="{LINE}" stroke-width="4"/>\n'
    for i, b in enumerate(spec.bars):
        cy = top + row * (i + 0.5)
        width = (x1 - x0) * b.value / peak  # zero-based scale: bar length is proportional to value
        label = wrap(b.label, 38, label_w - 30)[:2]
        for j, line in enumerate(label):
            body += _text(x0 - 30, cy + 13 - (len(label) - 1) * 22 + j * 44, line, 38, FG, 400, "end")
        body += (f'<rect x="{x0}" y="{cy - bar_h / 2:.1f}" width="{width:.1f}" height="{bar_h:.1f}" '
                 f'fill="{ACCENT}" rx="6"/>\n')
        body += _text(x0 + width + 24, cy + 14, _fmt(b.value, spec.units), 40, FG, 700)
    return _svg(body + _footer(spec, ledger))


def render_timeline(spec: GraphicSpec, ledger: ResearchLedger) -> str:
    header, top = _header(spec)
    axis_y = (top + H - 160) / 2 + 20
    n = len(spec.events)
    step = (W - 2 * MARGIN) / n
    body = header + (f'<line x1="{MARGIN}" y1="{axis_y:.0f}" x2="{W - MARGIN}" y2="{axis_y:.0f}" '
                     f'stroke="{LINE}" stroke-width="6"/>\n')
    for i, e in enumerate(spec.events):
        cx = MARGIN + step * (i + 0.5)
        above = i % 2 == 0
        body += f'<circle cx="{cx:.0f}" cy="{axis_y:.0f}" r="16" fill="{ACCENT}"/>\n'
        # Same-side neighbours are two steps apart; stay inside the 80 px safe edge.
        max_w = min(step * 1.7, 2 * (cx - 80), 2 * (W - 80 - cx))
        lines = wrap(e.text, 34, max_w)[:3]
        if above:
            y = axis_y - 60 - 44 * len(lines)
            body += _text(cx, y, e.when, 44, ACCENT, 700, "middle")
            for j, line in enumerate(lines):
                body += _text(cx, y + 50 + j * 42, line, 34, FG, 400, "middle")
        else:
            y = axis_y + 90
            body += _text(cx, y, e.when, 44, ACCENT, 700, "middle")
            for j, line in enumerate(lines):
                body += _text(cx, y + 50 + j * 42, line, 34, FG, 400, "middle")
    return _svg(body + _footer(spec, ledger))


def render_spec(spec: GraphicSpec, ledger: ResearchLedger) -> str:
    if spec.kind == "chapter_map":
        from .chapter_map import render_chapter_map
        return render_chapter_map(spec)
    if spec.kind == "title":
        return render_title(spec)
    if spec.kind == "bar_chart":
        return render_bar_chart(spec, ledger)
    return render_timeline(spec, ledger)
