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


def get_llm_provider(config: PipelineConfig, name: str | None = None) -> LLMProvider:
    """Return the chosen provider (``--provider`` or PIPELINE_LLM_PROVIDER), or raise if none is enabled."""
    choice = name or config.llm_provider
    if choice == "voicebox":
        from .voicebox_llm import VoiceboxLLM
        return VoiceboxLLM(config.voicebox_url, model_size=config.llm_model_size, allow_remote=config.allow_network)
    if choice == "ollama":
        from .ollama import OllamaLLM
        return OllamaLLM(config.ollama_url, model=config.ollama_model, allow_remote=config.allow_network)
    if choice in ("", "none"):
        raise ProviderUnavailableError(
            "no LLM provider is enabled. Use --provider ollama (local, recommended) or --provider voicebox, or set "
            "PIPELINE_LLM_PROVIDER; research and writing also work fully without one.")
    raise ProviderUnavailableError(f"unknown LLM provider {choice!r}; available: ollama, voicebox")
