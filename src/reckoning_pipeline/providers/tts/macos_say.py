"""macOS built-in ``say``: free, offline, preview-only.

Apple's macOS licence limits the system voices to personal, non-commercial
use, so this output is for timing previews and drafts only. It is registered
as ``commercial_use: not_allowed`` and can never be approved for publication.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import TTSError, TTSOptions, Voice

# "Name  en_US    # sample"; long names leave a single space before the locale.
_VOICE_RE = re.compile(r"^(?P<name>.+?)\s+(?P<locale>[a-z]{2,3}_[A-Za-z0-9]+)\s+#\s?(?P<desc>.*)$")


class MacSayProvider:
    name = "macos-say"
    sends_data_externally = False
    commercial_use_cleared = False
    license_note = ("macOS system voices are licensed for personal, non-commercial use only; "
                    "use for previews and timing, not for published narration.")
    terms_url = "https://www.apple.com/legal/sla/"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("say") or "/usr/bin/say"

    def version(self) -> str:
        return f"macOS {platform.mac_ver()[0] or 'unknown'}"

    def list_voices(self) -> list[Voice]:
        out = self._run([self.executable, "-v", "?"]).stdout
        voices = []
        for line in out.splitlines():
            m = _VOICE_RE.match(line.rstrip())
            if m:
                voices.append(Voice(m["name"].strip(), m["locale"], m["desc"].strip()))
        return voices

    def synthesize(self, text: str, voice: str, output_path: Path, options: TTSOptions) -> None:
        if not text.strip():
            raise TTSError("nothing to synthesize: narration text is empty")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Text goes through a file, never argv, so narration can't be read as options.
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as fh:
            fh.write(text)
            text_file = fh.name
        try:
            args = [self.executable, "-v", voice, "-o", str(output_path), "-f", text_file]
            if options.rate_wpm:
                args[1:1] = ["-r", str(options.rate_wpm)]
            self._run(args)
        finally:
            Path(text_file).unlink(missing_ok=True)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise TTSError(f"say produced no audio for voice {voice!r}")

    @staticmethod
    def _run(args: list[str]) -> subprocess.CompletedProcess:
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=300, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TTSError(f"say failed to run: {exc}") from exc
        if proc.returncode != 0:
            raise TTSError(f"say exited {proc.returncode}: {proc.stderr.strip()[:300]}")
        return proc
