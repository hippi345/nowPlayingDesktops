"""Linux desktop wallpaper across GNOME, KDE, and lightweight WM fallbacks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.platforms.linux_backends import (
    Backend,
    GnomeWallpaperBackend,
    KdeWallpaperBackend,
    select_wm_fallback_backend,
)
from now_playing_desktops.platforms.linux_de import (
    LinuxDesktopEnvironment,
    detect_linux_desktop_environment,
)
from now_playing_desktops.platforms.linux_screen import list_linux_screens, primary_screen_size

if sys.platform == "linux":
    _global_swaybg = None  # module-level for tests


class LinuxWallpaperPlatform:
    """Linux implementation of :class:`~now_playing_desktops.platforms.base.WallpaperPlatform`."""

    def __init__(
        self,
        *,
        de: LinuxDesktopEnvironment | None = None,
        backend: Backend | None = None,
    ) -> None:
        self._de = de if de is not None else detect_linux_desktop_environment()
        self._backend = backend if backend is not None else self._backend_for_de(self._de)

    @staticmethod
    def _backend_for_de(de: LinuxDesktopEnvironment) -> Backend:
        if de == LinuxDesktopEnvironment.GNOME:
            return GnomeWallpaperBackend()
        if de == LinuxDesktopEnvironment.KDE:
            return KdeWallpaperBackend()
        return select_wm_fallback_backend()

    def set_wallpaper(self, path: Path, *, screen_id: str | None = None) -> None:
        if screen_id is not None:
            raise NotImplementedError("Per-screen wallpapers are not supported on Linux yet")
        self._backend.set_wallpaper(path)

    def get_current_wallpaper(self, *, screen_id: str | None = None) -> Path | None:
        return self._backend.get_current_wallpaper()

    def get_primary_screen_size(self) -> tuple[int, int]:
        return primary_screen_size()

    def list_screens(self) -> list[ScreenInfo]:
        return list_linux_screens()

    def supports_per_screen_wallpaper(self) -> bool:
        return False

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
        from now_playing_desktops.wallpaper_snapshot import (
            attach_stable_copy_to_snapshot,
            should_preserve_existing_snapshot,
        )

        if should_preserve_existing_snapshot(
            existing_snapshot,
            session_active=session_active,
            recovering=recovering,
        ):
            preserved = dict(existing_snapshot or {})
            preserved.setdefault("backend", "linux")
            preserved["de"] = self._de.value
            return preserved

        snap = self._backend.capture_snapshot()
        snap["de"] = self._de.value
        dest_dir = state_dir or user_config_dir()
        raw_path = snap.get("path")
        source = Path(str(raw_path)) if raw_path else None
        return attach_stable_copy_to_snapshot(
            snap,
            state_dir=dest_dir,
            source_path=source,
            source_bytes=None,
            generated_dir=generated_dir,
        )

    def apply_restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        stable = snapshot.get("stable_path")
        if stable:
            snapshot = dict(snapshot)
            snapshot["path"] = stable
        backend_name = snapshot.get("backend")
        if backend_name == "gnome":
            self._backend = GnomeWallpaperBackend()
        elif backend_name == "kde":
            self._backend = KdeWallpaperBackend()
        elif backend_name == "feh":
            from now_playing_desktops.platforms.linux_backends import FehWallpaperBackend

            self._backend = FehWallpaperBackend()
        elif backend_name == "swaybg":
            from now_playing_desktops.platforms.linux_backends import SwaybgWallpaperBackend

            self._backend = SwaybgWallpaperBackend()
        elif backend_name == "nitrogen":
            from now_playing_desktops.platforms.linux_backends import NitrogenWallpaperBackend

            self._backend = NitrogenWallpaperBackend()
        self._backend.apply_snapshot(snapshot)


if sys.platform == "linux":
    try:
        platform = LinuxWallpaperPlatform()
    except OSError:
        platform = None  # type: ignore[assignment,misc]
else:
    platform = None  # type: ignore[assignment]
