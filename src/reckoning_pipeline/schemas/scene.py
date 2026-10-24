"""Scene manifest: ``scenes.json``.

Duration fields are deliberately separate:

* ``planned_duration_seconds`` — an editorial estimate, never used for timing.
* ``actual_narration_duration_seconds`` — measured from the narration audio.
* ``final_duration_seconds`` — timeline duration after holds and transitions.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .common import SCHEMA_VERSION, Identifier, NonEmptyStr, Record, Sha256, no_duplicates


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class CaptionStatus(StrEnum):
    NONE = "none"
    APPROXIMATE = "approximate"
    WORD_ALIGNED = "word_aligned"
    REVIEWED = "reviewed"


class RenderStatus(StrEnum):
    NOT_STARTED = "not_started"
    STALE = "stale"
    RENDERED = "rendered"
    FAILED = "failed"


class TransitionType(StrEnum):
    CUT = "cut"
    FADE = "fade"
    DISSOLVE = "dissolve"
    FADE_TO_BLACK = "fade_to_black"


class Transition(Record):
    type: TransitionType = TransitionType.CUT
    duration_seconds: float = Field(default=0.0, ge=0, le=5)

    @model_validator(mode="after")
    def _cut_has_no_duration(self) -> "Transition":
        if self.type is TransitionType.CUT and self.duration_seconds:
            raise ValueError("a 'cut' transition must have duration_seconds 0")
        if self.type is not TransitionType.CUT and not self.duration_seconds:
            raise ValueError(f"a '{self.type}' transition needs duration_seconds > 0")
        return self


class Scene(Record):
    scene_id: Identifier
    order: int = Field(ge=1)
    purpose: NonEmptyStr
    narration_text: str = ""
    visual_strategy: str = ""
    asset_ids: list[Identifier] = Field(default_factory=list)
    source_ids: list[Identifier] = Field(default_factory=list)
    claim_ids: list[Identifier] = Field(default_factory=list)
    planned_duration_seconds: float | None = Field(default=None, gt=0)
    actual_narration_duration_seconds: float | None = Field(default=None, ge=0)
    final_duration_seconds: float | None = Field(default=None, ge=0)
    narration_asset_id: Identifier | None = None
    caption_status: CaptionStatus = CaptionStatus.NONE
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    transition_in: Transition = Field(default_factory=Transition)
    transition_out: Transition = Field(default_factory=Transition)
    music_cue: str | None = None
    on_screen_text: list[str] = Field(default_factory=list)
    notes: str = ""
    render_status: RenderStatus = RenderStatus.NOT_STARTED
    input_fingerprint: Sha256 | None = None
    narration_speed: float | None = Field(default=None, ge=0.7, le=1.3)   # multiplies the TTS speed for this scene
    hold_after_seconds: float | None = Field(default=None, ge=0, le=5)    # picture held after narration ends
    lead_in_seconds: float | None = Field(default=None, ge=0, le=10)      # picture before narration starts

    @field_validator("asset_ids", "source_ids", "claim_ids")
    @classmethod
    def _unique(cls, value: list, info) -> list:
        return no_duplicates(value, info.field_name)

    @model_validator(mode="after")
    def _duration_rules(self) -> "Scene":
        if self.actual_narration_duration_seconds is not None and self.narration_asset_id is None:
            raise ValueError(
                "actual_narration_duration_seconds is set but narration_asset_id is not: "
                "actual duration must be measured from a narration audio asset"
            )
        if (self.narration_asset_id is not None and self.final_duration_seconds is not None
                and self.actual_narration_duration_seconds is None):
            raise ValueError(
                "final_duration_seconds is set before the narration was measured; "
                "measure actual_narration_duration_seconds first"
            )
        if self.caption_status is not CaptionStatus.NONE and self.narration_asset_id is None:
            raise ValueError("captions require a narration_asset_id")
        return self


class SceneManifest(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    scenes: list[Scene] = Field(default_factory=list)
