"""IDesktopWallpaper via ``ole32`` (no pywin32 required)."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":
    raise ImportError("windows_com_ctypes is Windows-only")

ole32 = ctypes.OleDLL("ole32")
kernel32 = ctypes.windll.kernel32

CLSID_DESKTOP_WALLPAPER = "{C2CF3110-460E-4fc1-B9D0-8A1C0C5699CC}"
IID_IDESKTOP_WALLPAPER = "{B92B56A9-8B55-4E70-9FE3-901FD638A9CF}"

CLSCTX_ALL = 0x17
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = 0x80010106
S_OK = 0
DWPOS_FILL = 5

_VTABLE_SET_WALLPAPER = 3
_VTABLE_SET_POSITION = 8
_VTABLE_GET_WALLPAPER = 4

_com_initialized = False


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _hresult_string(hr: int) -> str:
    if hr == 0:
        return "S_OK"
    if hr < 0:
        return f"HRESULT=0x{hr & 0xFFFFFFFF:08X}"
    return f"HRESULT={hr}"


def _guid_from_string(value: str) -> GUID:
    guid = GUID()
    hr = ole32.CLSIDFromString(value, ctypes.byref(guid))
    if hr < 0:
        raise OSError(f"CLSIDFromString failed for {value!r}: {_hresult_string(hr)}")
    return guid


def _ensure_com_apartment() -> None:
    global _com_initialized
    if _com_initialized:
        return
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr < 0 and hr != RPC_E_CHANGED_MODE:
        raise OSError(f"CoInitializeEx failed: {_hresult_string(hr)}")
    _com_initialized = True


def _com_method(interface: int, slot: int, restype, argtypes):
    iface = ctypes.c_void_p(interface)
    vtable = ctypes.cast(iface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    vtable_entries = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))
    prototype = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return prototype(vtable_entries[slot])


def _create_desktop_wallpaper() -> int:
    _ensure_com_apartment()
    clsid = _guid_from_string(CLSID_DESKTOP_WALLPAPER)
    iid = _guid_from_string(IID_IDESKTOP_WALLPAPER)
    interface = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(clsid),
        None,
        CLSCTX_ALL,
        ctypes.byref(iid),
        ctypes.byref(interface),
    )
    if hr < 0:
        raise OSError(f"CoCreateInstance(IDesktopWallpaper) failed: {_hresult_string(hr)}")
    return interface.value


def probe_idesktop_wallpaper_ctypes() -> tuple[bool, str]:
    try:
        interface = _create_desktop_wallpaper()
        if interface:
            return True, "CoCreateInstance(IDesktopWallpaper) via ole32 succeeded"
    except OSError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    return False, "CoCreateInstance returned null interface"


def create_desktop_wallpaper_interface() -> int:
    return _create_desktop_wallpaper()


def set_wallpaper_on_device(interface: int, device: str, path: str) -> None:
    set_position = _com_method(interface, _VTABLE_SET_POSITION, ctypes.c_long, [ctypes.c_int])
    hr = set_position(interface, DWPOS_FILL)
    if hr < 0:
        raise OSError(f"IDesktopWallpaper.SetPosition failed: {_hresult_string(hr)}")
    set_wallpaper = _com_method(
        interface,
        _VTABLE_SET_WALLPAPER,
        ctypes.c_long,
        [wintypes.LPCWSTR, wintypes.LPCWSTR],
    )
    hr = set_wallpaper(interface, device, path)
    if hr < 0:
        raise OSError(f"IDesktopWallpaper.SetWallpaper failed: {_hresult_string(hr)}")


def get_wallpaper_for_device(interface: int, device: str) -> str:
    get_wallpaper = _com_method(
        interface,
        _VTABLE_GET_WALLPAPER,
        ctypes.c_long,
        [wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPCWSTR)],
    )
    out = wintypes.LPCWSTR()
    hr = get_wallpaper(interface, device, ctypes.byref(out))
    if hr < 0:
        raise OSError(f"IDesktopWallpaper.GetWallpaper failed: {_hresult_string(hr)}")
    return str(out.value if out.value else "")
