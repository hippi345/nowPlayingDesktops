"""Optional IDesktopWallpaper COM helpers (pywin32 when available)."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

_DESKTOP_WALLPAPER_CLSID = "{C2CF3110-460E-4fc1-B9D0-8A1C0C5699CC}"
_IDESKTOP_WALLPAPER_IID = "{B92B56A9-8B55-4E70-9FE3-901FD638A9CF}"

_monitor_device_names: dict[str, str] = {}
_com_available: bool | None = None


def register_monitor_device(monitor_id: str, device_name: str) -> None:
    if monitor_id and device_name:
        _monitor_device_names[monitor_id] = device_name


def clear_monitor_device_registry() -> None:
    _monitor_device_names.clear()


def idesktop_wallpaper_available() -> bool:
    global _com_available
    if sys.platform != "win32":
        return False
    if _com_available is not None:
        return _com_available
    try:
        import pythoncom  # type: ignore[import-untyped]

        pythoncom.CoCreateInstance(
            _DESKTOP_WALLPAPER_CLSID,
            None,
            pythoncom.CLSCTX_ALL,
            _IDESKTOP_WALLPAPER_IID,
        )
        _com_available = True
    except Exception:
        _com_available = False
    return _com_available


def _desktop_wallpaper_interface():
    import pythoncom  # type: ignore[import-untyped]

    return pythoncom.CoCreateInstance(
        _DESKTOP_WALLPAPER_CLSID,
        None,
        pythoncom.CLSCTX_ALL,
        _IDESKTOP_WALLPAPER_IID,
    )


def set_wallpaper_for_monitor(monitor_id: str, path: str) -> None:
    if not idesktop_wallpaper_available():
        raise OSError("IDesktopWallpaper is not available")
    device = _monitor_device_names.get(monitor_id)
    if not device:
        raise OSError(f"No device name registered for monitor {monitor_id}")
    wallpaper = _desktop_wallpaper_interface()
    wallpaper.SetWallpaper(device, path)
    logger.debug("IDesktopWallpaper.SetWallpaper(%s, %s)", device, path)


def get_wallpaper_for_monitor(monitor_id: str) -> str | None:
    if not idesktop_wallpaper_available():
        return None
    device = _monitor_device_names.get(monitor_id)
    if not device:
        return None
    wallpaper = _desktop_wallpaper_interface()
    return str(wallpaper.GetWallpaper(device))
