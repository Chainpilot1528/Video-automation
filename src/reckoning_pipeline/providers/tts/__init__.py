from .base import TTSError, TTSOptions, TTSProvider, Voice
from .macos_say import MacSayProvider

PROVIDERS = {"macos-say": MacSayProvider}


def get_tts_provider(name: str) -> TTSProvider:
    if name not in PROVIDERS:
        raise TTSError(f"unknown TTS provider {name!r}; available: {', '.join(PROVIDERS)}")
    return PROVIDERS[name]()


__all__ = ["PROVIDERS", "MacSayProvider", "TTSError", "TTSOptions", "TTSProvider", "Voice", "get_tts_provider"]
