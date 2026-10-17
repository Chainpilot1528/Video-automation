"""Environment health checks for ``pipeline doctor``.

Each check returns PASS / WARN / FAIL with a remediation hint. Checks only
inspect the machine; they never install, download, or call external services.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from .config import PipelineConfig

GIB = 1024**3


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str
    remedy: str = ""


Which = Callable[[str], str | None]
Runner = Callable[[list[str]], str | None]
DiskUsage = Callable[[Path], tuple[int, int, int]]


def _run_first_line(args: list[str]) -> str | None:
    """Run a command (argument array, no shell) and return its first output line."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or proc.stderr).strip().splitlines()
    return out[0] if out else ""


def check_python(version_info=sys.version_info) -> CheckResult:
    v = f"{version_info[0]}.{version_info[1]}.{version_info[2]}"
    if tuple(version_info[:2]) < (3, 11):
        return CheckResult("python", Status.FAIL, f"Python {v}", "Use Python 3.11 or newer.")
    if tuple(version_info[:2]) >= (3, 14):
        return CheckResult(
            "python", Status.WARN, f"Python {v}",
            "Core deps support it; some optional ML packages may lack wheels for 3.14 yet.",
        )
    return CheckResult("python", Status.PASS, f"Python {v}")


def check_tool(
    name: str, executable: str, *, required: bool, remedy: str,
    which: Which = shutil.which, run: Runner = _run_first_line,
) -> CheckResult:
    path = which(executable)
    if path is None:
        status = Status.FAIL if required else Status.WARN
        label = "not found" if required else "not found (optional)"
        return CheckResult(name, status, f"{executable}: {label}", remedy)
    version = run([path, "-version" if name in {"ffmpeg", "ffprobe"} else "--version"])
    if version is None:
        return CheckResult(name, Status.FAIL if required else Status.WARN,
                           f"{path} found but did not run", remedy)
    return CheckResult(name, Status.PASS, f"{path} — {version}")


def check_disk(path: Path, config: PipelineConfig, disk_usage: DiskUsage = shutil.disk_usage) -> CheckResult:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    _total, _used, free = disk_usage(probe)
    free_gb = free / GIB
    detail = f"{free_gb:.1f} GiB free at {probe}"
    if free_gb < config.min_free_disk_gb:
        return CheckResult("disk", Status.FAIL, detail,
                           f"Free at least {config.min_free_disk_gb:g} GiB before rendering.")
    if free_gb < config.warn_free_disk_gb:
        return CheckResult("disk", Status.WARN, detail,
                           "Space is tight for media work; consider an external media root.")
    return CheckResult("disk", Status.PASS, detail)


def check_architecture(machine: str | None = None) -> CheckResult:
    machine = machine or platform.machine()
    if machine == "arm64":
        return CheckResult("architecture", Status.PASS, "Apple Silicon (arm64)")
    return CheckResult(
        "architecture", Status.WARN, f"{machine} (not Apple Silicon)",
        "No Metal/MLX acceleration: local LLM, TTS and image generation will be CPU-only and slow.",
    )


def check_writable_dir(name: str, path: Path) -> CheckResult:
    target = path if path.exists() else path.parent
    if path.exists() and not path.is_dir():
        return CheckResult(name, Status.FAIL, f"{path} exists but is not a directory",
                           "Point the setting at a directory.")
    if not target.exists():
        return CheckResult(name, Status.FAIL, f"{path} and its parent do not exist",
                           "Create the directory or change the setting.")
    if not os.access(target, os.W_OK):
        return CheckResult(name, Status.FAIL, f"{target} is not writable", "Fix permissions.")
    state = "exists" if path.exists() else "will be created"
    return CheckResult(name, Status.PASS, f"{path} ({state})")


def check_media_root(config: PipelineConfig) -> CheckResult:
    if config.media_root is None:
        return CheckResult("media_root", Status.PASS, "not set (media stays inside each project)")
    return check_writable_dir("media_root", config.media_root)


def check_network_policy(config: PipelineConfig) -> CheckResult:
    if config.allow_paid_providers:
        return CheckResult("providers", Status.WARN, "paid providers ENABLED",
                           "Unset PIPELINE_ALLOW_PAID_PROVIDERS unless spending is approved.")
    net = "allowed" if config.allow_network else "disabled"
    return CheckResult("providers", Status.PASS, f"paid providers off; network {net}")


def run_checks(
    config: PipelineConfig, *, which: Which | None = None, run: Runner | None = None,
    disk_usage: DiskUsage | None = None,
) -> list[CheckResult]:
    # Resolve defaults at call time so tests can monkeypatch module attributes.
    which = which or shutil.which
    run = run or _run_first_line
    disk_usage = disk_usage or shutil.disk_usage
    ffmpeg_remedy = "Install FFmpeg (see docs/INSTALL.md), or set PIPELINE_FFMPEG_PATH / PIPELINE_FFPROBE_PATH."
    return [
        check_python(),
        check_architecture(),
        check_tool("ffmpeg", config.ffmpeg_path, required=True, remedy=ffmpeg_remedy, which=which, run=run),
        check_tool("ffprobe", config.ffprobe_path, required=True, remedy=ffmpeg_remedy, which=which, run=run),
        check_tool("git", "git", required=False, remedy="Install Xcode Command Line Tools.", which=which, run=run),
        check_tool("ollama", "ollama", required=False,
                   remedy="Optional, for Phase 9 local LLM tasks. Not needed now.", which=which, run=run),
        check_disk(config.media_root or config.projects_root.resolve(), config, disk_usage),
        check_writable_dir("projects_root", config.projects_root),
        check_media_root(config),
        check_network_policy(config),
    ]


def has_failures(results: list[CheckResult]) -> bool:
    return any(r.status is Status.FAIL for r in results)
