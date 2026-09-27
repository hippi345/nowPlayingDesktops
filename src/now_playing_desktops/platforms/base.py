"""Platform abstraction for desktop wallpaper and display geometry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ScreenInfo:
    """One logical display."""

    screen_id: str
    width: int
    height: int
    is_primary: bool = False


class WallpaperPlatform(Protocol):
    """Wallpaper and display geometry for the host OS."""

    def set_wallpaper(self, path: Path, *, screen_id: str | None = None) -> None:
        """Set wallpaper on one screen or the whole desktop when ``screen_id`` is None."""
        ...

    def get_current_wallpaper(self, *, screen_id: str | None = None) -> Path | None:
        """Return the current wallpaper path for a screen, if known."""
        ...

    def get_primary_screen_size(self) -> tuple[int, int]:
        """Return primary display width and height in pixels."""
        ...

    def list_screens(self) -> list[ScreenInfo]:
        """Return connected displays in stable order."""
        ...

    def supports_per_screen_wallpaper(self) -> bool:
        """Whether distinct images can be set per ``screen_id``."""
        ...

    def capture_restore_snapshot(
        self,
        *,
        state_dir: Path | None = None,
        generated_dir: Path | None = None,
        existing_snapshot: dict[str, Any] | None = None,
        session_active: bool = False,
        recovering: bool = False,
    ) -> dict[str, Any]:
        """Serialize current wallpaper settings for later restore."""
        ...

    def apply_restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore wallpaper settings from :meth:`capture_restore_snapshot`."""
        ...
