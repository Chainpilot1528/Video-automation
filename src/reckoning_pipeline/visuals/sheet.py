"""HTML contact sheet: one page to review every scene's narration and visuals.

Self-contained (inline CSS, no network). Images are linked relative to the
report, so open it from the project's ``reports/`` folder. All project text
is HTML-escaped.
"""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from ..project.validate import ValidationResult
from ..schemas.asset import AssetRoot
from ..utils.fs import safe_resolve, write_text_atomic
from .placeholders import PLACEHOLDER_DIR
from .report import VisualReport

SHEET_FILE = "reports/visuals.html"
IMAGE_EXT = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}

CSS = """
:root{--bg:#f7f5f0;--card:#fff;--fg:#1d1d1b;--muted:#6b675f;--line:#e2ded5;--accent:#b97a12;
--ok:#2e7d4f;--warn:#a86400;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1d2026;--fg:#f2efe8;--muted:#9a968d;
--line:#33373f;--accent:#e0a33a;--ok:#6cc58f;--warn:#e0a33a;--bad:#ef6b62}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:0}.muted{color:var(--muted)}.gaps{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:12px 16px;margin:18px 0}.gaps li{margin:2px 0}
.scene{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}
.narr{margin:8px 0 12px;font-style:italic}.beats{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.beat{border:1px solid var(--line);border-radius:10px;overflow:hidden}.thumb{aspect-ratio:16/9;background:#000;
display:flex;align-items:center;justify-content:center}.thumb img,.thumb video{width:100%;height:100%;object-fit:contain}
.ph{width:100%;height:100%;border:3px dashed var(--bad);color:var(--bad);display:flex;align-items:center;
justify-content:center;text-align:center;padding:12px;font-weight:600;background:transparent}
.meta{padding:10px 12px}.badge{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;
border:1px solid currentColor;margin:0 4px 4px 0}.approved{color:var(--ok)}.pending_review,.pending,.changes_requested{color:var(--warn)}
.blocked,.stale,.missing,.unresolved{color:var(--bad)}.k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
ul{padding-left:18px;margin:4px 0}
"""


def _rel(from_dir: Path, target: Path) -> str:
    return Path(os.path.relpath(target, from_dir)).as_posix()


def build_sheet(result: ValidationResult, report: VisualReport, *, media_root: Path | None = None) -> str:
    project_dir = result.project_dir
    out_dir = safe_resolve(project_dir, SHEET_FILE).parent
    assets = {a.asset_id: a for a in result.registry.assets}
    summaries = {b.beat_id: b for b in report.beats}
    beats_by_scene: dict[str, list] = {}
    for b in (result.visuals.beats if result.visuals else []):
        beats_by_scene.setdefault(b.scene_id, []).append(b)

    def thumb(beat) -> str:
        if not beat.asset_ids:
            ph = safe_resolve(project_dir, f"{PLACEHOLDER_DIR}/{beat.beat_id}.svg")
            if ph.exists():
                return f'<img src="{escape(_rel(out_dir, ph))}" alt="placeholder">'
            return f'<div class="ph">UNRESOLVED<br>{escape(beat.requirements)}</div>'
        a = assets.get(beat.asset_ids[0])
        if a is None:
            return '<div class="ph">MISSING ASSET</div>'
        base = media_root if a.root is AssetRoot.MEDIA and media_root else project_dir
        path = (base / a.path).resolve()
        src = path.as_uri() if a.root is AssetRoot.MEDIA else _rel(out_dir, path)
        ext = path.suffix.lower()
        if ext in IMAGE_EXT:
            return f'<img src="{escape(src)}" alt="{escape(a.asset_id)}" loading="lazy">'
        if ext in VIDEO_EXT:
            return f'<video src="{escape(src)}" controls preload="metadata"></video>'
        return f'<div class="ph">{escape(a.type)}: {escape(a.path)}</div>'

    gap_items = "".join(f"<li><b>{escape(f.subject)}</b>: {escape(f.message)}</li>" for f in report.gaps)
    warn_items = "".join(f"<li><b>{escape(f.subject)}</b>: {escape(f.message)}</li>"
                         for f in report.findings if f.severity == "warning" and f not in report.gaps)
    parts = [f"<!doctype html><html lang=\"{escape(result.manifest.language)}\"><head><meta charset=\"utf-8\">"
             f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
             f"<title>Visuals: {escape(result.manifest.title)}</title><style>{CSS}</style></head><body><main>",
             f"<h1>{escape(result.manifest.title)}</h1><div class=\"muted\">Visual plan contact sheet · "
             f"{len(report.beats)} beats · {len(report.gaps)} gap(s)</div>",
             f"<section class=\"gaps\"><b>Gaps</b><ul>{gap_items or '<li>None</li>'}</ul>"
             f"<b>Warnings</b><ul>{warn_items or '<li>None</li>'}</ul></section>"]

    for s in sorted(result.scenes.scenes, key=lambda s: s.order):
        parts.append(f'<section class="scene"><h2>{s.order}. {escape(s.scene_id)}</h2>'
                     f'<div class="muted">{escape(s.purpose)}</div>'
                     f'<p class="narr">{escape(s.narration_text) or "(no narration)"}</p>'
                     f'<div class="k">Visual strategy</div><div>{escape(s.visual_strategy) or "—"}</div><br>'
                     '<div class="beats">')
        for b in sorted(beats_by_scene.get(s.scene_id, []), key=lambda b: b.order):
            summ = summaries[b.beat_id]
            res = "resolved" if summ.resolved else "unresolved"
            badges = (f'<span class="badge {res}">{res}</span>'
                      f'<span class="badge {escape(summ.rights)}">rights: {escape(summ.rights)}</span>'
                      f'<span class="badge {escape(summ.review_status)}">review: {escape(summ.review_status)}</span>')
            label = f'<div><b>Label:</b> {escape(b.label)}</div>' if b.label else ""
            text = "".join(f"<li>{escape(t)}</li>" for t in b.on_screen_text)
            refs = ", ".join(escape(x) for x in [*b.claim_ids, *b.source_ids]) or "—"
            parts.append(
                f'<article class="beat"><div class="thumb">{thumb(b)}</div><div class="meta">{badges}'
                f'<div><b>{escape(b.beat_id)}</b> · {escape(b.visual_type.value)}'
                f'{" / " + escape(b.graphic_kind.value) if b.graphic_kind else ""}</div>'
                f'<div><b>Takeaway:</b> {escape(b.takeaway)}</div>{label}'
                f'<div><b>Motion:</b> {escape(b.motion.value)}{" (" + escape(b.motion_purpose) + ")" if b.motion_purpose else ""}</div>'
                f'<div><b>Evidence:</b> {refs}</div>'
                f'{"<div><b>On screen:</b><ul>" + text + "</ul></div>" if text else ""}</div></article>')
        if not beats_by_scene.get(s.scene_id):
            parts.append('<div class="ph" style="aspect-ratio:16/9">NO VISUAL PLAN FOR THIS SCENE</div>')
        parts.append("</div></section>")
    parts.append("</main></body></html>\n")
    return "".join(parts)


def write_sheet(result: ValidationResult, report: VisualReport, *, media_root: Path | None = None) -> Path:
    out = safe_resolve(result.project_dir, SHEET_FILE)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(out, build_sheet(result, report, media_root=media_root))
    return out
