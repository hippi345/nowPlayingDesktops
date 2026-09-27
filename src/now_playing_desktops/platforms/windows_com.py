"""Optional IDesktopWallpaper COM helpers (pywin32 or ole32 ctypes)."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

_DESKTOP_WALLPAPER_CLSID = "{C2CF3110-460E-4fc1-B9D0-8A1C0C5699CC}"
_IDESKTOP_WALLPAPER_IID = "{B92B56A9-8B55-4E70-9FE3-901FD638A9CF}"
_RPC_E_CHANGED_MODE = -2147417850

_monitor_device_names: dict[str, str] = {}
_com_available: bool | None = None
_com_probe_detail: str = ""
_com_backend: str | None = None


def register_monitor_device(monitor_id: str, device_name: str) -> None:
    if monitor_id and device_name:
        _monitor_device_names[monitor_id] = device_name


def clear_monitor_device_registry() -> None:
    _monitor_device_names.clear()


def idesktop_wallpaper_probe_detail() -> str:
    return _com_probe_detail


def _probe_pythoncom() -> tuple[bool, str]:
    try:
        import pythoncom  # type: ignore[import-untyped]

        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except pythoncom.com_error as exc:
            if int(exc.hresult) != _RPC_E_CHANGED_MODE:
                return False, f"pythoncom.CoInitializeEx failed: HRESULT=0x{int(exc.hresult) & 0xFFFFFFFF:08X} ({exc})"
        pythoncom.CoCreateInstance(
            _DESKTOP_WALLPAPER_CLSID,
            None,
            pythoncom.CLSCTX_ALL,
            _IDESKTOP_WALLPAPER_IID,
        )
        return True, "pythoncom CoCreateInstance(IDesktopWallpaper) succeeded"
    except Exception as exc:  # noqa: BLE001
        return False, f"pythoncom: {type(exc).__name__}: {exc}"


def _probe_ctypes_com() -> tuple[bool, str]:
    try:
        from now_playing_desktops.platforms import windows_com_ctypes
    except ImportError as exc:
        return False, f"ctypes COM backend unavailable: {exc}"
    return windows_com_ctypes.probe_idesktop_wallpaper_ctypes()


def idesktop_wallpaper_probe() -> tuple[bool, str]:
    """Return availability and a human-readable probe trace (for ``diag``)."""
    global _com_available, _com_probe_detail, _com_backend
    if _com_available is not None:
        return _com_available, _com_probe_detail

    if sys.platform != "win32":
        _com_available = False
        _com_probe_detail = "non-win32"
        _com_backend = None
        return False, _com_probe_detail

    py_ok, py_detail = _probe_pythoncom()
    if py_ok:
        _com_available = True
        _com_probe_detail = py_detail
        _com_backend = "pythoncom"
        return True, py_detail

    ct_ok, ct_detail = _probe_ctypes_com()
    if ct_ok:
        _com_available = True
        _com_probe_detail = f"{py_detail}; fallback {ct_detail}"
        _com_backend = "ctypes"
        return True, _com_probe_detail

    _com_available = False
    _com_probe_detail = f"{py_detail}; {ct_detail}"
    _com_backend = None
    return False, _com_probe_detail


def idesktop_wallpaper_available() -> bool:
    available, _detail = idesktop_wallpaper_probe()
    return available


def _desktop_wallpaper_interface_pythoncom():
    import pythoncom  # type: ignore[import-untyped]

    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    except pythoncom.com_error as exc:
        if int(exc.hresult) != _RPC_E_CHANGED_MODE:
            raise
    return pythoncom.CoCreateInstance(
        _DESKTOP_WALLPAPER_CLSID,
        None,
        pythoncom.CLSCTX_ALL,
        _IDESKTOP_WALLPAPER_IID,
    )


_DWPOS_FILL = 5


def set_wallpaper_for_monitor(monitor_id: str, path: str) -> None:
    if not idesktop_wallpaper_available():
        raise OSError("IDesktopWallpaper is not available")
    device = _monitor_device_names.get(monitor_id)
    if not device:
        raise OSError(f"No device name registered for monitor {monitor_id}")
    if _com_backend == "ctypes":
        from now_playing_desktops.platforms import windows_com_ctypes

        interface = windows_com_ctypes.create_desktop_wallpaper_interface()
        windows_com_ctypes.set_wallpaper_on_device(interface, device, path)
    else:
        wallpaper = _desktop_wallpaper_interface_pythoncom()
        wallpaper.SetPosition(_DWPOS_FILL)
        wallpaper.SetWallpaper(device, path)
    logger.debug(
        "IDesktopWallpaper.SetPosition(FILL) SetWallpaper(%s, %s)",
        device,
        path,
    )


def get_wallpaper_for_monitor(monitor_id: str) -> str | None:
    if not idesktop_wallpaper_available():
        return None
    device = _monitor_device_names.get(monitor_id)
    if not device:
        return None
    if _com_backend == "ctypes":
        from now_playing_desktops.platforms import windows_com_ctypes

        interface = windows_com_ctypes.create_desktop_wallpaper_interface()
        return windows_com_ctypes.get_wallpaper_for_device(interface, device)
    wallpaper = _desktop_wallpaper_interface_pythoncom()
    return str(wallpaper.GetWallpaper(device))
