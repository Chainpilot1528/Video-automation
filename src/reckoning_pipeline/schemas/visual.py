"""Visual plan (``visuals.json``) and graphic specs.

Every narration beat gets a visual chosen down a decision hierarchy:
primary evidence, then original explanatory graphics, then licensed
stock/archive, then generated illustration, then restrained typography.
It is a hierarchy, not a quota: the plan records the choice and the report
questions choices that skip better options for precise claims.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .common import SCHEMA_VERSION, Identifier, NonEmptyStr, Record, no_duplicates


class VisualType(StrEnum):
    PRIMARY_EVIDENCE = "primary_evidence"      # documents, original data, artifacts, real footage
    ORIGINAL_GRAPHIC = "original_graphic"      # our diagrams, charts, timelines, maps, screens
    LICENSED_STOCK = "licensed_stock"          # licensed stock/archive for context and atmosphere
    GENERATED = "generated"                    # conceptual illustration or otherwise unavailable shots
    TYPOGRAPHY = "typography"                  # restrained on-screen text


HIERARCHY_RANK = {t: i for i, t in enumerate(VisualType, 1)}


class GraphicKind(StrEnum):
    TITLE = "title"
    DIAGRAM = "diagram"
    CHART = "chart"
    TIMELINE = "timeline"
    MAP = "map"
    SCREEN = "screen"


DATA_KINDS = frozenset({GraphicKind.CHART, GraphicKind.TIMELINE, GraphicKind.MAP})


class Motion(StrEnum):
    NONE = "none"
    SLOW_PUSH = "slow_push"
    PAN = "pan"
    REVEAL = "reveal"
    HIGHLIGHT = "highlight"
    BUILD = "build"


class BeatReview(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class GenerationRequest(Record):
    """A request for a generated visual, linked to its beat and scene."""

    prompt: NonEmptyStr
    negative_prompt: str = ""
    provider: str = ""            # empty until a provider is chosen and approved
    settings: dict[str, Any] = Field(default_factory=dict)
    status: Literal["requested", "generated", "rejected"] = "requested"


class VisualBeat(Record):
    beat_id: Identifier
    scene_id: Identifier
    order: int = Field(ge=1)                     # position within the scene
    takeaway: NonEmptyStr                        # what the viewer should understand from this visual
    visual_question: str = ""                    # the question this visual answers
    visual_type: VisualType
    graphic_kind: GraphicKind | None = None      # for original graphics
    asset_ids: list[Identifier] = Field(default_factory=list)   # empty = unresolved
    source_ids: list[Identifier] = Field(default_factory=list)
    claim_ids: list[Identifier] = Field(default_factory=list)
    requirements: str = ""                       # what is needed while unresolved
    on_screen_text: list[str] = Field(default_factory=list)
    motion: Motion = Motion.NONE
    motion_purpose: str = ""                     # clarify, reveal evidence, guide attention, or pacing
    offset_seconds: float | None = Field(default=None, ge=0)    # from scene start
    duration_seconds: float | None = Field(default=None, gt=0)
    is_reconstruction: bool = False              # depicts a real event without being genuine footage
    label: str = ""                              # on-screen label, e.g. "Reconstruction" / "AI illustration"
    generation: GenerationRequest | None = None
    review_status: BeatReview = BeatReview.PENDING
    notes: str = ""

    @field_validator("asset_ids", "source_ids", "claim_ids")
    @classmethod
    def _unique(cls, value: list, info) -> list:
        return no_duplicates(value, info.field_name)

    @model_validator(mode="after")
    def _rules(self) -> "VisualBeat":
        t = self.visual_type
        if t is VisualType.ORIGINAL_GRAPHIC and self.graphic_kind is None:
            raise ValueError("original graphics must set graphic_kind")
        if t is not VisualType.ORIGINAL_GRAPHIC and self.graphic_kind is not None:
            raise ValueError("graphic_kind is only for original_graphic beats")
        if t is VisualType.PRIMARY_EVIDENCE and not (self.source_ids or self.claim_ids):
            raise ValueError("primary evidence must reference the source_ids or claim_ids it shows")
        if self.graphic_kind in DATA_KINDS and not self.source_ids:
            raise ValueError(f"a {self.graphic_kind} shows data, so it must cite source_ids (never invent data)")
        if t is VisualType.GENERATED:
            if self.generation is None and not self.asset_ids:
                raise ValueError("generated visuals need a generation request or a generated asset")
            if not self.label.strip():
                raise ValueError("generated visuals must carry an on-screen label, e.g. 'AI illustration'")
        if self.generation is not None and t is not VisualType.GENERATED:
            raise ValueError("generation requests are only for generated beats")
        if self.is_reconstruction and not self.label.strip():
            raise ValueError("reconstructions must be labelled on screen (label), never passed off as genuine")
        if self.motion is not Motion.NONE and not self.motion_purpose.strip():
            raise ValueError("motion needs a motion_purpose: clarify, reveal evidence, guide attention, or pacing")
        if not self.asset_ids and not self.requirements.strip():
            raise ValueError("unresolved beats (no asset_ids) must state their requirements")
        return self


class VisualPlan(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    beats: list[VisualBeat] = Field(default_factory=list)


# --- deterministic graphic specs ---------------------------------------------

class BarDatum(Record):
    label: NonEmptyStr
    value: float = Field(ge=0)  # bars start at zero; negative values need a different chart


class TimelineEvent(Record):
    when: NonEmptyStr       # as displayed, e.g. "1998" or "Mar 2007"
    text: NonEmptyStr


class GraphicSpec(Record):
    """Input for ``pipeline graphics render``. Data must cite ledger sources."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    asset_id: Identifier
    kind: Literal["title", "bar_chart", "timeline"]
    title: NonEmptyStr
    subtitle: str = ""
    source_ids: list[Identifier] = Field(default_factory=list)
    data_locator: str = ""            # where in the source the numbers come from (table, page)
    units: str = ""
    bars: list[BarDatum] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)
    intended_scene_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rules(self) -> "GraphicSpec":
        if self.kind in ("bar_chart", "timeline") and not self.source_ids:
            raise ValueError(f"a {self.kind} must cite source_ids")
        if self.kind == "bar_chart":
            if not 1 <= len(self.bars) <= 8:
                raise ValueError("a bar chart needs 1-8 bars (more is unreadable on a phone)")
            if not self.data_locator:
                raise ValueError("bar charts must record data_locator (table/page the numbers come from)")
        if self.kind == "timeline" and not 2 <= len(self.events) <= 6:
            raise ValueError("a timeline needs 2-6 events")
        if self.kind == "title" and (self.bars or self.events):
            raise ValueError("title cards take no data")
        return self
