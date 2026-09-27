"""Windows display/wallpaper diagnostics (no Spotify required)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from now_playing_desktops.logging_setup import log_file_path

if TYPE_CHECKING:
    from now_playing_desktops.platforms.windows_monitors import MonitorInfo


@dataclass(frozen=True)
class MonitorDiagRow:
    monitor_id: str
    device_name: str
    rc_monitor: tuple[int, int, int, int]
    rc_monitor_size: tuple[int, int]
    dm_pels_size: tuple[int, int] | None
    dm_position: tuple[int, int] | None
    dpi_x: int
    dpi_y: int
    scale_x: float
    scale_y: float
    awareness: str
    compose_width: int
    compose_height: int


@dataclass(frozen=True)
class WindowsDiagReport:
    monitors: list[MonitorDiagRow]
    per_monitor_com: bool
    canvas_size: tuple[int, int]
    virtual_span: bool
    style_would_write: str
    registry_wallpaper_style: str
    registry_tile_wallpaper: str
    current_wallpaper_path: str | None
    log_file_path: str
    autostart_run_command: str | None = None
    run_lock_available: bool = True
    run_lock_holder: str | None = None


def collect_windows_diag_report() -> WindowsDiagReport:
    if sys.platform != "win32":
        return WindowsDiagReport(
            monitors=[],
            per_monitor_com=False,
            canvas_size=(1920, 1080),
            virtual_span=False,
            style_would_write="10",
            registry_wallpaper_style="?",
            registry_tile_wallpaper="?",
            current_wallpaper_path=None,
            log_file_path=str(log_file_path()),
        )

    from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform
    from now_playing_desktops.platforms.windows_com import idesktop_wallpaper_available
    from now_playing_desktops.platforms.windows_dpi import describe_thread_dpi_awareness_context
    from now_playing_desktops.platforms.windows_monitors import (
        compose_canvas_pixel_size,
        enumerate_monitors,
    )
    from now_playing_desktops.platforms.windows_restore import (
        WALLPAPER_STYLE_FILL,
        WALLPAPER_STYLE_SPAN,
        read_applied_wallpaper_style,
    )

    set_process_dpi_aware()
    monitors = enumerate_monitors()
    awareness = describe_thread_dpi_awareness_context()
    rows: list[MonitorDiagRow] = []
    for monitor in monitors:
        rows.append(_monitor_row(monitor, awareness))

    per_monitor = idesktop_wallpaper_available()
    virtual_span = len(monitors) > 1 and not per_monitor
    canvas_w, canvas_h = compose_canvas_pixel_size(monitors)
    style = WALLPAPER_STYLE_SPAN if virtual_span else WALLPAPER_STYLE_FILL

    platform = WindowsWallpaperPlatform()
    current = platform.get_current_wallpaper()
    reg = read_applied_wallpaper_style()
    from now_playing_desktops.platforms.autostart import read_windows_autostart_command
    from now_playing_desktops.single_instance import probe_run_lock_held

    lock_status = probe_run_lock_held()
    autostart_cmd = read_windows_autostart_command()

    return WindowsDiagReport(
        monitors=rows,
        per_monitor_com=per_monitor,
        canvas_size=(canvas_w, canvas_h),
        virtual_span=virtual_span,
        style_would_write=style,
        registry_wallpaper_style=reg["wallpaper_style"],
        registry_tile_wallpaper=reg["tile_wallpaper"],
        current_wallpaper_path=str(current) if current else None,
        log_file_path=str(log_file_path()),
        autostart_run_command=autostart_cmd,
        run_lock_available=lock_status.acquired,
        run_lock_holder=lock_status.holder_description,
    )


def _monitor_row(monitor: MonitorInfo, awareness: str) -> MonitorDiagRow:
    from now_playing_desktops.platforms.windows_dpi import enum_display_settings_monitor_geometry
    from now_playing_desktops.platforms.windows_monitors import _effective_dpi_for_monitor_id

    geo = (
        enum_display_settings_monitor_geometry(monitor.device_name) if monitor.device_name else None
    )
    dm_size = (geo[0], geo[1]) if geo else None
    dm_pos = (geo[2], geo[3]) if geo else None
    dpi_x, dpi_y = _effective_dpi_for_monitor_id(monitor.monitor_id)
    rect_w = monitor.rect_width or monitor.width
    rect_h = monitor.rect_height or monitor.height
    return MonitorDiagRow(
        monitor_id=monitor.monitor_id,
        device_name=monitor.device_name,
        rc_monitor=(
            monitor.rect_left,
            monitor.rect_top,
            monitor.rect_left + rect_w,
            monitor.rect_top + rect_h,
        ),
        rc_monitor_size=(rect_w, rect_h),
        dm_pels_size=dm_size,
        dm_position=dm_pos,
        dpi_x=dpi_x,
        dpi_y=dpi_y,
        scale_x=dpi_x / 96.0,
        scale_y=dpi_y / 96.0,
        awareness=awareness,
        compose_width=monitor.width,
        compose_height=monitor.height,
    )


def set_process_dpi_aware() -> None:
    from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware as _bootstrap

    _bootstrap()


def format_windows_diag_report(report: WindowsDiagReport) -> str:
    lines: list[str] = []
    lines.append("now-playing Windows diagnostics")
    lines.append(f"IDesktopWallpaper per-monitor: {report.per_monitor_com}")
    lines.append(f"Log file: {report.log_file_path}")
    for row in report.monitors:
        dm = f"{row.dm_pels_size[0]}x{row.dm_pels_size[1]}" if row.dm_pels_size else "unavailable"
        pos = f"({row.dm_position[0]},{row.dm_position[1]})" if row.dm_position else "(?,?)"
        lines.append(
            f"Monitor {row.monitor_id} device={row.device_name!r} "
            f"rcMonitor={row.rc_monitor_size[0]}x{row.rc_monitor_size[1]} "
            f"dmPels={dm} dmPosition={pos} "
            f"dpi={row.dpi_x}x{row.dpi_y} scale={row.scale_x:.2f}x{row.scale_y:.2f} "
            f"awareness={row.awareness} compose={row.compose_width}x{row.compose_height}",
        )
    lines.append(
        f"Canvas would compose: {report.canvas_size[0]}x{report.canvas_size[1]} "
        f"virtual_span={report.virtual_span}",
    )
    lines.append(f"Style would write: {report.style_would_write}")
    lines.append(
        f"Registry WallpaperStyle={report.registry_wallpaper_style} "
        f"TileWallpaper={report.registry_tile_wallpaper}",
    )
    lines.append(f"Current wallpaper: {report.current_wallpaper_path or '(none)'}")
    if report.autostart_run_command is not None:
        lines.append(f"Autostart Run entry: {report.autostart_run_command}")
    else:
        lines.append("Autostart Run entry: (not registered)")
    if report.run_lock_available:
        lines.append("Run lock: available (no other instance detected)")
    else:
        lines.append(
            f"Run lock: held by {report.run_lock_holder or 'another instance'}",
        )
    return "\n".join(lines)


def diag_report_as_dict(report: WindowsDiagReport) -> dict[str, Any]:
    """Structured report for tests."""
    return {
        "monitors": [
            {
                "monitor_id": row.monitor_id,
                "device_name": row.device_name,
                "rc_monitor_size": row.rc_monitor_size,
                "dm_pels_size": row.dm_pels_size,
                "compose_size": (row.compose_width, row.compose_height),
                "dpi": (row.dpi_x, row.dpi_y),
                "scale": (row.scale_x, row.scale_y),
            }
            for row in report.monitors
        ],
        "canvas_size": report.canvas_size,
        "style_would_write": report.style_would_write,
    }
