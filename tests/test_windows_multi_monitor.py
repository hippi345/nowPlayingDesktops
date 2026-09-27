from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from now_playing_desktops.platforms import windows as win_platform
from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform
from now_playing_desktops.platforms.windows_monitors import MonitorInfo, compose_canvas_pixel_size
from now_playing_desktops.platforms.windows_restore import (
    TILE_WALLPAPER_OFF,
    WALLPAPER_STYLE_SPAN,
    apply_windows_span_wallpaper_style,
)
from now_playing_desktops.platforms.windows_virtual_compose import (
    compose_virtual_desktop_wallpaper,
    draw_monitor_outlines,
    monitor_rect_on_canvas,
    panel_centers_on_virtual_canvas,
    virtual_desktop_origin,
)
from tests.helpers import ARTIFACTS_DIR, make_sample_cover

LONG_TITLE = "Long Title For Centering"

# Asymmetric mixed-DPI layout from verification (physical pixel sizes).
MIXED_MONITORS = [
    MonitorInfo("1", 1920, 1080, True, left=0, top=0, device_name=r"\\.\DISPLAY1"),
    MonitorInfo("2", 2560, 1440, False, left=-2560, top=-200, device_name=r"\\.\DISPLAY2"),
]


def test_compose_canvas_asymmetric_negative_origin():
    assert compose_canvas_pixel_size(MIXED_MONITORS) == (4480, 1440)


def test_each_monitor_tile_centered_within_three_pixels_on_virtual_canvas():
    cover = make_sample_cover()
    centers = panel_centers_on_virtual_canvas(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        monitors=MIXED_MONITORS,
    )
    origin_left, origin_top = virtual_desktop_origin(MIXED_MONITORS)
    assert len(centers) == 2
    for cx, cy, monitor in centers:
        x0, y0, x1, y1 = monitor_rect_on_canvas(
            monitor,
            origin_left=origin_left,
            origin_top=origin_top,
        )
        monitor_cx = (x0 + x1) / 2
        monitor_cy = (y0 + y1) / 2
        assert abs(cx - monitor_cx) <= 3.0
        assert abs(cy - monitor_cy) <= 3.0


def test_single_centered_tile_on_full_span_is_not_per_monitor_centered():
    cover = make_sample_cover()
    canvas_w, canvas_h = compose_canvas_pixel_size(MIXED_MONITORS)
    from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout

    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=canvas_w,
        height=canvas_h,
    )
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=canvas_w,
        height=canvas_h,
    )
    px0, py0, px1, py1 = layout.panel
    cx = (px0 + px1) / 2
    cy = (py0 + py1) / 2
    assert composed.size == (canvas_w, canvas_h)
    origin_left, origin_top = virtual_desktop_origin(MIXED_MONITORS)
    for monitor in MIXED_MONITORS:
        x0, y0, x1, y1 = monitor_rect_on_canvas(
            monitor,
            origin_left=origin_left,
            origin_top=origin_top,
        )
        monitor_cx = (x0 + x1) / 2
        monitor_cy = (y0 + y1) / 2
        assert abs(cx - monitor_cx) > 50 or abs(cy - monitor_cy) > 50


def test_virtual_desktop_compose_artifact_with_monitor_outlines():
    cover = make_sample_cover()
    composed = compose_virtual_desktop_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        monitors=MIXED_MONITORS,
    )
    outlined = draw_monitor_outlines(composed, MIXED_MONITORS)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    outlined.save(ARTIFACTS_DIR / "win-two-monitor-per-monitor.png")
    assert composed.size == (4480, 1440)


def test_apply_windows_span_wallpaper_style_writes_registry():
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
    tile_value = next(
        call.args[4]
        for call in winreg_mock.SetValueEx.call_args_list
        if call.args[1] == "TileWallpaper"
    )
    assert style_value == WALLPAPER_STYLE_SPAN
    assert tile_value == TILE_WALLPAPER_OFF


def test_set_wallpaper_virtual_span_uses_span_style(tmp_path: Path):
    image = tmp_path / "span.png"
    Image.new("RGB", (4480, 1440), (30, 30, 30)).save(image)
    fake_windll = MagicMock()
    fake_windll.user32.SystemParametersInfoW.return_value = 1
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_monitors.set_process_dpi_aware"),
        patch("now_playing_desktops.platforms.windows_restore.winreg"),
        patch(
            "now_playing_desktops.platforms.windows_com.idesktop_wallpaper_available",
            return_value=False,
        ),
        patch.object(
            WindowsWallpaperPlatform,
            "_monitor_pixel_size_for_screen",
            return_value=(4480, 1440),
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore.apply_windows_span_wallpaper_style",
        ) as span_mock,
        patch.object(win_platform.ctypes, "windll", fake_windll, create=True),
    ):
        platform = WindowsWallpaperPlatform()
        platform.set_wallpaper(image, virtual_desktop_span=True)
    span_mock.assert_called_once()


def test_runner_spi_fallback_uses_virtual_span_job(tmp_path: Path):
    from tests.helpers import FakePlatform, make_runner

    screens = [
        ScreenInfo("1", 1920, 1080, True, left=0, top=0),
        ScreenInfo("2", 2560, 1440, False, left=-2560, top=-200),
    ]
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"x")
    runner = make_runner(tmp_path, platform=platform)
    with (
        patch.object(sys, "platform", "win32"),
        patch.object(platform, "list_screens", return_value=screens),
    ):
        jobs = runner._resolve_wallpaper_render_jobs(screens)
    assert jobs == [(None, 4480, 1440, True)]


def test_runner_com_path_uses_per_monitor_jobs(tmp_path: Path):
    from tests.helpers import FakePlatform, make_runner

    screens = [
        ScreenInfo("1", 1920, 1080, True),
        ScreenInfo("2", 2560, 1440, False),
    ]
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    runner = make_runner(tmp_path, platform=platform)
    with (
        patch.object(platform, "list_screens", return_value=screens),
        patch.object(platform, "supports_per_screen_wallpaper", return_value=True),
    ):
        jobs = runner._resolve_wallpaper_render_jobs(screens)
    assert jobs == [
        ("1", 1920, 1080, False),
        ("2", 2560, 1440, False),
    ]


def test_per_monitor_com_set_wallpaper_per_screen(tmp_path: Path):
    image = tmp_path / "bg.jpg"
    Image.new("RGB", (64, 64), (40, 80, 120)).save(image, format="JPEG")
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_monitors.set_process_dpi_aware"),
        patch("now_playing_desktops.platforms.windows_restore.winreg"),
        patch(
            "now_playing_desktops.platforms.windows_com.idesktop_wallpaper_available",
            return_value=True,
        ),
        patch(
            "now_playing_desktops.platforms.windows_com.register_monitor_device",
        ),
        patch.object(
            WindowsWallpaperPlatform,
            "_monitor_pixel_size_for_screen",
            return_value=(64, 64),
        ),
        patch(
            "now_playing_desktops.platforms.windows._set_wallpaper_on_monitor",
        ) as set_mock,
    ):
        platform = WindowsWallpaperPlatform()
        platform.set_wallpaper(image, screen_id="5")
    set_mock.assert_called_once()
