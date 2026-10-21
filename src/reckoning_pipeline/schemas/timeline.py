"""Timeline plan: the explicit, render-ready description of a video.

The compiler produces this from validated manifests without running FFmpeg;
the renderer only executes it. Writing it to ``reports/timeline-<profile>.json``
makes every render reviewable before any expensive work happens.

Timing model (no overlaps, so nothing is double-counted):

    scene duration = lead_in + measured narration + tail_hold     (narrated scene)
                   = planned_duration_seconds or DEFAULT_SILENT    (silent scene)

Transitions happen *inside* each scene's own time: a fade-in at its start and
a fade-out at its end. A "dissolve" is rendered as a dip through black of the
same length. Scenes therefore butt-join, and total length = sum of scenes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field

from .common import SCHEMA_VERSION, Identifier, Record, Sha256
from .visual import Layer, Motion

SegmentKind = Literal["image", "video", "placeholder", "composition"]


class RenderProfile(Record):
    name: Literal["preview", "master_16x9"]
    width: int
    height: int
    fps: float
    video_preset: str
    crf: int
    audio_bitrate: str
    audio_sample_rate: int
    allow_placeholders: bool
    require_narration: bool


class TimelineLayer(Layer):
    """A composition layer with its image resolved to a file (text layers have no file)."""

    path: str = ""
    sha256: Sha256 | None = None


def layers_key(layers: list[TimelineLayer]) -> str:
    """Stable digest of a composition's layers (paths excluded, file checksums included)."""
    payload = [layer.model_dump(mode="json", exclude={"path"}) for layer in layers]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class TimelineSegment(Record):
    beat_id: str
    kind: SegmentKind
    path: str               # absolute path at compile time (asset, video, or placeholder to be written)
    sha256: Sha256 | None   # asset checksum; None for placeholders
    placeholder_text: str = ""
    start: float            # relative to the scene start
    duration: float = Field(gt=0)
    motion: Motion = Motion.NONE
    source_duration: float | None = None  # video assets only
    label: str = ""         # on-screen label for reconstructions / AI illustrations
    layers: list[TimelineLayer] = Field(default_factory=list)  # compositions only


class TimelineNarration(Record):
    asset_id: Identifier
    path: str
    sha256: Sha256
    duration: float


class TimelineCue(Record):
    start: float            # relative to the scene start
    end: float
    text: str


class TimelineScene(Record):
    scene_id: Identifier
    order: int
    start: float            # on the final timeline
    duration: float = Field(gt=0)
    lead_in: float
    fade_in: float
    fade_out: float
    narration: TimelineNarration | None = None
    segments: list[TimelineSegment] = Field(default_factory=list)
    cues: list[TimelineCue] = Field(default_factory=list)
    fingerprint: Sha256


class TimelineMusic(Record):
    asset_id: Identifier
    path: str
    sha256: Sha256
    gain_db: float
    duck: bool
    fade_in: float
    fade_out: float


class TimelinePlan(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_id: str
    profile: RenderProfile
    burn_captions: bool = False
    pipeline_version: str
    ffmpeg_version: str
    total_duration: float
    scenes: list[TimelineScene] = Field(default_factory=list)
    placeholder_count: int = 0
    music: TimelineMusic | None = None
    warnings: list[str] = Field(default_factory=list)
    fingerprint: Sha256
