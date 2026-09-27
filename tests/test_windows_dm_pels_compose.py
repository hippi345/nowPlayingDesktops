from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from now_playing_desktops.platforms import windows_monitors as wm
from now_playing_desktops.platforms.windows_monitors import (
    MonitorInfo,
    compose_canvas_pixel_size,
    monitor_info_from_win32,
)
from now_playing_desktops.platforms.windows_restore import (
    WALLPAPER_STYLE_CENTER,
    WALLPAPER_STYLE_FILL,
    WALLPAPER_STYLE_SPAN,
    apply_windows_span_wallpaper_style,
    apply_windows_wallpaper_style_for_image,
)
from now_playing_desktops.verification.wallpaper_analysis import assert_no_backdrop_band_edges
from now_playing_desktops.verification.windows_display import simulate_wallpaper_on_display
from tests.helpers import ARTIFACTS_DIR, make_sample_cover


def test_compose_size_from_dm_pels_when_rc_monitor_is_logical():
    info = wm._MONITORINFOEXW()
    info.rcMonitor = wm._RECT(0, 0, 1664, 1109)
    info.dwFlags = wm.MONITORINFOF_PRIMARY
    device = r"\\.\DISPLAY1"
    with patch(
        "now_playing_desktops.platforms.windows_dpi.enum_display_settings_monitor_geometry",
        return_value=(2496, 1664, 0, 0),
    ):
        monitor = monitor_info_from_win32(
            9,
            info,
            fallback_width=1920,
            fallback_height=1080,
            device_name=device,
        )
    assert monitor.width == 2496
    assert monitor.height == 1664
    assert monitor.rect_width == 1664
    assert monitor.rect_height == 1109


def test_compose_size_when_logical_and_physical_match_at_100_percent():
    info = wm._MONITORINFOEXW()
    info.rcMonitor = wm._RECT(0, 0, 1920, 1080)
    info.dwFlags = wm.MONITORINFOF_PRIMARY
    with patch(
        "now_playing_desktops.platforms.windows_dpi.enum_display_settings_monitor_geometry",
        return_value=(1920, 1080, 0, 0),
    ):
        monitor = monitor_info_from_win32(
            1,
            info,
            fallback_width=800,
            fallback_height=600,
            device_name=r"\\.\DISPLAY1",
        )
    assert monitor.width == 1920
    assert monitor.height == 1080
    assert monitor.rect_width == 1920


def test_virtual_canvas_uses_dm_position_for_mixed_dpi_layout():
    monitors = [
        MonitorInfo("1", 1920, 1080, True, left=0, top=0, device_name=r"\\.\DISPLAY1"),
        MonitorInfo("2", 2560, 1440, False, left=-2560, top=-200, device_name=r"\\.\DISPLAY2"),
    ]
    assert compose_canvas_pixel_size(monitors) == (4480, 1440)


@pytest.mark.parametrize(
    ("image_w", "image_h", "mon_w", "mon_h", "expected"),
    [
        (2496, 1664, 2496, 1664, WALLPAPER_STYLE_FILL),
        (1664, 1109, 2496, 1664, WALLPAPER_STYLE_FILL),
    ],
)
def test_wallpaper_style_never_center(image_w, image_h, mon_w, mon_h, expected):
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg"),
    ):
        style = apply_windows_wallpaper_style_for_image(
            image_width=image_w,
            image_height=image_h,
            monitor_width=mon_w,
            monitor_height=mon_h,
        )
    assert style == expected
    assert style != WALLPAPER_STYLE_CENTER


def test_span_fallback_still_uses_style_22():
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg") as winreg_mock,
    ):
        apply_windows_span_wallpaper_style()
    style_value = next(
        call.args[4]
        for call in winreg_mock.SetValueEx.call_args_list
        if call.args[1] == "WallpaperStyle"
    )
    assert style_value == WALLPAPER_STYLE_SPAN


def test_laptop_center_mismatch_simulation_artifact_and_fill_fix():
    from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout

    cover = make_sample_cover()
    logical_w, logical_h = 1664, 1109
    physical_w, physical_h = 2496, 1664
    logical_image = compose_wallpaper(
        cover,
        title="Long Title For Centering",
        artist="Artist",
        width=logical_w,
        height=logical_h,
    )
    physical_image = compose_wallpaper(
        cover,
        title="Long Title For Centering",
        artist="Artist",
        width=physical_w,
        height=physical_h,
    )
    before = simulate_wallpaper_on_display(
        logical_image,
        display_width=physical_w,
        display_height=physical_h,
        wallpaper_style=WALLPAPER_STYLE_CENTER,
    )
    after = simulate_wallpaper_on_display(
        physical_image,
        display_width=physical_w,
        display_height=physical_h,
        wallpaper_style=WALLPAPER_STYLE_FILL,
    )
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    before.save(ARTIFACTS_DIR / "sim-laptop-before-center.png")
    after.save(ARTIFACTS_DIR / "sim-laptop-after-fill.png")

    # Center on a smaller bitmap leaves black borders (~67% area coverage).
    black_pixels = sum(1 for pixel in before.getdata() if pixel == (0, 0, 0))
    total = physical_w * physical_h
    assert black_pixels / total > 0.25

    layout = plan_wallpaper_layout(
        cover,
        title="Long Title For Centering",
        artist="Artist",
        width=physical_w,
        height=physical_h,
    )
    assert_no_backdrop_band_edges(after, cover, layout=layout)
    after_black = sum(1 for pixel in after.getdata() if pixel == (0, 0, 0))
    assert after_black / total < 0.02

    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg"),
    ):
        style = apply_windows_wallpaper_style_for_image(
            image_width=logical_w,
            image_height=logical_h,
            monitor_width=physical_w,
            monitor_height=physical_h,
        )
    assert style == WALLPAPER_STYLE_FILL
