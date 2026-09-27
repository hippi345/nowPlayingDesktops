"""Windows wallpaper snapshot capture and restore (stable file copy + registry)."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from now_playing_desktops.wallpaper_snapshot import (
    STABLE_WALLPAPER_BASENAME,
    attach_stable_copy_to_snapshot,
    bytes_match_render,
    collect_render_content_hashes,
    copy_file_to_stable_wallpaper,
    file_digest,
    path_is_generated_render,
    should_preserve_existing_snapshot,
)
from now_playing_desktops.wallpaper_state import path_is_under_directory

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02
_MAX_WALLPAPER_CHARS = 260

DESKTOP_KEY = r"Control Panel\Desktop"
WALLPAPER_STYLE_FILL = "10"
TILE_WALLPAPER_OFF = "0"
COLORS_KEY = r"Control Panel\Colors"
WALLPAPERS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers"
IE_DESKTOP_KEY = r"Software\Microsoft\Internet Explorer\Desktop\General"

BACKGROUND_PICTURE = 0
BACKGROUND_SOLID = 1
BACKGROUND_SLIDESHOW = 2
BACKGROUND_SPOTLIGHT = 3


def _read_reg_string(root: int, subkey: str, name: str) -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(root, subkey) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    if value is None:
        return None
    return str(value)


def _write_reg_string(root: int, subkey: str, name: str, value: str) -> None:
    if winreg is None:
        return
    with winreg.CreateKey(root, subkey) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _write_reg_dword(root: int, subkey: str, name: str, value: int) -> None:
    if winreg is None:
        return
    with winreg.CreateKey(root, subkey) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def _get_last_error() -> int:
    return int(ctypes.windll.kernel32.GetLastError())


def _transcoded_wallpaper_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"


def _cached_files_wallpaper_path() -> Path | None:
    appdata = os.environ.get("APPDATA", "")
    cached_dir = Path(appdata) / "Microsoft" / "Windows" / "Themes" / "CachedFiles"
    if not cached_dir.is_dir():
        return None
    candidates = [p for p in cached_dir.iterdir() if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _wallpaper_source_from_registry() -> Path | None:
    if winreg is None:
        return None
    raw = _read_reg_string(winreg.HKEY_CURRENT_USER, IE_DESKTOP_KEY, "WallpaperSource")
    if not raw:
        return None
    expanded = Path(os.path.expandvars(raw))
    if expanded.is_file():
        return expanded
    return None


def iter_windows_wallpaper_source_candidates(
    reported_path: Path | None,
) -> Iterator[Path]:
    """Yield wallpaper file candidates in Windows source priority order."""
    registry_source = _wallpaper_source_from_registry()
    if registry_source is not None:
        yield registry_source
    cached = _cached_files_wallpaper_path()
    if cached is not None:
        yield cached
    yield _transcoded_wallpaper_path()
    if reported_path is not None:
        if reported_path.is_file():
            yield reported_path
        else:
            expanded = Path(os.path.expandvars(str(reported_path)))
            if expanded.is_file():
                yield expanded


def _pick_wallpaper_source_bytes(
    *,
    state_dir: Path,
    generated_dir: Path | None,
    reported_path: Path | None,
    render_digests: set[str],
) -> tuple[Path | None, bytes | None]:
    seen: set[str] = set()
    for candidate in iter_windows_wallpaper_source_candidates(reported_path):
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if not candidate.is_file():
            continue
        if path_is_generated_render(
            candidate,
            generated_dir=generated_dir,
            state_dir=state_dir,
        ):
            logger.debug("Skipping generated render wallpaper source: %s", candidate)
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        if bytes_match_render(data, render_digests):
            logger.debug("Skipping render digest wallpaper source: %s", candidate)
            continue
        logger.info("Selected Windows wallpaper snapshot source: %s", candidate)
        return candidate, data
    return None, None


def apply_windows_fill_wallpaper_style() -> None:
    """Force Fill (not Center/Tile) so the bitmap matches the monitor size."""
    if winreg is None:
        return
    _write_reg_string(
        winreg.HKEY_CURRENT_USER,
        DESKTOP_KEY,
        "WallpaperStyle",
        WALLPAPER_STYLE_FILL,
    )
    _write_reg_string(
        winreg.HKEY_CURRENT_USER,
        DESKTOP_KEY,
        "TileWallpaper",
        TILE_WALLPAPER_OFF,
    )
    logger.debug(
        "Set WallpaperStyle=%s TileWallpaper=%s before applying wallpaper",
        WALLPAPER_STYLE_FILL,
        TILE_WALLPAPER_OFF,
    )


def _read_desktop_style() -> dict[str, str]:
    if winreg is None:
        return {"wallpaper_style": "10", "tile_wallpaper": "0"}
    return {
        "wallpaper_style": _read_reg_string(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, "WallpaperStyle")
        or "10",
        "tile_wallpaper": _read_reg_string(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, "TileWallpaper")
        or "0",
    }


def _read_background_type() -> int:
    if winreg is None:
        return BACKGROUND_PICTURE
    raw = _read_reg_string(winreg.HKEY_CURRENT_USER, WALLPAPERS_KEY, "BackgroundType")
    if raw is None:
        return BACKGROUND_PICTURE
    try:
        return int(raw)
    except ValueError:
        return BACKGROUND_PICTURE


def _read_solid_color() -> str | None:
    return _read_reg_string(winreg.HKEY_CURRENT_USER, COLORS_KEY, "Background")


def capture_windows_restore_snapshot(
    *,
    state_dir: Path,
    generated_dir: Path | None,
    reported_path: str | None,
    per_monitor: bool,
    monitor_paths: dict[str, str],
    existing_snapshot: dict[str, Any] | None = None,
    session_active: bool = False,
    recovering: bool = False,
) -> dict[str, Any]:
    """Build a restore snapshot with a stable on-disk wallpaper copy."""
    if should_preserve_existing_snapshot(
        existing_snapshot,
        session_active=session_active,
        recovering=recovering,
    ):
        logger.info(
            "Preserving existing wallpaper snapshot: %s",
            existing_snapshot.get("stable_path"),
        )
        preserved = dict(existing_snapshot or {})
        preserved.setdefault("backend", "windows")
        return preserved

    style = _read_desktop_style()
    background_type = _read_background_type()
    solid_color = _read_solid_color() if background_type == BACKGROUND_SOLID else None
    render_digests = collect_render_content_hashes(generated_dir)

    primary_reported = Path(reported_path) if reported_path else None
    if (
        primary_reported
        and generated_dir
        and path_is_under_directory(primary_reported, generated_dir)
    ):
        primary_reported = None

    snapshot: dict[str, Any] = {
        "backend": "windows",
        "path": None,
        "stable_path": None,
        "content_hash": None,
        "wallpaper_style": style["wallpaper_style"],
        "tile_wallpaper": style["tile_wallpaper"],
        "background_type": background_type,
        "solid_color": solid_color,
        "per_monitor": per_monitor,
        "monitors": {},
    }

    if background_type != BACKGROUND_SOLID:
        source_path, source_bytes = _pick_wallpaper_source_bytes(
            state_dir=state_dir,
            generated_dir=generated_dir,
            reported_path=primary_reported,
            render_digests=render_digests,
        )
        snapshot = attach_stable_copy_to_snapshot(
            snapshot,
            state_dir=state_dir,
            source_path=source_path,
            source_bytes=source_bytes,
            generated_dir=generated_dir,
            render_digests=render_digests,
        )

    if per_monitor and monitor_paths:
        monitors_stable: dict[str, str] = {}
        for monitor_id, raw in monitor_paths.items():
            mon_path = Path(raw)
            if generated_dir and path_is_under_directory(mon_path, generated_dir):
                continue
            if path_is_generated_render(
                mon_path,
                generated_dir=generated_dir,
                state_dir=state_dir,
            ):
                continue
            if not mon_path.is_file():
                continue
            try:
                data = mon_path.read_bytes()
            except OSError:
                continue
            if bytes_match_render(data, render_digests):
                continue
            dest, digest = copy_file_to_stable_wallpaper(
                mon_path,
                state_dir,
                basename=f"{STABLE_WALLPAPER_BASENAME}-{monitor_id}",
            )
            monitors_stable[monitor_id] = str(dest.resolve())
            logger.info(
                "Copied monitor %s wallpaper snapshot to %s (digest=%s)",
                monitor_id,
                dest,
                digest,
            )
        snapshot["monitors"] = monitors_stable

    logger.debug(
        "Windows restore snapshot: stable_path=%s content_hash=%s",
        snapshot.get("stable_path"),
        snapshot.get("content_hash"),
    )
    return snapshot


def _apply_spi_wallpaper(path_str: str) -> None:
    logger.info(
        "Restoring wallpaper via SystemParametersInfoW(SPI_SETDESKWALLPAPER): %s",
        path_str,
    )
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER,
        0,
        path_str,
        SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
    )
    if not ok:
        err = _get_last_error()
        raise OSError(
            f"SystemParametersInfoW(SPI_SETDESKWALLPAPER) failed for {path_str!r} "
            f"(GetLastError={err})"
        )


def _restore_desktop_style(snapshot: dict[str, Any]) -> None:
    style = snapshot.get("wallpaper_style")
    tile = snapshot.get("tile_wallpaper")
    if style is not None:
        _write_reg_string(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, "WallpaperStyle", str(style))
    if tile is not None:
        _write_reg_string(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, "TileWallpaper", str(tile))


def _restore_solid_color(rgb: str) -> None:
    _write_reg_string(winreg.HKEY_CURRENT_USER, COLORS_KEY, "Background", rgb)
    _write_reg_dword(winreg.HKEY_CURRENT_USER, WALLPAPERS_KEY, "BackgroundType", BACKGROUND_SOLID)
    _write_reg_string(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, "Wallpaper", "")
    logger.info("Restored solid desktop color: %s", rgb)


def _notify_background_type_restored(background_type: int) -> None:
    if background_type == BACKGROUND_SLIDESHOW:
        logger.warning(
            "Restored a static wallpaper image. Re-enable slideshow in "
            "Settings > Personalization > Background if you use a slideshow."
        )
    elif background_type == BACKGROUND_SPOTLIGHT:
        logger.warning(
            "Restored a static wallpaper image. Re-enable Windows Spotlight in "
            "Settings > Personalization > Background if you use Spotlight."
        )


def apply_windows_restore_snapshot(
    snapshot: dict[str, Any],
    *,
    set_wallpaper_on_monitor: Any,
    set_wallpaper_primary: Any,
) -> None:
    """Re-apply wallpaper and registry fields from ``snapshot``."""
    background_type = int(snapshot.get("background_type", BACKGROUND_PICTURE))
    solid_color = snapshot.get("solid_color")

    if background_type == BACKGROUND_SOLID and solid_color:
        _restore_solid_color(str(solid_color))
        return

    restore_path = snapshot.get("stable_path")
    if not restore_path:
        logger.warning("Windows restore snapshot has no stable_path; refusing to restore")
        return
    path = Path(str(restore_path))
    if not path.is_file():
        logger.warning("Windows restore wallpaper file missing: %s", path)
        return

    path_str = str(path.resolve())
    expected_hash = snapshot.get("content_hash")
    if expected_hash:
        actual = file_digest(path.read_bytes())
        if actual != expected_hash:
            logger.warning(
                "Stable wallpaper digest mismatch before restore (expected %s, got %s)",
                expected_hash,
                actual,
            )

    if snapshot.get("per_monitor") and snapshot.get("monitors"):
        for monitor_id, raw in snapshot["monitors"].items():
            mon_path = Path(raw)
            if mon_path.is_file():
                set_wallpaper_on_monitor(str(mon_path.resolve()), monitor_id)
        _restore_desktop_style(snapshot)
        if background_type in {BACKGROUND_SLIDESHOW, BACKGROUND_SPOTLIGHT}:
            _write_reg_dword(
                winreg.HKEY_CURRENT_USER,
                WALLPAPERS_KEY,
                "BackgroundType",
                background_type,
            )
            _notify_background_type_restored(background_type)
        return

    _apply_spi_wallpaper(path_str)
    _restore_desktop_style(snapshot)

    if background_type in {BACKGROUND_SLIDESHOW, BACKGROUND_SPOTLIGHT}:
        _write_reg_dword(
            winreg.HKEY_CURRENT_USER,
            WALLPAPERS_KEY,
            "BackgroundType",
            background_type,
        )
        _notify_background_type_restored(background_type)


def read_stable_wallpaper_bytes(snapshot: dict[str, Any]) -> bytes:
    """Return bytes from the snapshot stable copy (for tests and verification)."""
    stable = snapshot.get("stable_path")
    if not stable:
        raise ValueError("snapshot has no stable_path")
    return Path(str(stable)).read_bytes()
