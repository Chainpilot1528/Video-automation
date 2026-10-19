"""Project manifest: ``project.json``."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .common import (
    SCHEMA_VERSION, AwareDatetime, Identifier, NonEmptyStr, Record, RelPath, Slug, no_duplicates, utcnow,
)

ALLOWED_FRAME_RATES = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    IN_RESEARCH = "in_research"
    SCRIPT_APPROVED = "script_approved"
    IN_PRODUCTION = "in_production"
    IN_REVIEW = "in_review"
    PUBLICATION_READY = "publication_ready"
    ARCHIVED = "archived"


class Platform(StrEnum):
    YOUTUBE = "youtube"
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM_REELS = "instagram_reels"
    INSTAGRAM = "instagram"
    SUBSTACK = "substack"


class OutputProfileName(StrEnum):
    PREVIEW = "preview"
    MASTER_16X9 = "master_16x9"
    VERTICAL_9X16 = "vertical_9x16"


class Resolution(Record):
    width: int = Field(ge=16, le=7680)
    height: int = Field(ge=16, le=4320)

    @model_validator(mode="after")
    def _even(self) -> "Resolution":
        if self.width % 2 or self.height % 2:
            raise ValueError("width and height must be even numbers (required by H.264/yuv420p)")
        return self


class ProjectPaths(Record):
    """Locations of the project's other files, relative to the project folder."""

    brief: RelPath = "brief.md"
    research_ledger: RelPath = "research/ledger.json"
    script: RelPath = "script/script.md"
    scenes: RelPath = "scenes.json"
    asset_registry: RelPath = "assets/registry.json"
    approvals: RelPath = "approvals.json"  # optional; absent means no approvals yet
    visual_plan: RelPath = "visuals.json"  # optional; absent means no visual plan yet


class MusicSettings(Record):
    """A music bed under the whole video, ducked under narration."""

    asset_id: Identifier
    gain_db: float = Field(default=-14.0, ge=-40, le=0)  # bed level before ducking
    duck: bool = True                                   # lower the bed while narration plays
    fade_in_seconds: float = Field(default=2.0, ge=0, le=10)
    fade_out_seconds: float = Field(default=3.0, ge=0, le=15)


class ProjectManifest(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_id: Slug
    title: NonEmptyStr
    working_title: str = ""
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")
    target_platforms: list[Platform] = Field(default_factory=lambda: [Platform.YOUTUBE], min_length=1)
    output_profiles: list[OutputProfileName] = Field(
        default_factory=lambda: [OutputProfileName.PREVIEW, OutputProfileName.MASTER_16X9], min_length=1
    )
    frame_rate: float = 30.0
    resolution: Resolution = Field(default_factory=lambda: Resolution(width=1920, height=1080))
    audio_sample_rate: Literal[44100, 48000] = 48000
    paths: ProjectPaths = Field(default_factory=ProjectPaths)
    project_status: ProjectStatus = ProjectStatus.DRAFT
    created_at: AwareDatetime = Field(default_factory=utcnow)
    updated_at: AwareDatetime = Field(default_factory=utcnow)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    music: MusicSettings | None = None

    @field_validator("frame_rate")
    @classmethod
    def _frame_rate(cls, value: float) -> float:
        if not any(abs(value - allowed) < 1e-6 for allowed in ALLOWED_FRAME_RATES):
            raise ValueError(f"frame_rate must be one of {list(ALLOWED_FRAME_RATES)}")
        return value

    @field_validator("target_platforms")
    @classmethod
    def _platforms(cls, value: list) -> list:
        return no_duplicates(value, "target_platforms")

    @field_validator("output_profiles")
    @classmethod
    def _profiles(cls, value: list) -> list:
        return no_duplicates(value, "output_profiles")

    @model_validator(mode="after")
    def _timestamps(self) -> "ProjectManifest":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self
