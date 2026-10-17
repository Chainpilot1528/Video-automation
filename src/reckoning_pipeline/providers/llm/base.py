"""Provider-neutral LLM interface.

Providers are adapters, not the architecture. None is enabled by default and
none ships yet (Phase 9 evaluates local/hosted options). Every adapter must
document internet use, cost, and what data it sends before it can be enabled.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...config import PipelineConfig


class ProviderUnavailableError(RuntimeError):
    """No LLM provider is enabled, or the enabled one cannot be used."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    sends_data_externally: bool

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        """Return the model's text response to ``prompt``."""
        ...


def get_llm_provider(config: PipelineConfig) -> LLMProvider:
    """Return the configured provider, or raise if none is enabled.

    Phase 3 ships the interface only; adapters are added and benchmarked in Phase 9.
    """
    raise ProviderUnavailableError(
        "no LLM provider is enabled. Adapters (e.g. a local Ollama model) arrive in Phase 9; "
        "research and drafting work fully without one."
    )
