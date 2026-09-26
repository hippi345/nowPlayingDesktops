"""Detect Linux desktop environment and session hints."""

from __future__ import annotations

import os
import subprocess
from enum import StrEnum


class LinuxDesktopEnvironment(StrEnum):
    GNOME = "gnome"
    KDE = "kde"
    OTHER = "other"


_GNOME_MARKERS = frozenset(
    {
        "gnome",
        "unity",
        "budgie",
        "cinnamon",
        "ubuntu",
        "pop",
    }
)


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    return value.lower().replace(":", " ").strip()


def _tokens_from_env() -> set[str]:
    tokens: set[str] = set()
    for key in ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "GDMSESSION"):
        raw = os.environ.get(key)
        if not raw:
            continue
        for part in raw.split(":"):
            part = part.strip().lower()
            if part:
                tokens.add(part)
    return tokens


def _running_process_names() -> set[str]:
    try:
        proc = subprocess.run(
            ["ps", "-eo", "comm="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode != 0:
        return set()
    return {line.strip().lower() for line in proc.stdout.splitlines() if line.strip()}


def detect_linux_desktop_environment(
    *,
    env_tokens: set[str] | None = None,
    process_names: set[str] | None = None,
) -> LinuxDesktopEnvironment:
    """Classify the session as GNOME-family, KDE, or other."""
    tokens = env_tokens if env_tokens is not None else _tokens_from_env()
    processes = process_names if process_names is not None else _running_process_names()

    kde_hits = {"plasmashell", "kwin_wayland", "kwin_x11", "kde"}
    if tokens & kde_hits or processes & kde_hits:
        return LinuxDesktopEnvironment.KDE

    for token in tokens:
        for marker in _GNOME_MARKERS:
            if marker in token:
                return LinuxDesktopEnvironment.GNOME

    gnome_procs = {"gnome-shell", "mutter", "cinnamon", "budgie-wm"}
    if processes & gnome_procs:
        return LinuxDesktopEnvironment.GNOME

    return LinuxDesktopEnvironment.OTHER
