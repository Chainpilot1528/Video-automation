"""Locate external executables (FFmpeg, ffprobe) without relying on a login PATH.

Apps launched from the Dock, IDEs and some shells don't load ``~/.zprofile``,
so MacPorts/Homebrew directories may be missing from PATH. We fall back to
their standard install locations.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

FALLBACK_DIRS = ("/opt/local/bin", "/usr/local/bin", "/opt/homebrew/bin")


class ToolNotFoundError(RuntimeError):
    """A required executable could not be found."""


def find_tool(configured: str) -> str | None:
    """Resolve a configured tool name or path to an executable path, or None."""
    if os.sep in configured:
        path = Path(configured).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    found = shutil.which(configured)
    if found:
        return found
    for directory in FALLBACK_DIRS:
        candidate = Path(directory) / configured
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def require_tool(configured: str, setting: str) -> str:
    path = find_tool(configured)
    if path is None:
        raise ToolNotFoundError(f"{configured!r} not found; install FFmpeg (docs/INSTALL.md) or set {setting}")
    return path
