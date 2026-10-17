"""Shared types for all manifest schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
MAX_SLUG_LEN = 64
ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=MAX_SLUG_LEN)]
Identifier = Annotated[str, StringConstraints(pattern=ID_PATTERN)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _check_rel_path(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("path must be a non-empty string")
    if "\\" in value:
        raise ValueError("use forward slashes in paths")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("~"):
        raise ValueError("path must be relative to its root folder, not absolute")
    if ".." in path.parts:
        raise ValueError("path must not contain '..'")
    return value


RelPath = Annotated[str, AfterValidator(_check_rel_path)]


def _require_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone, e.g. 2026-10-17T12:00:00+00:00")
    return value


AwareDatetime = Annotated[datetime, AfterValidator(_require_tz)]


class Record(BaseModel):
    """Base for every schema: unknown fields are errors, never silently dropped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def duplicates(values: list) -> list:
    seen, dupes = set(), []
    for v in values:
        if v in seen and v not in dupes:
            dupes.append(v)
        seen.add(v)
    return dupes


def no_duplicates(values: list, field: str) -> list:
    dupes = duplicates(values)
    if dupes:
        raise ValueError(f"{field} contains duplicates: {dupes}")
    return values


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
