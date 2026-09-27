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


class _MONITORINFOEXW(_MONITORINFO):
    _fields_ = [("szDevice", wintypes.WCHAR * 32)]


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
    device_name: str = ""
    rect_width: int = 0
    rect_height: int = 0
    rect_left: int = 0
    rect_top: int = 0


def monitor_device_name_from_szdevice(sz_device: object) -> str:
    """Read ``MONITORINFOEXW.szDevice`` (ctypes may expose it as ``str`` or a WCHAR buffer)."""
    if isinstance(sz_device, str):
        return sz_device
    value = getattr(sz_device, "value", sz_device)
    if isinstance(value, str):
        return value
    return str(value)


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


def _effective_dpi_for_monitor_id(monitor_id: str) -> tuple[int, int]:
    try:
        return _effective_dpi_for_hmonitor(int(monitor_id))
    except (ValueError, TypeError):
        return 96, 96


def _effective_dpi_for_hmonitor(hmonitor: int) -> tuple[int, int]:
    if sys.platform != "win32":
        return 96, 96
    try:
        shcore = ctypes.windll.shcore
        mdt_effective_dpi = 0
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        result = shcore.GetDpiForMonitor(
            hmonitor,
            mdt_effective_dpi,
            ctypes.byref(dpi_x),
            ctypes.byref(dpi_y),
        )
        if result == 0:
            return max(96, int(dpi_x.value)), max(96, int(dpi_y.value))
    except (AttributeError, OSError, TypeError):
        pass
    return 96, 96


def set_process_dpi_aware() -> None:
    from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware as _bootstrap

    _bootstrap()


def primary_screen_pixel_size() -> tuple[int, int]:
    if sys.platform != "win32" or user32 is None:
        return 1920, 1080
    set_process_dpi_aware()
    width = int(user32.GetSystemMetrics(SM_CXSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYSCREEN))
    return max(1, width), max(1, height)


def compose_canvas_pixel_size(monitors: list[MonitorInfo]) -> tuple[int, int]:
    """Pixel size for a single SPI wallpaper bitmap (virtual desktop span or one monitor)."""
    if not monitors:
        return primary_screen_pixel_size()
    if len(monitors) == 1:
        monitor = monitors[0]
        return monitor.width, monitor.height
    left = min(monitor.left for monitor in monitors)
    top = min(monitor.top for monitor in monitors)
    right = max(monitor.left + monitor.width for monitor in monitors)
    bottom = max(monitor.top + monitor.height for monitor in monitors)
    return max(1, right - left), max(1, bottom - top)


def log_monitors_for_wallpaper_render(monitors: list[MonitorInfo]) -> None:
    """Log detected monitor geometry (call after DPI awareness is enabled)."""
    if not monitors:
        logger.warning("No monitors detected for wallpaper render")
        return
    canvas_w, canvas_h = compose_canvas_pixel_size(monitors)
    for monitor in monitors:
        dpi_x, dpi_y = _effective_dpi_for_monitor_id(monitor.monitor_id)
        logger.info(
            "Monitor %s: %dx%d at (%d,%d) primary=%s effective_dpi=%dx%d",
            monitor.monitor_id,
            monitor.width,
            monitor.height,
            monitor.left,
            monitor.top,
            monitor.is_primary,
            dpi_x,
            dpi_y,
        )
    logger.info("Wallpaper compose canvas: %dx%d", canvas_w, canvas_h)


def log_wallpaper_apply_for_monitor(
    *,
    monitor: MonitorInfo,
    composed_width: int,
    composed_height: int,
    wallpaper_style: str,
) -> None:
    """Log one INFO line per monitor when applying a wallpaper (Windows diagnostics)."""
    from now_playing_desktops.platforms.windows_dpi import (
        describe_thread_dpi_awareness_context,
        enum_display_settings_pixel_size,
    )

    dpi_x, dpi_y = _effective_dpi_for_monitor_id(monitor.monitor_id)
    scale_x = dpi_x / 96.0
    scale_y = dpi_y / 96.0
    dm_pels = enum_display_settings_pixel_size(monitor.device_name) if monitor.device_name else None
    dm_w, dm_h = dm_pels if dm_pels else (None, None)
    rect_w = monitor.rect_width or monitor.width
    rect_h = monitor.rect_height or monitor.height
    awareness = describe_thread_dpi_awareness_context()
    logger.info(
        "Wallpaper apply monitor=%s device=%r rcMonitor=%dx%d dmPels=%sx%s "
        "dpi=%dx%d scale=%.2fx%.2f awareness=%s canvas=%dx%d style=%s",
        monitor.monitor_id,
        monitor.device_name,
        rect_w,
        rect_h,
        dm_w if dm_w is not None else "?",
        dm_h if dm_h is not None else "?",
        dpi_x,
        dpi_y,
        scale_x,
        scale_y,
        awareness,
        composed_width,
        composed_height,
        wallpaper_style,
    )
    if dm_w is not None and dm_h is not None and (composed_width, composed_height) != (dm_w, dm_h):
        logger.warning(
            "Composed wallpaper %dx%d does not match dmPels %dx%d for monitor %s",
            composed_width,
            composed_height,
            dm_w,
            dm_h,
            monitor.monitor_id,
        )


