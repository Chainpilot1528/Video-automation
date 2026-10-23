"""Chapter-map styles. Each style module offers the same geometry: ``map_size``, ``view_center``,
``marker_anchor``, ``MEDALLION_W``/``MEDALLION_H`` and ``SLOTS``."""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType

from . import chapter_core, chapter_map

STYLES: dict[str, ModuleType] = {"steps": chapter_map, "core": chapter_core}


def map_info(path: Path) -> tuple[ModuleType, int] | None:
    """(style module, level count) of a rendered chapter map, or None if the file isn't one."""
    try:
        with path.open("rb") as fh:
            head = fh.read(800).decode("utf-8", "replace")
    except OSError:
        return None
    levels = re.search(r'data-chapter-levels="(\d+)"', head)
    style = re.search(r'data-chapter-style="(\w+)"', head)
    if not levels:
        return None
    module = STYLES.get(style.group(1) if style else "steps")
    return (module, int(levels.group(1))) if module else None
