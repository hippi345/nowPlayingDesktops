"""Windows monitor enumeration and sizing."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


MONITORINFOF_PRIMARY = 1
SM_CXSCREEN = 0
SM_CYSCREEN = 1

if sys.platform == "win32":
    user32 = ctypes.windll.user32
else:
    user32 = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MonitorInfo:
    monitor_id: str
    width: int
    height: int
    is_primary: bool
    left: int = 0
    top: int = 0


def monitor_size_from_rect(left: int, top: int, right: int, bottom: int) -> tuple[int, int]:
    """Return pixel width and height from a Win32 RECT (origin may be negative)."""
    return right - left, bottom - top


def ensure_positive_monitor_size(
    width: int,
    height: int,
    *,
    fallback_width: int,
    fallback_height: int,
) -> tuple[int, int, bool]:
    """Return a positive size, substituting fallback metrics when needed."""
    if width > 0 and height > 0:
        return width, height, False
    fw = max(1, fallback_width)
    fh = max(1, fallback_height)
    return fw, fh, True


def set_process_dpi_aware() -> None:
    import contextlib

    if sys.platform != "win32" or user32 is None:
        return
    try:
        user32.SetProcessDpiAwarenessContext(-4)
        return
    except (AttributeError, OSError, TypeError):
        pass
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    with contextlib.suppress(AttributeError, OSError):
        user32.SetProcessDPIAware()


def primary_screen_pixel_size() -> tuple[int, int]:
    if sys.platform != "win32" or user32 is None:
        return 1920, 1080
    width = int(user32.GetSystemMetrics(SM_CXSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYSCREEN))
    return max(1, width), max(1, height)


def monitor_info_from_win32(
    hmonitor: int,
    info: _MONITORINFO,
    *,
    fallback_width: int,
    fallback_height: int,
) -> MonitorInfo:
    rect = info.rcMonitor
    width, height = monitor_size_from_rect(rect.left, rect.top, rect.right, rect.bottom)
    width, height, substituted = ensure_positive_monitor_size(
        width,
        height,
        fallback_width=fallback_width,
        fallback_height=fallback_height,
    )
    if substituted:
        logger.warning(
            "Invalid monitor size for %s (rect=%s,%s,%s,%s); using primary screen %sx%s",
            hmonitor,
            rect.left,
            rect.top,
            rect.right,
            rect.bottom,
            width,
            height,
        )
    is_primary = bool(info.dwFlags & MONITORINFOF_PRIMARY)
    return MonitorInfo(
        monitor_id=str(int(hmonitor)),
        width=width,
        height=height,
        is_primary=is_primary,
        left=rect.left,
        top=rect.top,
    )


def enumerate_monitors() -> list[MonitorInfo]:
    if sys.platform != "win32" or user32 is None:
        return [
            MonitorInfo(monitor_id="0", width=1920, height=1080, is_primary=True),
        ]

    set_process_dpi_aware()
    fallback_w, fallback_h = primary_screen_pixel_size()
    collected: list[MonitorInfo] = []

    @ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(_RECT),
        wintypes.LPARAM,
    )
    def callback(hmonitor, _hdc, _lprc_monitor, _data):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return True
        collected.append(
            monitor_info_from_win32(
                int(hmonitor),
                info,
                fallback_width=fallback_w,
                fallback_height=fallback_h,
            )
        )
        return True

    user32.EnumDisplayMonitors(0, 0, callback, 0)
    if not collected:
        collected.append(
            MonitorInfo(
                monitor_id="0",
                width=fallback_w,
                height=fallback_h,
                is_primary=True,
            )
        )
    elif not any(m.is_primary for m in collected):
        first = collected[0]
        collected[0] = MonitorInfo(
            monitor_id=first.monitor_id,
            width=first.width,
            height=first.height,
            is_primary=True,
            left=first.left,
            top=first.top,
        )
    return collected


def largest_monitor_pixel_size(monitors: list[MonitorInfo]) -> tuple[int, int]:
    if not monitors:
        return primary_screen_pixel_size()
    best = monitors[0]
    best_area = best.width * best.height
    for monitor in monitors[1:]:
        area = monitor.width * monitor.height
        if area > best_area:
            best = monitor
            best_area = area
    return best.width, best.height
