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


class Layer(Record):
    """One element of a composition: an image or a block of text placed on a dark canvas.

    Positions and sizes are fractions of the frame, so a layout works at any resolution.
    Times are seconds from the start of the beat. Motion is a slow, linear drift and zoom
    over the layer's own lifetime.
    """

    kind: Literal["image", "text"]
    asset_id: Identifier | None = None          # image layers
    text: str = ""                              # text layers
    text_style: Literal["quote", "label", "caption"] = "label"
    highlight: str = ""                         # part of ``text`` drawn in the accent colour
    reveal: Literal["fade", "words"] = "fade"   # "words": appear phrase by phrase as the narrator reads them
    claim_id: Identifier | None = None          # quotes: the ledger quotation claim this text reproduces
    x: float = Field(default=0.5, ge=0, le=1)   # centre of the layer, across the frame
    y: float = Field(default=0.5, ge=0, le=1)   # centre of the layer, down the frame
    width: float = Field(default=0.4, gt=0, le=1.5)    # fraction of frame width
    max_height: float = Field(default=0.8, gt=0, le=1.5)  # images are fitted inside width x max_height
    start: float = Field(default=0.0, ge=0)
    end: float | None = Field(default=None, gt=0)  # None = until the beat ends
    fade_in: float = Field(default=1.2, ge=0, le=10)
    fade_out: float = Field(default=1.2, ge=0, le=10)
    drift_x: float = Field(default=0.0, ge=-0.3, le=0.3)  # total travel, fraction of frame width
    drift_y: float = Field(default=0.0, ge=-0.3, le=0.3)
    zoom_from: float = Field(default=1.0, ge=0.5, le=2.0)
    zoom_to: float = Field(default=1.0, ge=0.5, le=2.0)
    edge: Literal["none", "feather", "oval", "circle"] = "none"
    feather: float = Field(default=0.09, gt=0, le=0.5)  # feathered/oval edge width, fraction of the shorter side
    crop: tuple[float, float, float, float] | None = None  # (left, top, right, bottom) fractions of the source

    @model_validator(mode="after")
    def _rules(self) -> "Layer":
        if self.kind == "image" and not self.asset_id:
            raise ValueError("image layers need an asset_id")
        if self.kind == "text":
            if not self.text.strip():
                raise ValueError("text layers need text")
            if self.asset_id:
                raise ValueError("text layers take no asset_id")
            if self.highlight and self.highlight not in self.text:
                raise ValueError("highlight must be part of the layer's text")
        elif self.reveal != "fade" or self.claim_id:
            raise ValueError("reveal and claim_id are for text layers")
        if self.end is not None and self.end <= self.start:
            raise ValueError("a layer must end after it starts")
        if self.crop is not None:
            left, top, right, bottom = self.crop
            if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
                raise ValueError("crop is (left, top, right, bottom) as fractions with left < right and top < bottom")
            if self.kind != "image":
                raise ValueError("only image layers can be cropped")
        return self


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
    layers: list[Layer] = Field(default_factory=list)   # a composition on a dark canvas instead of one picture
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
        if not self.asset_ids and not self.requirements.strip() and not self.layers:
            raise ValueError("unresolved beats (no asset_ids) must state their requirements")
        if self.layers:
            images = list(dict.fromkeys(layer.asset_id for layer in self.layers if layer.kind == "image"))
            if sorted(images) != sorted(self.asset_ids):
                raise ValueError("a composition's asset_ids must list exactly the assets its image layers use")
            if self.motion is not Motion.NONE:
                raise ValueError("compositions move per layer (drift, zoom); leave the beat's motion as none")
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
