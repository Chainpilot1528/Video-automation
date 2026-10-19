"""Typed, versioned data contracts. These manifests are the source of truth."""

from __future__ import annotations

import json
from pathlib import Path

from .approval import ApprovalEvent, ApprovalLog
from .asset import Asset, AssetRegistry
from .narration import NarrationReport, PronunciationList
from .common import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from .project import ProjectManifest
from .qa import QAReport
from .render import RenderReport
from .research import Claim, ResearchLedger, Source
from .scene import Scene, SceneManifest
from .visual import GraphicSpec, VisualBeat, VisualPlan

# File-level models, keyed by the JSON Schema file name they export to.
FILE_MODELS = {
    "project": ProjectManifest,
    "scenes": SceneManifest,
    "research_ledger": ResearchLedger,
    "asset_registry": AssetRegistry,
    "approvals": ApprovalLog,
    "visuals": VisualPlan,
    "graphic_spec": GraphicSpec,
    "pronunciations": PronunciationList,
    "narration_report": NarrationReport,
    "render_report": RenderReport,
    "qa_report": QAReport,
}


def json_schemas() -> dict[str, str]:
    """Return {file name: JSON Schema text} for every file-level model."""
    return {
        f"{name}.schema.json": json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        for name, model in FILE_MODELS.items()
    }


def export_json_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in json_schemas().items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


__all__ = [
    "SCHEMA_VERSION", "SUPPORTED_SCHEMA_VERSIONS", "FILE_MODELS",
    "ApprovalEvent", "ApprovalLog", "Asset", "AssetRegistry", "Claim", "ProjectManifest", "RenderReport",
    "GraphicSpec", "QAReport", "ResearchLedger", "Scene", "SceneManifest", "Source", "VisualBeat", "VisualPlan",
    "export_json_schemas", "json_schemas",
]
