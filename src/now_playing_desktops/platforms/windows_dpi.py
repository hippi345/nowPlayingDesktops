"""Windows process DPI awareness and physical monitor pixel sizing."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# https://learn.microsoft.com/en-us/windows/win32/hidpi/dpi-awareness-context
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

PROCESS_DPI_UNAWARE = 0
PROCESS_SYSTEM_DPI_AWARE = 1
PROCESS_PER_MONITOR_DPI_AWARE = 2

ENUM_CURRENT_SETTINGS = -1
# Win32 display ``DEVMODEW`` size expected by ``EnumDisplaySettingsW`` (bytes).
DEVMODEW_DISPLAY_SIZE = 220
DM_POSITION = 0x00000020
DM_PELSWIDTH = 0x80000
DM_PELSHEIGHT = 0x100000

DPI_AWARENESS_UNAWARE = 0
DPI_AWARENESS_SYSTEM_AWARE = 1
DPI_AWARENESS_PER_MONITOR_AWARE = 2
DPI_AWARENESS_PER_MONITOR_AWARE_V2 = 3

class DEVMODEW(ctypes.Structure):
    """Win32 ``DEVMODEW`` layout for ``EnumDisplaySettingsW`` (display fields)."""

    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", wintypes.LONG),
        ("dmPositionY", wintypes.LONG),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", wintypes.SHORT),
        ("dmDuplex", wintypes.SHORT),
        ("dmYResolution", wintypes.SHORT),
        ("dmTTOption", wintypes.SHORT),
        ("dmCollate", wintypes.SHORT),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
    ]


if sys.platform == "win32":
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None  # type: ignore[assignment]
    gdi32 = None  # type: ignore[assignment]
    kernel32 = None  # type: ignore[assignment]


@dataclass(frozen=True)
class DpiAwarenessBootstrapResult:
    thread_awareness_before: str
    thread_awareness_after: str
    process_awareness_before: int
    process_awareness_after: int
    successful_method: str | None
    attempt_log: tuple[str, ...]
    manifest_likely: bool


def _get_last_error() -> int:
    if kernel32 is None:
        return 0
    return int(kernel32.GetLastError())


def bootstrap_process_dpi_awareness() -> DpiAwarenessBootstrapResult:
    """Set DPI awareness and return a diagnostic trace (for ``diag`` and logging)."""
    before_thread = describe_thread_dpi_awareness_context()
    before_process = get_process_dpi_awareness()
    attempts: list[str] = []
    successful: str | None = None
    manifest_likely = before_process != PROCESS_DPI_UNAWARE or before_thread not in {
        "unaware",
        "unaware(process)",
    }

    if sys.platform != "win32" or user32 is None:
        return DpiAwarenessBootstrapResult(
            thread_awareness_before=before_thread,
            thread_awareness_after=before_thread,
            process_awareness_before=before_process,
            process_awareness_after=before_process,
            successful_method="non-win32 stub",
            attempt_log=tuple(attempts),
            manifest_likely=manifest_likely,
        )

    try:
        if user32.SetProcessDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            successful = "SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)"
            attempts.append(f"{successful}=ok")
        else:
            err = _get_last_error()
            attempts.append(
                f"SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2) failed GetLastError={err}",
            )
    except (AttributeError, OSError, TypeError) as exc:
        attempts.append(f"SetProcessDpiAwarenessContext unavailable: {exc}")

    if successful is None:
        try:
            shcore = ctypes.windll.shcore
            hr = shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
            if hr == 0:
                successful = "SetProcessDpiAwareness(PER_MONITOR_DPI_AWARE)"
                attempts.append(f"{successful}=ok")
            else:
                attempts.append(f"SetProcessDpiAwareness failed HRESULT=0x{hr & 0xFFFFFFFF:08X}")
        except (AttributeError, OSError, TypeError) as exc:
            attempts.append(f"SetProcessDpiAwareness unavailable: {exc}")

    if successful is None:
        try:
            if user32.SetProcessDPIAware():
                successful = "SetProcessDPIAware()"
                attempts.append(f"{successful}=ok")
            else:
                attempts.append(f"SetProcessDPIAware() failed GetLastError={_get_last_error()}")
        except (AttributeError, OSError, TypeError) as exc:
            attempts.append(f"SetProcessDPIAware unavailable: {exc}")

    after_thread = describe_thread_dpi_awareness_context()
    after_process = get_process_dpi_awareness()
    if successful is None and after_thread != "unaware":
        successful = "already-aware (manifest or prior bootstrap)"
        manifest_likely = True
    elif successful is not None and before_process != PROCESS_DPI_UNAWARE and successful.startswith(
        "SetProcess",
    ):
        manifest_likely = False

    return DpiAwarenessBootstrapResult(
        thread_awareness_before=before_thread,
        thread_awareness_after=after_thread,
        process_awareness_before=before_process,
        process_awareness_after=after_process,
        successful_method=successful,
        attempt_log=tuple(attempts),
        manifest_likely=manifest_likely,
    )


def set_process_dpi_aware() -> None:
    """Enable per-monitor DPI awareness (v2 when available) before any size queries."""
    result = bootstrap_process_dpi_awareness()
    if result.successful_method:
        logger.debug("DPI bootstrap: %s", result.successful_method)
    for line in result.attempt_log:
        logger.debug("DPI bootstrap attempt: %s", line)


def get_process_dpi_awareness() -> int:
    """Return process DPI awareness (0 unaware, 1 system, 2 per-monitor)."""
    if sys.platform != "win32":
        return PROCESS_PER_MONITOR_DPI_AWARE
    try:
        shcore = ctypes.windll.shcore
        awareness = wintypes.DWORD()
        if shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness)) == 0:
            return int(awareness.value)
    except (AttributeError, OSError, TypeError):
        pass
    return PROCESS_DPI_UNAWARE


def is_process_dpi_aware() -> bool:
    return get_process_dpi_awareness() != PROCESS_DPI_UNAWARE


def describe_thread_dpi_awareness_context() -> str:
    """Human-readable DPI awareness for the calling thread (for diagnostics)."""
    if sys.platform != "win32" or user32 is None:
        return "per-monitor-v2 (non-win32 stub)"
    labels = {
        DPI_AWARENESS_UNAWARE: "unaware",
        DPI_AWARENESS_SYSTEM_AWARE: "system",
        DPI_AWARENESS_PER_MONITOR_AWARE: "per-monitor",
        DPI_AWARENESS_PER_MONITOR_AWARE_V2: "per-monitor-v2",
    }
    try:
        context = user32.GetThreadDpiAwarenessContext()
        awareness = int(user32.GetAwarenessFromDpiAwarenessContext(context))
        return labels.get(awareness, f"unknown({awareness})")
    except (AttributeError, OSError, TypeError):
        proc = get_process_dpi_awareness()
        proc_labels = {
            PROCESS_DPI_UNAWARE: "unaware(process)",
            PROCESS_SYSTEM_DPI_AWARE: "system(process)",
            PROCESS_PER_MONITOR_DPI_AWARE: "per-monitor(process)",
        }
        return proc_labels.get(proc, f"unknown-process({proc})")


def _enum_display_settings_devmode(device_name: str) -> DEVMODEW | None:
    if sys.platform != "win32" or user32 is None:
        return None
    devmode = DEVMODEW()
    devmode.dmSize = DEVMODEW_DISPLAY_SIZE
    devmode.dmDriverExtra = 0
    if not user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
        return None
    return devmode


def enum_display_settings_pixel_size(device_name: str) -> tuple[int, int] | None:
    """Return ``dmPelsWidth`` x ``dmPelsHeight`` for a monitor device, if available."""
    devmode = _enum_display_settings_devmode(device_name)
    if devmode is None:
        return None
    if not (devmode.dmFields & DM_PELSWIDTH) or not (devmode.dmFields & DM_PELSHEIGHT):
        return None
    width = int(devmode.dmPelsWidth)
    height = int(devmode.dmPelsHeight)
    if width <= 0 or height <= 0:
        return None
    return width, height


def enum_display_settings_monitor_geometry(
    device_name: str,
) -> tuple[int, int, int, int] | None:
    """
    Return physical width, height, and virtual-desktop origin from ``EnumDisplaySettingsW``.

    Uses ``dmPelsWidth`` / ``dmPelsHeight`` and ``dmPosition`` — not ``GetMonitorInfo`` rects.
    """
    devmode = _enum_display_settings_devmode(device_name)
    if devmode is None:
        return None
    if not (devmode.dmFields & DM_PELSWIDTH) or not (devmode.dmFields & DM_PELSHEIGHT):
        return None
    width = int(devmode.dmPelsWidth)
    height = int(devmode.dmPelsHeight)
    if width <= 0 or height <= 0:
        return None
    if devmode.dmFields & DM_POSITION:
        left = int(devmode.dmPositionX)
        top = int(devmode.dmPositionY)
    else:
        left = 0
        top = 0
    return width, height, left, top


def reconcile_dm_pels_with_monitor_rect(
    *,
    dm_width: int,
    dm_height: int,
    rect_width: int,
    rect_height: int,
    dpi_x: int,
    dpi_y: int,
) -> tuple[int, int]:
    """
    Keep ``dmPels`` as ground truth unless it looks like a spurious 1.5× upscale.

    On the owner's 96 DPI / 1664×1109 laptop, a bad size/DPI path produced
    ``dmPels`` or scaled sizes at exactly 1.5× ``rcMonitor`` (2496×1664), which
    then displayed with ~75%% horizontal tile center after shell fill/stretch.
    """
    if rect_width <= 0 or rect_height <= 0:
        return dm_width, dm_height
    if dm_width == rect_width and dm_height == rect_height:
        return dm_width, dm_height
    if dpi_x == 96 and dpi_y == 96:
        ratio_w = dm_width / rect_width
        ratio_h = dm_height / rect_height
        if abs(ratio_w - 1.5) < 0.02 and abs(ratio_h - 1.5) < 0.02:
            logger.warning(
                "Ignoring dmPels %dx%d (~1.5× rcMonitor %dx%d at 96 DPI); using rcMonitor",
                dm_width,
                dm_height,
                rect_width,
                rect_height,
            )
            return rect_width, rect_height
    return dm_width, dm_height


def physical_pixel_size_from_rect(
    *,
    rect_width: int,
    rect_height: int,
    dpi_x: int,
    dpi_y: int,
    native_size: tuple[int, int] | None,
) -> tuple[int, int]:
    """
    Legacy helper for tests. Wallpaper compose uses ``EnumDisplaySettings`` only.

    Do not multiply by ``dpi/96`` when the monitor rect is already in physical
    pixels (the common per-monitor v2 case at 100%% scale).
    """
    if rect_width <= 0 or rect_height <= 0:
        return max(1, rect_width), max(1, rect_height)

    if native_size is not None:
        return native_size

    if not is_process_dpi_aware() and (dpi_x, dpi_y) != (96, 96):
        scaled = (
            max(1, round(rect_width * dpi_x / 96)),
            max(1, round(rect_height * dpi_y / 96)),
        )
        if scaled != (rect_width, rect_height):
            logger.info(
                "DPI-unaware monitor rect %dx%d scaled to %dx%d (dpi=%dx%d)",
                rect_width,
                rect_height,
                scaled[0],
                scaled[1],
                dpi_x,
                dpi_y,
            )
            return scaled

    return rect_width, rect_height


def simulate_top_left_scale_center_offset(
    *,
    image_width: int,
    image_height: int,
    display_width: int,
    display_height: int,
    tile_center_x: float,
) -> float:
    """
    Model Windows stretching a bitmap from the origin when sizes differ.

    Used in tests to explain the ~75%% horizontal center shift at 150%% scaling.
    """
    if image_width <= 0 or image_height <= 0:
        return tile_center_x
    scale_x = display_width / image_width
    return tile_center_x * scale_x
