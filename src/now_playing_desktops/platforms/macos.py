"""macOS desktop wallpaper via Finder / appscript."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from pathlib import Path


class MacOSWallpaperPlatform:
    """macOS implementation of :class:`~now_playing_desktops.platforms.base.WallpaperPlatform`."""

    def set_wallpaper(self, image_path: Path) -> None:
        from appscript import app, mactypes

        app("Finder").desktop_picture.set(mactypes.File(str(image_path.resolve())))

    def get_current_wallpaper(self) -> Path | None:
        from appscript import app

        ref = app("Finder").desktop_picture.get()
        path = str(ref.path)
        if not path:
            return None
        return Path(path)

    def get_primary_screen_size(self) -> tuple[int, int]:
        lib_path = ctypes.util.find_library("CoreGraphics")
        if not lib_path:
            return 1920, 1080
        cg = ctypes.CDLL(lib_path)
        main_id = cg.CGMainDisplayID()
        width = int(cg.CGDisplayPixelsWide(main_id))
        height = int(cg.CGDisplayPixelsHigh(main_id))
        if width <= 0 or height <= 0:
            return 1920, 1080
        return width, height


def set_desktop_wallpaper(image_path: Path) -> None:
    """Set the macOS desktop background to ``image_path`` (legacy helper)."""
    MacOSWallpaperPlatform().set_wallpaper(image_path)


if sys.platform == "darwin":
    platform = MacOSWallpaperPlatform()
else:
    platform = None  # type: ignore[assignment]
