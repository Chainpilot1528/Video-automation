"""Voicebox's built-in Qwen3 LLM (Apache-2.0) as a local text generator.

Uses ``POST /llm/generate`` on the local Voicebox app. Voicebox can be
configured to forward LLM calls to a *custom remote endpoint*; this adapter
reads that setting before every call and refuses if it points off-machine
(unless network use is approved), then checks the reply really came from a
local Qwen3 size. It never triggers a model download: if the chosen size
isn't downloaded, it says so and stops.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

from .base import ProviderUnavailableError

DEFAULT_URL = "http://127.0.0.1:17493"
LOCAL_SIZES = ("0.6B", "1.7B", "4B")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_SYSTEM_CHARS = 4000
MAX_PROMPT_CHARS = 50_000
MAX_TOKENS_LIMIT = 4096
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

Opener = Callable[..., Any]


class VoiceboxLLM:
    name = "voicebox-qwen3"

    def __init__(self, base_url: str = DEFAULT_URL, *, model_size: str = "1.7B", allow_remote: bool = False,
                 timeout: float = 900.0, opener: Opener = urllib.request.urlopen) -> None:
        if model_size not in LOCAL_SIZES:
            raise ProviderUnavailableError(f"model size must be one of {LOCAL_SIZES}, got {model_size!r}")
        host = urlparse(base_url).hostname or ""
        if host not in LOOPBACK_HOSTS and not allow_remote:
            raise ProviderUnavailableError(f"Voicebox URL {base_url!r} is not on this machine; refusing to send "
                                           "script material off-device")
        self.base_url = base_url.rstrip("/")
        self.model_size = model_size
        self.allow_remote = allow_remote
        self.sends_data_externally = host not in LOOPBACK_HOSTS
        self.timeout = timeout
        self._open = opener

    def _request(self, method: str, path: str, body: dict | None = None, timeout: float = 30) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self._open(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("detail", "")
            except (ValueError, AttributeError):
                detail = ""
            raise ProviderUnavailableError(f"Voicebox LLM error {exc.code}{': ' + str(detail) if detail else ''}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderUnavailableError(f"can't reach Voicebox at {self.base_url}; is the app open?") from exc

    def check_local(self) -> None:
        """Refuse if Voicebox forwards LLM calls to a remote endpoint, or the model isn't downloaded."""
        _, settings = self._request("GET", "/settings/captures")
        endpoint = (settings or {}).get("custom_llm_endpoint") if isinstance(settings, dict) else None
        if endpoint:
            host = urlparse(endpoint).hostname or ""
            if host not in LOOPBACK_HOSTS and not self.allow_remote:
                raise ProviderUnavailableError(
                    f"Voicebox is set to send LLM requests to a custom endpoint ({host or endpoint}); refusing so "
                    "script material stays on this Mac. Clear it in Voicebox settings to use the built-in Qwen3.")
        _, status = self._request("GET", "/models/status")
        models = status.get("models", status) if isinstance(status, dict) else status
        name = f"qwen3-{self.model_size.lower()}"
        entry = next((m for m in models or [] if m.get("model_name") == name), None)
        if entry is None or not entry.get("downloaded"):
            raise ProviderUnavailableError(
                f"Qwen3 {self.model_size} isn't downloaded in Voicebox; download it in Voicebox → Models "
                "(the pipeline won't start a download on its own)")

    def version(self) -> str:
        _, info = self._request("GET", "/")
        return f"voicebox {info.get('version', 'unknown') if isinstance(info, dict) else 'unknown'} / qwen3-{self.model_size}"

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024, temperature: float = 0.4) -> str:
        if len(system) > MAX_SYSTEM_CHARS:
            raise ProviderUnavailableError(f"system prompt is {len(system)} chars; Voicebox allows {MAX_SYSTEM_CHARS}")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise ProviderUnavailableError(f"prompt is {len(prompt)} chars; Voicebox allows {MAX_PROMPT_CHARS}")
        self.check_local()
        code, data = self._request("POST", "/llm/generate", {
            "prompt": prompt, "system": system or None, "model_size": self.model_size,
            "max_tokens": max(1, min(max_tokens, MAX_TOKENS_LIMIT)), "temperature": temperature,
        }, timeout=self.timeout)
        if code == 202:
            raise ProviderUnavailableError(f"Qwen3 {self.model_size} is still downloading in Voicebox; try again later")
        if not isinstance(data, dict) or "text" not in data:
            raise ProviderUnavailableError("Voicebox returned no text")
        if data.get("model_size") not in LOCAL_SIZES:
            raise ProviderUnavailableError(f"reply came from {data.get('model_size')!r}, not a local Qwen3 model; discarded")
        return strip_thinking(data["text"])


def strip_thinking(text: str) -> str:
    """Remove Qwen3 <think>…</think> reasoning blocks (and a dangling unclosed one)."""
    text = _THINK_RE.sub("", text)
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()
