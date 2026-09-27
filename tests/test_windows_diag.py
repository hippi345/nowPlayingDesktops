from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from now_playing_desktops.cli import main
from now_playing_desktops.platforms.windows_diag import (
    collect_windows_diag_report,
    diag_report_as_dict,
    format_windows_diag_report,
)
from now_playing_desktops.platforms.windows_monitors import MonitorInfo
from now_playing_desktops.platforms.windows_restore import WALLPAPER_STYLE_FILL


def test_reconcile_rejects_spurious_15x_dm_pels_at_96_dpi():
    from now_playing_desktops.platforms.windows_dpi import reconcile_dm_pels_with_monitor_rect

    width, height = reconcile_dm_pels_with_monitor_rect(
        dm_width=2496,
        dm_height=1664,
        rect_width=1664,
        rect_height=1109,
        dpi_x=96,
        dpi_y=96,
    )
    assert (width, height) == (1664, 1109)


def test_reconcile_keeps_matching_dm_pels_at_96_dpi():
    from now_playing_desktops.platforms.windows_dpi import reconcile_dm_pels_with_monitor_rect

    assert reconcile_dm_pels_with_monitor_rect(
        dm_width=1664,
        dm_height=1109,
        rect_width=1664,
        rect_height=1109,
        dpi_x=96,
        dpi_y=96,
    ) == (1664, 1109)


def test_monitor_info_compose_1664x1109_at_96_dpi():
    from now_playing_desktops.platforms import windows_monitors as wm

    info = wm._MONITORINFOEXW()
    info.rcMonitor = wm._RECT(0, 0, 1664, 1109)
    info.dwFlags = wm.MONITORINFOF_PRIMARY
    with (
        patch(
            "now_playing_desktops.platforms.windows_dpi.enum_display_settings_monitor_geometry",
            return_value=(1664, 1109, 0, 0),
        ),
        patch(
            "now_playing_desktops.platforms.windows_monitors._effective_dpi_for_hmonitor",
            return_value=(96, 96),
        ),
    ):
        monitor = wm.monitor_info_from_win32(
            1,
            info,
            fallback_width=1920,
            fallback_height=1080,
            device_name=r"\\.\DISPLAY1",
        )
    assert monitor.width == 1664
    assert monitor.height == 1109


def test_windows_diag_mocked_96dpi_1664x1109():
    monitors = [
        MonitorInfo(
            "65537",
            1664,
            1109,
            True,
            left=0,
            top=0,
            device_name=r"\\.\DISPLAY1",
            rect_width=1664,
            rect_height=1109,
            rect_left=0,
            rect_top=0,
        ),
    ]
    platform = MagicMock()
    platform.get_current_wallpaper.return_value = None
    with (
        patch.object(sys, "platform", "win32"),
        patch(
            "now_playing_desktops.platforms.windows_monitors.enumerate_monitors",
            return_value=monitors,
        ),
        patch(
            "now_playing_desktops.platforms.windows_dpi.enum_display_settings_monitor_geometry",
            return_value=(1664, 1109, 0, 0),
        ),
        patch(
            "now_playing_desktops.platforms.windows_monitors._effective_dpi_for_monitor_id",
            return_value=(96, 96),
        ),
        patch(
            "now_playing_desktops.platforms.windows_com.idesktop_wallpaper_available",
            return_value=True,
        ),
        patch(
            "now_playing_desktops.platforms.windows.WindowsWallpaperPlatform",
            return_value=platform,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore.read_applied_wallpaper_style",
            return_value={"wallpaper_style": "10", "tile_wallpaper": "0"},
        ),
        patch(
            "now_playing_desktops.platforms.windows_dpi.describe_thread_dpi_awareness_context",
            return_value="per-monitor-v2",
        ),
        patch("now_playing_desktops.platforms.windows_dpi.set_process_dpi_aware"),
    ):
        report = collect_windows_diag_report()
        text = format_windows_diag_report(report)

    data = diag_report_as_dict(report)
    assert data["canvas_size"] == (1664, 1109)
    assert data["style_would_write"] == WALLPAPER_STYLE_FILL
    assert data["monitors"][0]["compose_size"] == (1664, 1109)
    assert data["monitors"][0]["scale"] == (1.0, 1.0)
    assert "1.5" not in text
    assert "scale=1.00x1.00" in text
    assert "Style would write: 10" in text


def test_cli_diag_command(capsys):
    from now_playing_desktops.platforms.windows_diag import WindowsDiagReport

    fake_report = WindowsDiagReport(
        monitors=[],
        per_monitor_com=False,
        canvas_size=(1664, 1109),
        virtual_span=False,
        style_would_write="10",
        registry_wallpaper_style="10",
        registry_tile_wallpaper="0",
        current_wallpaper_path=None,
        log_file_path="/tmp/now-playing.log",
    )
    with (
        patch.object(sys, "platform", "win32"),
        patch(
            "now_playing_desktops.platforms.windows_diag.collect_windows_diag_report",
            return_value=fake_report,
        ),
        patch("now_playing_desktops.logging_setup.configure_application_logging"),
    ):
        code = main(["diag"])
    assert code == 0
    assert "1664x1109" in capsys.readouterr().out
