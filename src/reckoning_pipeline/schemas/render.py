"""Render report: written to ``reports/`` after each render (Phase 7)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import SCHEMA_VERSION, AwareDatetime, Identifier, Record, Sha256, Slug
from .project import OutputProfileName


class RenderOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class RenderInput(Record):
    path: str
    sha256: Sha256
    role: str = ""  # e.g. narration, visual, music, captions
    scene_id: Identifier | None = None


class RenderOutput(Record):
    path: str
    sha256: Sha256
    size_bytes: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    video_codec: str = ""
    audio_codec: str = ""


class RenderReport(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_id: Slug
    profile: OutputProfileName
    status: RenderOutcome
    started_at: AwareDatetime
    finished_at: AwareDatetime
    pipeline_version: str
    ffmpeg_version: str = ""
    commands: list[list[str]] = Field(default_factory=list)
    settings: dict[str, str | int | float | bool] = Field(default_factory=dict)
    inputs: list[RenderInput] = Field(default_factory=list)
    output: RenderOutput | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
