"""Filesystem helpers: root containment, atomic writes, checksums."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class UnsafePathError(ValueError):
    """A path resolves outside the root it must stay inside."""


def safe_resolve(root: Path, relative: str) -> Path:
    """Resolve ``relative`` under ``root`` (following symlinks) and refuse escapes."""
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise UnsafePathError(f"{relative!r} resolves outside {root_resolved}")
    return candidate


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temporary sibling file, then rename into place."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_json_atomic(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
