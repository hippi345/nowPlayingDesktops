"""Platform-specific wallpaper setters and display helpers."""

from __future__ import annotations

import sys

from now_playing_desktops.platforms.base import ScreenInfo, WallpaperPlatform


class UnsupportedPlatformError(RuntimeError):
    """Raised when the host OS has no wallpaper backend in this package."""


def get_platform() -> WallpaperPlatform:
    """Return the wallpaper platform implementation for the current OS."""
    if sys.platform == "win32":
        from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform

        return WindowsWallpaperPlatform()
    if sys.platform == "darwin":
        from now_playing_desktops.platforms.macos import MacOSWallpaperPlatform

        return MacOSWallpaperPlatform()
    if sys.platform == "linux":
        from now_playing_desktops.platforms.linux import LinuxWallpaperPlatform

        try:
            return LinuxWallpaperPlatform()
        except OSError as exc:
            raise UnsupportedPlatformError(
                "Linux wallpaper backend unavailable; install gsettings (GNOME), "
                "plasma tools (KDE), or feh/swaybg/nitrogen."
            ) from exc
    raise UnsupportedPlatformError(
        f"Unsupported platform {sys.platform!r}; wallpaper control is not available."
    )


__all__ = [
    "ScreenInfo",
    "UnsupportedPlatformError",
    "WallpaperPlatform",
    "get_platform",
]
