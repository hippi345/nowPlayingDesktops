"""Windows desktop wallpaper via SystemParametersInfo."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover - import guard for non-Windows CI
    winreg = None  # type: ignore[assignment]

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02
SM_CXSCREEN = 0
SM_CYSCREEN = 1
_MAX_WALLPAPER_CHARS = 260


class WindowsWallpaperPlatform:
    """Windows implementation of :class:`~now_playing_desktops.platforms.base.WallpaperPlatform`."""

    def set_wallpaper(self, image_path: Path) -> None:
        path_str = str(image_path.resolve())
        if not ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            path_str,
            SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
        ):
            raise OSError(f"SystemParametersInfoW failed for {path_str}")

    def get_current_wallpaper(self) -> Path | None:
        buffer = ctypes.create_unicode_buffer(_MAX_WALLPAPER_CHARS)
        if not ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETDESKWALLPAPER,
            len(buffer),
            buffer,
            0,
        ):
            return _wallpaper_from_registry()
        path = buffer.value.strip()
        if not path:
            return _wallpaper_from_registry()
        return Path(path)

    def get_primary_screen_size(self) -> tuple[int, int]:
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(SM_CXSCREEN)), int(user32.GetSystemMetrics(SM_CYSCREEN))


def _wallpaper_from_registry() -> Path | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Control Panel\Desktop",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Wallpaper")
    except OSError:
        return None
    if not value:
        return None
    return Path(str(value))


def set_desktop_wallpaper(image_path: Path) -> None:
    """Set the Windows desktop background to ``image_path`` (legacy helper)."""
    WindowsWallpaperPlatform().set_wallpaper(image_path)


if sys.platform == "win32":
    platform = WindowsWallpaperPlatform()
else:
    platform = None  # type: ignore[assignment]
