"""macOS desktop wallpaper on every display."""

from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys
from pathlib import Path
from typing import Any

from now_playing_desktops.platforms.base import ScreenInfo

_PYOBJC_AVAILABLE = False
if sys.platform == "darwin":
    try:
        from AppKit import NSWorkspace  # type: ignore[import-not-found]
        from Foundation import NSURL  # type: ignore[import-not-found]

        _PYOBJC_AVAILABLE = True
    except ImportError:
        NSWorkspace = None  # type: ignore[assignment,misc]
        NSURL = None  # type: ignore[assignment,misc]


class MacOSWallpaperPlatform:
    """macOS implementation of :class:`~now_playing_desktops.platforms.base.WallpaperPlatform`."""

    def set_wallpaper(self, image_path: Path, *, screen_id: str | None = None) -> None:
        resolved = image_path.resolve()
        if screen_id is None:
            self._set_all_screens(resolved)
            return
        if _PYOBJC_AVAILABLE:
            self._set_pyobjc_screen(resolved, screen_id)
        else:
            self._set_all_screens(resolved)

    @staticmethod
    def _escape_applescript_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _set_all_screens(self, path: Path) -> None:
        if _PYOBJC_AVAILABLE:
            workspace = NSWorkspace.sharedWorkspace()
            url = NSURL.fileURLWithPath_(str(path))
            for screen in self._nsscreens():
                workspace.setDesktopImageURL_forScreen_options_error_(url, screen, None, None)
            return
        escaped = self._escape_applescript_string(str(path))
        script = (
            f'tell application "System Events" to tell every desktop to set picture to "{escaped}"'
        )
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)

    def _set_pyobjc_screen(self, path: Path, screen_id: str) -> None:
        workspace = NSWorkspace.sharedWorkspace()
        url = NSURL.fileURLWithPath_(str(path))
        for screen in self._nsscreens():
            if str(screen.hash()) == screen_id or screen.localizedName() == screen_id:
                workspace.setDesktopImageURL_forScreen_options_error_(url, screen, None, None)
                return
        raise ValueError(f"Unknown screen_id {screen_id!r}")

    def get_current_wallpaper(self, *, screen_id: str | None = None) -> Path | None:
        if _PYOBJC_AVAILABLE:
            screens = self._nsscreens()
            if screen_id is not None:
                for screen in screens:
                    if str(screen.hash()) == screen_id or screen.localizedName() == screen_id:
                        url = NSWorkspace.sharedWorkspace().desktopImageURLForScreen_(screen)
                        if url:
                            return Path(url.path())
                return None
            if screens:
                url = NSWorkspace.sharedWorkspace().desktopImageURLForScreen_(screens[0])
                if url:
                    return Path(url.path())
            return None
        if sys.platform != "darwin":
            return None
        try:
            from appscript import app
        except ImportError:
            return None
        ref = app("Finder").desktop_picture.get()
        path = str(ref.path)
        if not path:
            return None
        return Path(path)

    def get_primary_screen_size(self) -> tuple[int, int]:
        screens = self.list_screens()
        for screen in screens:
            if screen.is_primary:
                return screen.width, screen.height
        if screens:
            return screens[0].width, screens[0].height
        return _core_graphics_primary_size()

    def list_screens(self) -> list[ScreenInfo]:
        if _PYOBJC_AVAILABLE:
            result: list[ScreenInfo] = []
            for index, screen in enumerate(self._nsscreens()):
                frame = screen.frame()
                width = int(frame.size.width)
                height = int(frame.size.height)
                result.append(
                    ScreenInfo(
                        screen_id=str(screen.hash()),
                        width=width,
                        height=height,
                        is_primary=index == 0,
                    )
                )
            return result
        width, height = _core_graphics_primary_size()
        return [ScreenInfo(screen_id="primary", width=width, height=height, is_primary=True)]

    def supports_per_screen_wallpaper(self) -> bool:
        return True

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
            return dict(existing_snapshot or {"backend": "macos"})

        screens: dict[str, str] = {}
        for screen in self.list_screens():
            current = self.get_current_wallpaper(screen_id=screen.screen_id)
            if current:
                screens[screen.screen_id] = str(current)
        primary = self.get_current_wallpaper()
        snap: dict[str, Any] = {
            "backend": "macos",
            "path": str(primary) if primary else None,
            "screens": screens,
        }
        dest_dir = state_dir or user_config_dir()
        source = primary if primary and primary.is_file() else None
        return attach_stable_copy_to_snapshot(
            snap,
            state_dir=dest_dir,
            source_path=source,
            source_bytes=None,
            generated_dir=generated_dir,
        )

    def apply_restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        screens = snapshot.get("screens") or {}
        if screens:
            for screen_id, raw in screens.items():
                path = Path(raw)
                if path.is_file():
                    self.set_wallpaper(path, screen_id=screen_id)
            return
        stable = snapshot.get("stable_path")
        if stable:
            path = Path(str(stable))
            if path.is_file():
                self.set_wallpaper(path)
                return
        raw = snapshot.get("path")
        if raw:
            path = Path(raw)
            if path.is_file():
                self.set_wallpaper(path)

    @staticmethod
    def _nsscreens():
        from AppKit import NSScreen  # type: ignore[import-not-found]

        return NSScreen.screens()


def _core_graphics_primary_size() -> tuple[int, int]:
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
