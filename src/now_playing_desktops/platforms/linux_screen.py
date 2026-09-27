"""Linux display geometry helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from now_playing_desktops.platforms.base import ScreenInfo

_PRIMARY_FALLBACK = (1920, 1080)


def _parse_xrandr_primary(lines: list[str]) -> list[ScreenInfo]:
    screens: list[ScreenInfo] = []
    pattern = re.compile(
        r"^(\S+)\s+connected\s+(primary)?\s*(\d+)x(\d+)\+(\d+)\+(\d+)",
    )
    for line in lines:
        match = pattern.match(line.strip())
        if not match:
            continue
        name, primary_flag, width, height, _x, _y = match.groups()
        screens.append(
            ScreenInfo(
                screen_id=name,
                width=int(width),
                height=int(height),
                is_primary=primary_flag is not None,
            )
        )
    if screens and not any(s.is_primary for s in screens):
        screens[0] = ScreenInfo(
            screen_id=screens[0].screen_id,
            width=screens[0].width,
            height=screens[0].height,
            is_primary=True,
        )
    return screens


def screens_from_xrandr(run_xrandr: bool = True) -> list[ScreenInfo]:
    if not run_xrandr:
        return []
    try:
        proc = subprocess.run(
            ["xrandr", "--query"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return _parse_xrandr_primary(proc.stdout.splitlines())


def screens_from_gnome() -> list[ScreenInfo]:
    try:
        proc = subprocess.run(
            ["gsettings", "get", "org.gnome.Mutter", "display-config"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    numbers = re.findall(r"(\d{3,5})", proc.stdout)
    if len(numbers) >= 2:
        w, h = int(numbers[0]), int(numbers[1])
        if w > 0 and h > 0:
            return [ScreenInfo(screen_id="primary", width=w, height=h, is_primary=True)]
    return []


def screens_from_wlr_randr() -> list[ScreenInfo]:
    try:
        proc = subprocess.run(
            ["wlr-randr"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    screens: list[ScreenInfo] = []
    current_name = "primary"
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(" "):
            current_name = stripped.split()[0]
        if "current" in stripped and "x" in stripped:
            match = re.search(r"(\d+)x(\d+)", stripped)
            if match:
                screens.append(
                    ScreenInfo(
                        screen_id=current_name,
                        width=int(match.group(1)),
                        height=int(match.group(2)),
                        is_primary=len(screens) == 0,
                    )
                )
    return screens


def list_linux_screens() -> list[ScreenInfo]:
    for provider in (screens_from_xrandr, screens_from_gnome, screens_from_wlr_randr):
        found = provider()
        if found:
            return found
    w, h = _PRIMARY_FALLBACK
    return [ScreenInfo(screen_id="primary", width=w, height=h, is_primary=True)]


def primary_screen_size() -> tuple[int, int]:
    screens = list_linux_screens()
    for screen in screens:
        if screen.is_primary:
            return screen.width, screen.height
    if screens:
        return screens[0].width, screens[0].height
    return _PRIMARY_FALLBACK


def path_from_file_uri(uri: str) -> Path | None:
    if not uri:
        return None
    text = uri.strip().strip("'\"")
    if text.startswith("file://"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(text)
        return Path(unquote(parsed.path))
    return Path(text)
