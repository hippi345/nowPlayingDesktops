"""Windows monitor enumeration and sizing."""

from __future__ import annotations

import sys
from dataclasses import dataclass

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    MONITORINFOF_PRIMARY = 1
else:
    user32 = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MonitorInfo:
    monitor_id: str
    width: int
    height: int
    is_primary: bool


def set_process_dpi_aware() -> None:
    import contextlib

    if sys.platform != "win32" or user32 is None:
        return
    try:
        user32.SetProcessDpiAwarenessContext(-4)
    except (AttributeError, OSError):
        with contextlib.suppress(AttributeError, OSError):
            user32.SetProcessDPIAware()


def enumerate_monitors() -> list[MonitorInfo]:
    if sys.platform != "win32" or user32 is None:
        return [
            MonitorInfo(monitor_id="0", width=1920, height=1080, is_primary=True),
        ]

    collected: list[MonitorInfo] = []

    @ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(_MONITORINFO),
        ctypes.c_double,
    )
    def callback(hmonitor, _hdc, lpmi, _data):
        info = lpmi.contents
        width = info.rcMonitor.right - info.rcMonitor.left
        height = info.rcMonitor.bottom - info.rcMonitor.top
        is_primary = bool(info.dwFlags & MONITORINFOF_PRIMARY)
        collected.append(
            MonitorInfo(
                monitor_id=str(int(hmonitor)),
                width=width,
                height=height,
                is_primary=is_primary,
            )
        )
        return 1

    user32.EnumDisplayMonitors(0, 0, callback, 0)
    if collected and not any(m.is_primary for m in collected):
        first = collected[0]
        collected[0] = MonitorInfo(
            monitor_id=first.monitor_id,
            width=first.width,
            height=first.height,
            is_primary=True,
        )
    return collected


def largest_monitor_pixel_size(monitors: list[MonitorInfo]) -> tuple[int, int]:
    if not monitors:
        return 1920, 1080
    best = monitors[0]
    best_area = best.width * best.height
    for monitor in monitors[1:]:
        area = monitor.width * monitor.height
        if area > best_area:
            best = monitor
            best_area = area
    return best.width, best.height
