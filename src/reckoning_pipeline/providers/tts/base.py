"""Provider-neutral text-to-speech interface.

TTS is optional: imported human narration is a first-class route. Every
adapter declares whether it sends data off the machine and whether its
output is cleared for commercial publication; output that isn't cleared is
registered as ``commercial_use: not_allowed`` so it can never be approved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


class TTSError(RuntimeError):
    """Synthesis failed or the provider is unavailable."""


@dataclass(frozen=True)
class Voice:
    name: str
    locale: str
    description: str = ""


@dataclass(frozen=True)
class TTSOptions:
    rate_wpm: int | None = None
    extra: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class TTSProvider(Protocol):
    name: str
    sends_data_externally: bool
    commercial_use_cleared: bool
    license_note: str
    terms_url: str

    def version(self) -> str:
        """Provider/model version, recorded in provenance and cache keys."""
        ...

    def list_voices(self) -> list[Voice]:
        ...

    def synthesize(self, text: str, voice: str, output_path: Path, options: TTSOptions) -> None:
        """Write speech for ``text`` to ``output_path`` (any format FFmpeg reads)."""
        ...