def monitor_info_from_win32(
    hmonitor: int,
    info: _MONITORINFO,
    *,
    fallback_width: int,
    fallback_height: int,
    device_name: str | None = None,
) -> MonitorInfo:
    from now_playing_desktops.platforms.windows_dpi import (
        enum_display_settings_monitor_geometry,
        reconcile_dm_pels_with_monitor_rect,
    )

    rect = info.rcMonitor
    rect_width, rect_height = monitor_size_from_rect(rect.left, rect.top, rect.right, rect.bottom)
    left, top = int(rect.left), int(rect.top)
    width, height = rect_width, rect_height
    dpi_x, dpi_y = _effective_dpi_for_hmonitor(int(hmonitor))
    geometry = enum_display_settings_monitor_geometry(device_name) if device_name else None
    if geometry is not None:
        dm_w, dm_h, left, top = geometry
        width, height = reconcile_dm_pels_with_monitor_rect(
            dm_width=dm_w,
            dm_height=dm_h,
            rect_width=rect_width,
            rect_height=rect_height,
            dpi_x=dpi_x,
            dpi_y=dpi_y,
        )
    else:
        safe_rect_w, safe_rect_h, _ = ensure_positive_monitor_size(
            rect_width,
            rect_height,
            fallback_width=fallback_width,
            fallback_height=fallback_height,
        )
        width, height = safe_rect_w, safe_rect_h
        if device_name:
            logger.warning(
                "EnumDisplaySettings unavailable for %r; using GetMonitorInfo rect %dx%d",
                device_name,
                width,
                height,
            )
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
    dpi_x, dpi_y = _effective_dpi_for_hmonitor(int(hmonitor))
    logger.debug(
        "Win32 monitor %s rect=%sx%s dmPels=%sx%s at (%s,%s) dpi=%sx%s primary=%s",
        hmonitor,
        rect_width,
        rect_height,
        width,
        height,
        left,
        top,
        dpi_x,
        dpi_y,
        is_primary,
    )
    return MonitorInfo(
        monitor_id=str(int(hmonitor)),
        width=width,
        height=height,
        is_primary=is_primary,
        left=left,
        top=top,
        device_name=device_name or "",
        rect_width=rect_width,
        rect_height=rect_height,
        rect_left=int(rect.left),
        rect_top=int(rect.top),
    )


def enumerate_monitors() -> list[MonitorInfo]:
    if sys.platform != "win32" or user32 is None:
        return [
            MonitorInfo(monitor_id="0", width=1920, height=1080, is_primary=True),
        ]

    set_process_dpi_aware()
    fallback_w, fallback_h = primary_screen_pixel_size()
    collected: list[MonitorInfo] = []

    _callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

    @_callback_type(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(_RECT),
        wintypes.LPARAM,
    )
    def callback(hmonitor, _hdc, _lprc_monitor, _data):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return True
        device = ""
        try:
            device = monitor_device_name_from_szdevice(info.szDevice)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not read monitor device name for hmonitor=%s: %s",
                hmonitor,
                exc,
                exc_info=True,
            )
        try:
            monitor = monitor_info_from_win32(
                int(hmonitor),
                info,
                fallback_width=fallback_w,
                fallback_height=fallback_h,
                device_name=device,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "EnumDisplayMonitors callback failed for hmonitor=%s: %s",
                hmonitor,
                exc,
                exc_info=True,
            )
            rect = info.rcMonitor
            rect_w, rect_h = monitor_size_from_rect(
                rect.left,
                rect.top,
                rect.right,
                rect.bottom,
            )
            width, height, _ = ensure_positive_monitor_size(
                rect_w,
                rect_h,
                fallback_width=fallback_w,
                fallback_height=fallback_h,
            )
            monitor = MonitorInfo(
                monitor_id=str(int(hmonitor)),
                width=width,
                height=height,
                is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                left=int(rect.left),
                top=int(rect.top),
                device_name=device,
                rect_width=rect_w,
                rect_height=rect_h,
                rect_left=int(rect.left),
                rect_top=int(rect.top),
            )
        collected.append(monitor)
        if sys.platform == "win32" and monitor.device_name:
            from now_playing_desktops.platforms import windows_com

            windows_com.register_monitor_device(monitor.monitor_id, monitor.device_name)
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
            device_name=first.device_name,
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


if sys.platform == "win32":
    set_process_dpi_aware()  # noqa: E402 — import-time bootstrap for library use
