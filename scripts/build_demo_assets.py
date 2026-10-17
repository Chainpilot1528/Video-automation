"""Generate the demo project's original SVG graphics and refresh their checksums.

Deterministic: the same code always produces byte-identical files, so the
recorded sha256 values stay valid. Run from the repo root:

    .venv/bin/python scripts/build_demo_assets.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

PROJECT = Path(__file__).resolve().parent.parent / "examples" / "demo-project"
W, H = 1920, 1080
BG, FG, MUTED, ACCENT, LINE = "#14161a", "#f2efe8", "#9a968d", "#e0a33a", "#3a3d44"
FONT = "Helvetica, Arial, sans-serif"


def svg(body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
        f'<rect width="{W}" height="{H}" fill="{BG}"/>\n{body}</svg>\n'
    )


def text(x: int, y: int, s: str, size: int, fill: str = FG, weight: int = 400, anchor: str = "start") -> str:
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>\n')


def box(x: int, y: int, w: int, h: int, stroke: str = LINE) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="none" stroke="{stroke}" stroke-width="4"/>\n'


def arrow(x1: int, y: int, x2: int) -> str:
    return (f'<line x1="{x1}" y1="{y}" x2="{x2 - 24}" y2="{y}" stroke="{ACCENT}" stroke-width="6"/>\n'
            f'<polygon points="{x2},{y} {x2 - 30},{y - 16} {x2 - 30},{y + 16}" fill="{ACCENT}"/>\n')


def title_card() -> str:
    return svg(
        text(W // 2, 470, "ANATOMY OF A", 64, MUTED, 400, "middle")
        + text(W // 2, 600, "Traceable Scene", 140, FG, 700, "middle")
        + f'<line x1="760" y1="680" x2="1160" y2="680" stroke="{ACCENT}" stroke-width="6"/>\n'
        + text(W // 2, 770, "Demo project · original graphics · example data", 40, MUTED, 400, "middle")
    )


def claim_ledger() -> str:
    body = text(160, 200, "A claim is tracked separately from its source", 64, FG, 700)
    stages = [("Claim", "what we say"), ("Source", "where it comes from"), ("Review", "a named person checks")]
    for i, (name, sub) in enumerate(stages):
        x = 160 + i * 560
        body += box(x, 420, 440, 260, ACCENT if i == 2 else LINE)
        body += text(x + 220, 540, name, 72, FG, 700, "middle")
        body += text(x + 220, 610, sub, 36, MUTED, 400, "middle")
        if i < 2:
            body += arrow(x + 450, 550, x + 550)
    body += text(160, 860, "Status starts as  unverified  until a human records a review.", 44, MUTED)
    return svg(body)


def asset_record() -> str:
    rows = [("asset_id", "s03-asset-record"), ("creator", "Reckoning Self"),
            ("license", "Original work"), ("commercial use", "allowed"),
            ("sha256", "64 hex characters, checked before every render")]
    body = text(160, 200, "Every asset carries its paperwork", 64, FG, 700)
    body += box(160, 290, 1600, 620)
    for i, (k, v) in enumerate(rows):
        y = 400 + i * 110
        body += text(220, y, k, 44, MUTED)
        body += text(720, y, v, 44, ACCENT if k == "sha256" else FG, 700 if k == "sha256" else 400)
    return svg(body)


def review_gates() -> str:
    gates = ["Script", "Visuals", "Final export", "Publish"]
    body = text(160, 200, "People approve. Nothing publishes itself.", 64, FG, 700)
    for i, g in enumerate(gates):
        x = 160 + i * 420
        body += box(x, 440, 340, 200, ACCENT)
        body += text(x + 170, 555, g, 52, FG, 700, "middle")
        if i < len(gates) - 1:
            body += arrow(x + 345, 540, x + 415)
    body += text(160, 820, "Each gate is a recorded human decision.", 44, MUTED)
    return svg(body)


GRAPHICS = {
    "assets/graphics/s01_title.svg": title_card,
    "assets/graphics/s02_claim_ledger.svg": claim_ledger,
    "assets/graphics/s03_asset_record.svg": asset_record,
    "assets/graphics/s04_review_gates.svg": review_gates,
}


def main() -> None:
    checksums = {}
    for rel, build in GRAPHICS.items():
        path = PROJECT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = build().encode("utf-8")
        path.write_bytes(data)
        checksums[rel] = hashlib.sha256(data).hexdigest()
        print(f"{checksums[rel]}  {rel}")

    registry_path = PROJECT / "assets" / "registry.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for asset in registry["assets"]:
            if asset["path"] in checksums:
                asset["sha256"] = checksums[asset["path"]]
        registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated checksums in {registry_path.relative_to(PROJECT.parent.parent)}")


if __name__ == "__main__":
    main()
