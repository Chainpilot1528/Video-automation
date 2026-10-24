"""Output profiles. Vertical 9:16 waits until landscape rendering is stable (Phase 11)."""

from __future__ import annotations

from ..schemas import ProjectManifest
from ..schemas.timeline import RenderProfile


class ProfileError(ValueError):
    """Unknown or not-yet-supported profile."""


def get_profile(name: str, manifest: ProjectManifest) -> RenderProfile:
    if name == "preview":
        # Small and fast for reviewing timing on a 4-core Intel laptop.
        return RenderProfile(name="preview", width=960, height=540, fps=manifest.frame_rate,
                             video_preset="veryfast", crf=28, audio_bitrate="128k",
                             audio_sample_rate=manifest.audio_sample_rate,
                             allow_placeholders=True, require_narration=False)
    if name == "master_16x9":
        return RenderProfile(name="master_16x9", width=manifest.resolution.width,
                             height=manifest.resolution.height, fps=manifest.frame_rate,
                             # upload grade: low compression, a careful preset, and dark-scene tuning so the
                             # near-black canvas and soft glows don't band after YouTube re-encodes them
                             video_preset="slow", crf=14, audio_bitrate="192k",
                             audio_sample_rate=manifest.audio_sample_rate,
                             allow_placeholders=False, require_narration=True,
                             x264_params="aq-mode=3:aq-strength=0.9:deblock=-1,-1")
    if name == "vertical_9x16":
        raise ProfileError("vertical_9x16 is built only after the landscape master is approved (Phase 11)")
    raise ProfileError(f"unknown profile {name!r}; use preview or master_16x9")
