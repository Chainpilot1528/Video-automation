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
        return problems


class AssetRegistry(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    assets: list[Asset] = Field(default_factory=list)
