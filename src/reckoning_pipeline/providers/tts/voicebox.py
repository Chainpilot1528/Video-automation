"""Voicebox (https://github.com/jamiepine/voicebox, MIT): local, offline TTS studio.

Talks to the Voicebox app's local REST API (default http://127.0.0.1:17493)
through its OpenAI-compatible ``POST /v1/audio/speech`` endpoint. Text never
leaves the machine: non-loopback URLs are refused unless network use is
explicitly allowed (``PIPELINE_ALLOW_NETWORK``).

Rights are decided per voice, not per app:

* a **preset** voice of an engine whose model licence has been reviewed
  (currently Kokoro-82M, Apache-2.0) is cleared for commercial use, and is
  registered ``pending_review`` like any other asset;
* **cloned** voices need the voice owner's consent, and **designed** voices or
  other engines need a licence review, so their output is registered
  ``not_allowed`` / ``blocked`` until a person records that and reviews it.

Voices are Voicebox profiles (by name or id). ``<engine>:<voice_id>`` selects a
built-in preset voice, creating a matching preset profile in Voicebox on first
use: ``kokoro:af_heart`` (Kokoro-82M) or ``qwen_custom_voice:Ryan`` (Qwen3-TTS
CustomVoice, which also takes a delivery instruction via ``TTSOptions.extra``).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .base import TTSError, TTSOptions, Voice

DEFAULT_URL = "http://127.0.0.1:17493"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_INPUT_CHARS = 10_000  # Voicebox's /v1/audio/speech limit
PROFILE_SUFFIX = "(pipeline)"


@dataclass(frozen=True)
class EngineLicense:
    name: str
    url: str


# Engines whose *model* licence has been reviewed for commercial narration.
REVIEWED_ENGINES = {
    "kokoro": EngineLicense("Apache-2.0", "https://huggingface.co/hexgrad/Kokoro-82M"),
    "qwen_custom_voice": EngineLicense("Apache-2.0",
                                       "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"),
}
# Engines whose preset voices can be named as "<engine>:<voice_id>".
PRESET_ENGINES = ("kokoro", "qwen_custom_voice")
# Qwen3-TTS runs about 10x slower than real time on a CPU; give each request room.
SLOW_ENGINES = {"qwen_custom_voice": 3600.0}
DEFAULT_MODEL_SIZE = {"qwen_custom_voice": "0.6B"}  # 1.7B doesn't fit in 8 GB of RAM


@dataclass(frozen=True)
class Clearance:
    cleared: bool
    note: str
    terms_url: str


Opener = Callable[..., Any]


class VoiceboxProvider:
    name = "voicebox"

    def __init__(self, base_url: str = DEFAULT_URL, *, engine: str = "kokoro", allow_remote: bool = False,
                 timeout: float = 900.0, opener: Opener = urllib.request.urlopen) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise TTSError(f"invalid Voicebox URL {base_url!r}")
        loopback = parsed.hostname in LOOPBACK_HOSTS
        if not loopback and not allow_remote:
            raise TTSError(f"Voicebox URL {base_url!r} is not on this machine; refusing to send narration "
                           "off-device (set PIPELINE_ALLOW_NETWORK=true only if that is approved)")
        self.base_url = base_url.rstrip("/")
        self.engine = engine
        self.sends_data_externally = not loopback
        self.timeout = timeout
        self._open = opener
        self._version: str | None = None
        self._routes: set[str] | None = None

    # --- static description (used when no voice is known yet) ---------------

    @property
    def commercial_use_cleared(self) -> bool:
        return self.engine in REVIEWED_ENGINES

    @property
    def license_note(self) -> str:
        lic = REVIEWED_ENGINES.get(self.engine)
        if lic:
            return (f"Voicebox (MIT) running the {self.engine} engine, model licensed {lic.name}. "
                    "Preset voices only; cloned voices need the speaker's consent.")
        return f"Voicebox engine {self.engine!r} has no reviewed model licence; output is blocked from publication."

    @property
    def terms_url(self) -> str:
        lic = REVIEWED_ENGINES.get(self.engine)
        return lic.url if lic else "https://github.com/jamiepine/voicebox"

    # --- HTTP ----------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None, *, timeout: float | None = None,
                 raw: bool = False) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "X-Voicebox-Client-Id": "reckoning-pipeline"})
        try:
            with self._open(req, timeout=timeout or 30) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            raise TTSError(f"Voicebox {method} {path} failed ({exc.code}): {_error_message(exc.read())}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise TTSError(f"can't reach Voicebox at {self.base_url} ({getattr(exc, 'reason', exc)}); "
                           "is the Voicebox app open?") from exc
        return payload if raw else json.loads(payload or b"null")

    # --- TTSProvider ---------------------------------------------------------

    def _has_route(self, path: str) -> bool:
        """Whether the running Voicebox exposes ``path`` (its API changed between releases)."""
        if self._routes is None:
            try:
                spec = self._request("GET", "/openapi.json")
                self._routes = set((spec or {}).get("paths", {})) if isinstance(spec, dict) else set()
            except TTSError:
                self._routes = set()
        return path in self._routes

    def version(self) -> str:
        if self._version is None:
            info = self._request("GET", "/")
            v = info.get("version", "unknown") if isinstance(info, dict) else "unknown"
            self._version = f"voicebox {v} / {self.engine}"
        return self._version

    def profiles(self) -> list[dict]:
        result = self._request("GET", "/profiles")
        return result if isinstance(result, list) else []

    def presets(self, engine: str | None = None) -> list[dict]:
        result = self._request("GET", f"/profiles/presets/{engine or self.engine}")
        return result.get("voices", []) if isinstance(result, dict) else []

    def engine_for(self, voice: str) -> str:
        """The engine a voice runs on: its "<engine>:" prefix, else this provider's default."""
        prefix, sep, _ = voice.partition(":")
        return prefix if sep and prefix in PRESET_ENGINES else self.engine

    def list_voices(self) -> list[Voice]:
        voices = []
        for p in self.profiles():
            kind = p.get("voice_type", "cloned")
            detail = f"{kind}" + (f" {p.get('preset_engine')}:{p.get('preset_voice_id')}" if kind == "preset" else "")
            voices.append(Voice(p["name"], p.get("language", ""), detail))
        for engine in dict.fromkeys((self.engine, *PRESET_ENGINES)):
            try:
                presets = self.presets(engine)
            except TTSError:
                if engine == self.engine:
                    raise
                continue  # an older Voicebox without this engine
            for v in presets:
                voices.append(Voice(f"{engine}:{v['voice_id']}", v.get("language", ""),
                                    f"{engine} preset {v.get('name', '')} ({v.get('gender', '')}); "
                                    "profile created on first use"))
        return voices

    def resolve_profile(self, voice: str, *, create: bool = True) -> dict:
        """Find the Voicebox profile for ``voice``; ``engine:voice_id`` may create a preset profile."""
        profiles = self.profiles()
        engine, _, preset_id = voice.partition(":")
        if preset_id and engine in PRESET_ENGINES:
            for p in profiles:
                if (p.get("voice_type") == "preset" and p.get("preset_engine") == engine
                        and p.get("preset_voice_id") == preset_id):
                    return p
            preset = next((v for v in self.presets(engine) if v.get("voice_id") == preset_id), None)
            if preset is None:
                raise TTSError(f"{engine} has no preset voice {preset_id!r}; see 'pipeline narration voices "
                               "--provider voicebox'")
            if not create:
                raise TTSError(f"no Voicebox profile yet for {voice!r}")
            return self._request("POST", "/profiles", {
                "name": f"{engine.title()} {preset_id} {PROFILE_SUFFIX}", "language": preset.get("language", "en"),
                "voice_type": "preset", "preset_engine": engine, "preset_voice_id": preset_id,
                "default_engine": engine,
                "description": "Created by reckoning-pipeline for narration previews and builds.",
            })
        wanted = voice.lower()
        for p in profiles:
            if p.get("id") == voice or p.get("name", "").lower() == wanted:
                return p
        raise TTSError(f"Voicebox has no voice profile {voice!r}; see 'pipeline narration voices --provider voicebox'")

    def voice_clearance(self, voice: str) -> Clearance:
        profile = self.resolve_profile(voice)
        kind = profile.get("voice_type", "cloned")
        engine = profile.get("preset_engine") or self.engine
        lic = REVIEWED_ENGINES.get(engine)
        if kind == "preset" and lic:
            return Clearance(True, f"Voicebox (MIT) {engine} preset voice "
                                   f"'{profile.get('preset_voice_id')}'; model licensed {lic.name} ({lic.url}).",
                             lic.url)
        if kind == "cloned":
            return Clearance(False, "Cloned voice: publishing needs the voice owner's written consent. Record it in "
                                    "rights_evidence, set commercial_use, then review the asset.",
                             "https://github.com/jamiepine/voicebox")
        return Clearance(False, f"{kind} voice on engine {engine!r}: model licence not reviewed for "
                                "commercial narration.", "https://github.com/jamiepine/voicebox")

    def synthesize(self, text: str, voice: str, output_path: Path, options: TTSOptions) -> None:
        if not text.strip():
            raise TTSError("nothing to synthesize: narration text is empty")
        if len(text) > MAX_INPUT_CHARS:
            raise TTSError(f"narration is {len(text)} characters; Voicebox accepts at most {MAX_INPUT_CHARS} per request")
        profile = self.resolve_profile(voice)
        engine = self.engine_for(voice)
        extra = options.extra or {}
        if engine in SLOW_ENGINES or extra.get("instruct"):
            # Only the native endpoint carries a model size and a delivery instruction.
            body = {"profile_id": profile["id"], "text": text, "engine": engine,
                    "language": profile.get("language") or "en", "seed": 0}
            if extra.get("model_size") or engine in DEFAULT_MODEL_SIZE:
                body["model_size"] = extra.get("model_size") or DEFAULT_MODEL_SIZE[engine]
            if extra.get("instruct"):
                body["instruct"] = extra["instruct"]
            audio = self._request("POST", "/generate/stream", body,
                                  timeout=max(self.timeout, SLOW_ENGINES.get(engine, 0.0)), raw=True)
        elif self._has_route("/v1/audio/speech"):
            speed = float(options.extra.get("speed", 1.0)) if options.extra else 1.0
            audio = self._request("POST", "/v1/audio/speech",
                                  {"model": engine, "input": text, "voice": profile["id"],
                                   "response_format": "wav", "speed": speed},
                                  timeout=self.timeout, raw=True)
        else:
            # Voicebox <= 0.5.0: stream the WAV directly (nothing saved to its history). Fixed seed
            # keeps repeat builds of the same text as stable as the engine allows.
            audio = self._request("POST", "/generate/stream",
                                  {"profile_id": profile["id"], "text": text, "engine": engine,
                                   "language": profile.get("language") or "en", "seed": 0},
                                  timeout=self.timeout, raw=True)
        if not audio or audio[:4] != b"RIFF":
            raise TTSError("Voicebox returned no WAV audio")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)


def _error_message(body: bytes) -> str:
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return body.decode("utf-8", "replace")[:300]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if data.get("detail"):
            return str(data["detail"])
    return str(data)[:300]
