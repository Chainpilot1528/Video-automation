"""Asset registry: ``assets/registry.json``.

Unknown rights never default to approved: ``publication_status: approved``
is only accepted when the rights fields are complete and positive.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .common import SCHEMA_VERSION, Identifier, NonEmptyStr, Record, RelPath, Sha256, no_duplicates


class AssetType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    NARRATION = "narration"
    MUSIC = "music"
    SOUND_EFFECT = "sound_effect"
    GRAPHIC = "graphic"
    FONT = "font"
    DOCUMENT = "document"
    OTHER = "other"


class AssetRoot(StrEnum):
    PROJECT = "project"  # path relative to the project folder
    MEDIA = "media"      # path relative to PIPELINE_MEDIA_ROOT


class CreationMethod(StrEnum):
    DOWNLOADED = "downloaded"
    USER_SUPPLIED = "user_supplied"
    GENERATED = "generated"
    ORIGINAL_GRAPHIC = "original_graphic"
    RECORDED = "recorded"


class CommercialUse(StrEnum):
    ALLOWED = "allowed"
    NOT_ALLOWED = "not_allowed"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublicationStatus(StrEnum):
    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    BLOCKED = "blocked"


EXTERNAL_METHODS = frozenset({CreationMethod.DOWNLOADED, CreationMethod.USER_SUPPLIED,
                              CreationMethod.GENERATED})
VISUAL_TYPES = frozenset({AssetType.IMAGE, AssetType.VIDEO})
AUDIO_MUSIC_TYPES = frozenset({AssetType.MUSIC, AssetType.SOUND_EFFECT})


class GenerationInfo(Record):
    provider: NonEmptyStr
    model: NonEmptyStr
    model_version: str = ""
    generated_on: date | None = None
    prompt: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    terms_url: str = ""


class Asset(Record):
    asset_id: Identifier
    path: RelPath
    root: AssetRoot = AssetRoot.PROJECT
    type: AssetType
    creation_method: CreationMethod
    provider: str = ""  # originating site, archive, or service
    source_url: str | None = None
    creator: str = ""
    rights_holder: str = ""
    license_name: str = ""
    license_url: str = ""
    commercial_use: CommercialUse = CommercialUse.UNKNOWN
    attribution_required: bool | None = None  # None = not yet known
    attribution_text: str = ""
    derivatives_allowed: bool | None = None
    rights_evidence: str = ""
    # Rights checklist. None = not yet checked; approval needs the relevant ones answered.
    identifiable_people: bool | None = None
    people_clearance: str = ""       # release obtained, or why none is needed (e.g. editorial use)
    trademarks_visible: bool | None = None
    trademark_notes: str = ""        # how use avoids implying endorsement
    raw_redistribution_allowed: bool | None = None  # may the raw file ship in a public archive?
    platform_cleared: bool | None = None  # music/SFX: confirmed safe for YouTube/Instagram use
    generation: GenerationInfo | None = None
    acquired_date: date | None = None
    sha256: Sha256
    derived_from: Identifier | None = None
    intended_scene_ids: list[Identifier] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PENDING
    publication_status: PublicationStatus = PublicationStatus.PENDING_REVIEW
    notes: str = ""

    @field_validator("intended_scene_ids")
    @classmethod
    def _unique(cls, value: list) -> list:
        return no_duplicates(value, "intended_scene_ids")

    @model_validator(mode="after")
    def _rules(self) -> "Asset":
        if self.creation_method is CreationMethod.GENERATED and self.generation is None:
            raise ValueError("generated assets must record generation (provider, model, ...)")
        if self.creation_method is not CreationMethod.GENERATED and self.generation is not None:
            raise ValueError("generation info is only allowed when creation_method is 'generated'")
        if self.creation_method is CreationMethod.DOWNLOADED and not self.source_url:
            raise ValueError("downloaded assets must record source_url")
        if self.derived_from == self.asset_id:
            raise ValueError("an asset cannot be derived from itself")
        if self.publication_status is PublicationStatus.APPROVED:
            problems = self.approval_blockers()
            if problems:
                raise ValueError("publication_status 'approved' is not allowed: " + "; ".join(problems))
        return self

    def approval_blockers(self) -> list[str]:
        """Reasons this asset's rights are not yet complete enough to approve."""
        problems = []
        if self.review_status is not ReviewStatus.APPROVED:
            problems.append("review_status is not 'approved'")
        if self.commercial_use is not CommercialUse.ALLOWED:
            problems.append(f"commercial_use is '{self.commercial_use}'")
        if self.attribution_required is None:
            problems.append("attribution_required is unknown")
        if self.attribution_required and not self.attribution_text:
            problems.append("attribution is required but attribution_text is empty")
        if not self.rights_evidence:
            problems.append("rights_evidence is empty")
        if not (self.rights_holder or self.creator):
            problems.append("rights_holder/creator is empty")
        if self.creation_method in (CreationMethod.DOWNLOADED, CreationMethod.USER_SUPPLIED) \
                and not self.license_name:
            problems.append("license_name is empty")
        if self.creation_method is CreationMethod.DOWNLOADED and not self.license_url:
            problems.append("license_url is empty (record the exact licence for this asset)")
        if self.creation_method is CreationMethod.GENERATED and self.generation \
                and not self.generation.terms_url:
            problems.append("generation.terms_url is empty (record the service terms)")
        return problems + self.checklist_gaps()

    @property
    def is_external(self) -> bool:
        return self.creation_method in EXTERNAL_METHODS

    def checklist_gaps(self) -> list[str]:
        """Rights-checklist questions that must be answered before approval."""
        gaps = []
        visual = self.type in VISUAL_TYPES
        if self.is_external and self.derivatives_allowed is None:
            gaps.append("derivatives_allowed is unknown")
        if visual and self.creation_method is not CreationMethod.ORIGINAL_GRAPHIC:
            if self.identifiable_people is None:
                gaps.append("identifiable_people is unknown")
            elif self.identifiable_people and not self.people_clearance:
                gaps.append("identifiable people shown but people_clearance is empty")
        if visual and self.is_external:
            if self.trademarks_visible is None:
                gaps.append("trademarks_visible is unknown")
            elif self.trademarks_visible and not self.trademark_notes:
                gaps.append("trademarks visible but trademark_notes is empty")
        if self.type in AUDIO_MUSIC_TYPES and self.is_external and self.platform_cleared is not True:
            gaps.append("music/SFX not confirmed cleared for platform use (platform_cleared)")
        return gaps


class AssetRegistry(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    assets: list[Asset] = Field(default_factory=list)
