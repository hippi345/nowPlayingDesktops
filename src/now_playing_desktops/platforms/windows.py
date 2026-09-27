"""Windows desktop wallpaper via SystemParametersInfo and optional per-monitor COM."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path
from typing import Any

from now_playing_desktops.platforms.base import ScreenInfo

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02
SM_CXSCREEN = 0
SM_CYSCREEN = 1
_MAX_WALLPAPER_CHARS = 260


class WindowsWallpaperPlatform:
    """Windows implementation of :class:`~now_playing_desktops.platforms.base.WallpaperPlatform`."""

    def __init__(self) -> None:
        if sys.platform == "win32":
            from now_playing_desktops.platforms.windows_monitors import set_process_dpi_aware

            set_process_dpi_aware()
        from now_playing_desktops.platforms.windows_com import idesktop_wallpaper_available

        self._per_monitor = sys.platform == "win32" and idesktop_wallpaper_available()

    def set_wallpaper(self, image_path: Path, *, screen_id: str | None = None) -> None:
        from now_playing_desktops.platforms.windows_monitors import enumerate_monitors
        from now_playing_desktops.platforms.windows_restore import (
            apply_windows_fill_wallpaper_style,
            apply_windows_span_wallpaper_style,
        )

        path_str = str(image_path.resolve())
        if screen_id is not None and self._per_monitor:
            apply_windows_fill_wallpaper_style()
            _set_wallpaper_on_monitor(path_str, screen_id)
            return
        monitors = enumerate_monitors() if sys.platform == "win32" else []
        if screen_id is None and len(monitors) > 1:
            apply_windows_span_wallpaper_style()
        else:
            apply_windows_fill_wallpaper_style()
        if not ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            path_str,
            SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
        ):
            err = int(ctypes.windll.kernel32.GetLastError())
            raise OSError(f"SystemParametersInfoW failed for {path_str} (GetLastError={err})")

    def get_current_wallpaper(self, *, screen_id: str | None = None) -> Path | None:
        if screen_id is not None and self._per_monitor:
            path = _get_wallpaper_for_monitor(screen_id)
            if path:
                return Path(path)
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
        if sys.platform != "win32":
            return 1920, 1080
        from now_playing_desktops.platforms.windows_monitors import (
            enumerate_monitors,
            largest_monitor_pixel_size,
        )

        monitors = enumerate_monitors()
        for monitor in monitors:
            if monitor.is_primary:
                return monitor.width, monitor.height
        return largest_monitor_pixel_size(monitors)

    def list_screens(self) -> list[ScreenInfo]:
        if sys.platform != "win32":
            return [ScreenInfo(screen_id="0", width=1920, height=1080, is_primary=True)]
        from now_playing_desktops.platforms.windows_monitors import enumerate_monitors

        return [
            ScreenInfo(
                screen_id=m.monitor_id,
                width=m.width,
                height=m.height,
                is_primary=m.is_primary,
                left=m.left,
                top=m.top,
            )
            for m in enumerate_monitors()
        ]

    def supports_per_screen_wallpaper(self) -> bool:
        return self._per_monitor

    def capture_restore_snapshot(
        self,
        *,
        state_dir: Path | None = None,
        generated_dir: Path | None = None,
        existing_snapshot: dict[str, Any] | None = None,
        session_active: bool = False,
        recovering: bool = False,
    ) -> dict[str, Any]:
        from now_playing_desktops.config import user_config_dir
        from now_playing_desktops.platforms.windows_restore import capture_windows_restore_snapshot

        monitors: dict[str, str] = {}
        if self._per_monitor:
            for screen in self.list_screens():
                current = self.get_current_wallpaper(screen_id=screen.screen_id)
                if current:
                    monitors[screen.screen_id] = str(current)
        primary = self.get_current_wallpaper()
        dest_dir = state_dir or user_config_dir()
        return capture_windows_restore_snapshot(
            state_dir=dest_dir,
            generated_dir=generated_dir,
            reported_path=str(primary) if primary else None,
            per_monitor=self._per_monitor,
            monitor_paths=monitors,
            existing_snapshot=existing_snapshot,
            session_active=session_active,
            recovering=recovering,
        )

    def apply_restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        from now_playing_desktops.platforms.windows_restore import apply_windows_restore_snapshot

        apply_windows_restore_snapshot(
            snapshot,
            set_wallpaper_on_monitor=_set_wallpaper_on_monitor,
            set_wallpaper_primary=lambda path: self.set_wallpaper(path),
        )

    def restore_original_wallpaper(self, snapshot: dict[str, Any]) -> None:
        """Alias used in tests; delegates to :meth:`apply_restore_snapshot`."""
        self.apply_restore_snapshot(snapshot)


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


def _set_wallpaper_on_monitor(path_str: str, monitor_id: str) -> None:
    from now_playing_desktops.platforms.windows_com import set_wallpaper_for_monitor

    set_wallpaper_for_monitor(monitor_id, path_str)


def _get_wallpaper_for_monitor(monitor_id: str) -> str | None:
    from now_playing_desktops.platforms.windows_com import get_wallpaper_for_monitor

    return get_wallpaper_for_monitor(monitor_id)


def set_desktop_wallpaper(image_path: Path) -> None:
    """Set the Windows desktop background to ``image_path`` (legacy helper)."""
    WindowsWallpaperPlatform().set_wallpaper(image_path)


if sys.platform == "win32":
    platform = WindowsWallpaperPlatform()
else:
    platform = None  # type: ignore[assignment]
