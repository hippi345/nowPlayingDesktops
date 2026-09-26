"""Platform abstraction for desktop wallpaper and display geometry."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class WallpaperPlatform(Protocol):
    """Interface PR 2 can extend with per-monitor support."""

    def set_wallpaper(self, path: Path) -> None:
        """Set the desktop wallpaper to ``path``."""
        ...

    def get_current_wallpaper(self) -> Path | None:
        """Return the current wallpaper path, if known."""
        ...

    def get_primary_screen_size(self) -> tuple[int, int]:
        """Return primary display width and height in pixels."""
        ...
