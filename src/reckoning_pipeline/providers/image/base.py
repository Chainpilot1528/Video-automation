"""Provider-neutral image/video generation interface.

No provider ships or is enabled. Local diffusion on an 8 GB Intel Mac is
impractical, and hosted services cost money and send prompts off the
machine, so any adapter needs a licence/terms review, a disk/memory check,
and explicit approval (Phase 9). Until then, unresolved beats get clearly
labelled placeholders, never unrelated substitute media.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ...config import PipelineConfig


class ImageProviderUnavailableError(RuntimeError):
    """No image provider is enabled."""


@runtime_checkable
class ImageProvider(Protocol):
    name: str
    sends_data_externally: bool
    commercial_use_cleared: bool
    terms_url: str

    def version(self) -> str:
        ...

    def generate(self, prompt: str, output_path: Path, *, negative_prompt: str = "", width: int = 1920,
                 height: int = 1080, seed: int | None = None, settings: dict[str, Any] | None = None) -> None:
        """Write one image for ``prompt`` to ``output_path``."""
        ...


def get_image_provider(config: PipelineConfig) -> ImageProvider:
    raise ImageProviderUnavailableError(
        "no image generation provider is enabled (none ships; evaluated in Phase 9 with your approval). "
        "Use 'pipeline visuals placeholders' for unresolved beats, or supply a manual asset."
    )
