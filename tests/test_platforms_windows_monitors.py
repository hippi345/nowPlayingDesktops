from __future__ import annotations

import sys
from unittest.mock import patch

from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform
from now_playing_desktops.platforms.windows_monitors import (
    MonitorInfo,
    largest_monitor_pixel_size,
)


def test_largest_monitor_pixel_size_picks_biggest_area():
    monitors = [
        MonitorInfo("1", 1920, 1080, True),
        MonitorInfo("2", 2560, 1440, False),
    ]
    assert largest_monitor_pixel_size(monitors) == (2560, 1440)


def test_windows_list_screens_from_enumerate():
    platform = WindowsWallpaperPlatform()
    monitors = [
        MonitorInfo("10", 1920, 1080, True),
        MonitorInfo("20", 1280, 1024, False),
    ]
    with (
        patch.object(sys, "platform", "win32"),
        patch(
            "now_playing_desktops.platforms.windows_monitors.enumerate_monitors",
            return_value=monitors,
        ),
    ):
        screens = platform.list_screens()
    assert len(screens) == 2
    assert screens[0].screen_id == "10"


def test_windows_per_monitor_set_when_com_available(tmp_path):
    image = tmp_path / "bg.jpg"
    image.write_bytes(b"x")
    with (
        patch.object(sys, "platform", "win32"),
        patch(
            "now_playing_desktops.platforms.windows_com.idesktop_wallpaper_available",
            return_value=True,
        ),
        patch(
            "now_playing_desktops.platforms.windows._set_wallpaper_on_monitor",
        ) as set_mock,
    ):
        platform = WindowsWallpaperPlatform()
        platform.set_wallpaper(image, screen_id="5")
    set_mock.assert_called_once()


def test_windows_capture_restore_snapshot_includes_monitors(tmp_path):
    platform = WindowsWallpaperPlatform()
    primary = tmp_path / "wall.jpg"
    primary.write_bytes(b"w")
    with (
        patch.object(platform, "_per_monitor", True),
        patch.object(platform, "list_screens", return_value=[]),
        patch.object(platform, "get_current_wallpaper", return_value=primary),
    ):
        snap = platform.capture_restore_snapshot()
    assert snap["path"] == str(primary)
