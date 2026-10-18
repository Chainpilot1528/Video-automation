from .base import TTSError, TTSOptions, TTSProvider, Voice
from .macos_say import MacSayProvider
from .voicebox import VoiceboxProvider

PROVIDERS = {"macos-say": MacSayProvider, "voicebox": VoiceboxProvider}


def get_tts_provider(name: str, config=None) -> TTSProvider:
    if name not in PROVIDERS:
        raise TTSError(f"unknown TTS provider {name!r}; available: {', '.join(PROVIDERS)}")
    if name == "voicebox":
        if config is None:
            return VoiceboxProvider()
        return VoiceboxProvider(config.voicebox_url, engine=config.voicebox_engine,
                                allow_remote=config.allow_network)
    return PROVIDERS[name]()


__all__ = ["PROVIDERS", "MacSayProvider", "TTSError", "TTSOptions", "TTSProvider", "Voice", "VoiceboxProvider",
           "get_tts_provider"]
