"""Optional IDesktopWallpaper COM helpers (patched in tests; off by default)."""

from __future__ import annotations


def idesktop_wallpaper_available() -> bool:
    return False


def set_wallpaper_for_monitor(monitor_id: str, path: str) -> None:
    raise OSError("IDesktopWallpaper is not available")


def get_wallpaper_for_monitor(monitor_id: str) -> str | None:
    return None
