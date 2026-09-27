"""Windows wallpaper snapshot capture and restore (stable file copy + registry)."""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

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
COLORS_KEY = r"Control Panel\Colors"
WALLPAPERS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers"

BACKGROUND_PICTURE = 0
BACKGROUND_SOLID = 1
BACKGROUND_SLIDESHOW = 2
BACKGROUND_SPOTLIGHT = 3

STABLE_WALLPAPER_BASENAME = "original-wallpaper"


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


def _spi_get_wallpaper_path() -> str | None:
    buffer = ctypes.create_unicode_buffer(_MAX_WALLPAPER_CHARS)
    if not ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETDESKWALLPAPER,
        len(buffer),
        buffer,
        0,
    ):
        logger.debug("SPI_GETDESKWALLPAPER failed (GetLastError=%s)", _get_last_error())
        return _read_reg_string(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, "Wallpaper")
    path = buffer.value.strip()
    if not path:
        return _read_reg_string(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, "Wallpaper")
    return path


def _transcoded_wallpaper_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"


def _guess_image_extension(source: Path) -> str:
    if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
        return source.suffix.lower()
    try:
        from PIL import Image

        with Image.open(source) as image:
            fmt = (image.format or "JPEG").upper()
    except OSError:
        return ".jpg"
    if fmt == "PNG":
        return ".png"
    if fmt in {"JPEG", "JPG"}:
        return ".jpg"
    return ".jpg"


def _resolve_copy_source(reported_path: Path | None) -> Path | None:
    transcoded = _transcoded_wallpaper_path()
    if transcoded.is_file():
        return transcoded
    if reported_path is not None and reported_path.is_file():
        return reported_path
    if reported_path is not None:
        expanded = Path(os.path.expandvars(str(reported_path)))
        if expanded.is_file():
            return expanded
    return None


def _copy_to_stable_path(source: Path, state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    ext = _guess_image_extension(source)
    dest = state_dir / f"{STABLE_WALLPAPER_BASENAME}{ext}"
    shutil.copy2(source, dest)
    logger.info("Copied wallpaper snapshot to stable path: %s (from %s)", dest, source)
    return dest


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
) -> dict[str, Any]:
    """Build a restore snapshot with a stable on-disk wallpaper copy."""
    style = _read_desktop_style()
    background_type = _read_background_type()
    solid_color = _read_solid_color() if background_type == BACKGROUND_SOLID else None

    primary_reported = Path(reported_path) if reported_path else None
    if (
        primary_reported
        and generated_dir
        and path_is_under_directory(primary_reported, generated_dir)
    ):
        logger.debug("Skipping capture of generated wallpaper as original: %s", primary_reported)
        primary_reported = None

    stable_path: str | None = None
    source = _resolve_copy_source(primary_reported)
    if source is not None:
        if generated_dir and path_is_under_directory(source, generated_dir):
            logger.debug("Skipping copy of generated wallpaper source: %s", source)
        else:
            stable = _copy_to_stable_path(source, state_dir)
            stable_path = str(stable.resolve())

    snapshot: dict[str, Any] = {
        "backend": "windows",
        "path": stable_path or reported_path,
        "stable_path": stable_path,
        "wallpaper_style": style["wallpaper_style"],
        "tile_wallpaper": style["tile_wallpaper"],
        "background_type": background_type,
        "solid_color": solid_color,
        "per_monitor": per_monitor,
        "monitors": {},
    }

    if per_monitor and monitor_paths:
        monitors_stable: dict[str, str] = {}
        for monitor_id, raw in monitor_paths.items():
            mon_path = Path(raw)
            if generated_dir and path_is_under_directory(mon_path, generated_dir):
                continue
            mon_source = _resolve_copy_source(mon_path)
            if mon_source is None:
                monitors_stable[monitor_id] = raw
                continue
            ext = _guess_image_extension(mon_source)
            dest = state_dir / f"{STABLE_WALLPAPER_BASENAME}-{monitor_id}{ext}"
            shutil.copy2(mon_source, dest)
            monitors_stable[monitor_id] = str(dest.resolve())
            logger.info(
                "Copied monitor %s wallpaper snapshot to %s",
                monitor_id,
                dest,
            )
        snapshot["monitors"] = monitors_stable

    logger.debug(
        "Windows restore snapshot: stable_path=%s style=%s tile=%s background_type=%s",
        stable_path,
        style["wallpaper_style"],
        style["tile_wallpaper"],
        background_type,
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

    restore_path = snapshot.get("stable_path") or snapshot.get("path")
    if not restore_path:
        logger.warning("Windows restore snapshot has no wallpaper path")
        return
    path = Path(str(restore_path))
    if not path.is_file():
        logger.warning("Windows restore wallpaper file missing: %s", path)
        return

    path_str = str(path.resolve())

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
