"""Ollama (https://ollama.com, MIT): local LLMs, quantized to fit small machines.

Talks to the local Ollama server (default http://127.0.0.1:11434) through
``POST /api/chat``. Non-loopback URLs are refused unless network use is
approved. It never pulls a model: if the configured model isn't installed,
it says which command to run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

from .base import ProviderUnavailableError
from .voicebox_llm import strip_thinking

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
CONTEXT_TOKENS = 8192  # brief + claims + script so far; larger costs RAM on an 8 GB Mac

Opener = Callable[..., Any]


class OllamaLLM:
    name = "ollama"

    def __init__(self, base_url: str = DEFAULT_URL, *, model: str = DEFAULT_MODEL, allow_remote: bool = False,
                 timeout: float = 1800.0, opener: Opener = urllib.request.urlopen) -> None:
        host = urlparse(base_url).hostname or ""
        if host not in LOOPBACK_HOSTS and not allow_remote:
            raise ProviderUnavailableError(f"Ollama URL {base_url!r} is not on this machine; refusing to send "
                                           "script material off-device")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.sends_data_externally = host not in LOOPBACK_HOSTS
        self.timeout = timeout
        self._open = opener
        self._checked = False

    def _request(self, method: str, path: str, body: dict | None = None, timeout: float = 30) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self._open(req, timeout=timeout) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("error", "")
            except (ValueError, AttributeError):
                detail = ""
            raise ProviderUnavailableError(f"Ollama error {exc.code}{': ' + detail if detail else ''}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderUnavailableError(f"can't reach Ollama at {self.base_url}; is the Ollama app running?") from exc

    def check_model(self) -> None:
        tags = self._request("GET", "/api/tags") or {}
        names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
        if self.model not in names:
            raise ProviderUnavailableError(f"Ollama model {self.model!r} isn't installed; run: ollama pull {self.model} "
                                           "(the pipeline won't download models on its own)")
        self._checked = True

    def version(self) -> str:
        info = self._request("GET", "/api/version") or {}
        return f"ollama {info.get('version', 'unknown')} / {self.model}"

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024, temperature: float = 0.4) -> str:
        if not self._checked:
            self.check_model()
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        data = self._request("POST", "/api/chat", {
            "model": self.model, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": CONTEXT_TOKENS},
        }, timeout=self.timeout)
        content = ((data or {}).get("message") or {}).get("content")
        if not content:
            raise ProviderUnavailableError("Ollama returned no text")
        return strip_thinking(content)
