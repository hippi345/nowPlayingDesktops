from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform
from now_playing_desktops.platforms.windows_monitors import (
    MonitorInfo,
    ensure_positive_monitor_size,
    enumerate_monitors,
    largest_monitor_pixel_size,
    monitor_size_from_rect,
)
from now_playing_desktops.spotify_art import TrackPlayback
from tests.helpers import FakePlatform, make_runner, make_test_cover

PLAYING = TrackPlayback(
    track_id="track-log-once",
    art_url="https://example.com/art.jpg",
    title="Song",
    artist="Artist",
    is_playing=True,
)


@pytest.mark.parametrize(
    ("left", "top", "right", "bottom", "width", "height"),
    [
        (0, 0, 1664, 1109, 1664, 1109),
        (0, 0, 3840, 2160, 3840, 2160),
        (-1920, 0, 0, 1080, 1920, 1080),
        (0, -1080, 1920, 0, 1920, 1080),
    ],
)
def test_monitor_size_from_rect_realistic_layouts(left, top, right, bottom, width, height):
    assert monitor_size_from_rect(left, top, right, bottom) == (width, height)


def test_monitor_size_mixed_dpi_pair():
    primary = monitor_size_from_rect(0, 0, 2560, 1440)
    secondary = monitor_size_from_rect(2560, 0, 4480, 1080)
    assert primary == (2560, 1440)
    assert secondary == (1920, 1080)


def test_ensure_positive_monitor_size_substitutes_invalid():
    width, height, substituted = ensure_positive_monitor_size(
        1109,
        -1664,
        fallback_width=1664,
        fallback_height=1109,
    )
    assert substituted is True
    assert (width, height) == (1664, 1109)


def test_ensure_positive_monitor_size_keeps_valid():
    assert ensure_positive_monitor_size(1920, 1080, fallback_width=800, fallback_height=600) == (
        1920,
        1080,
        False,
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


def test_monitor_info_from_win32_invalid_rect_falls_back():
    from now_playing_desktops.platforms import windows_monitors as wm

    info = wm._MONITORINFO()
    info.rcMonitor = wm._RECT(0, 1664, 1109, 0)
    info.dwFlags = wm.MONITORINFOF_PRIMARY
    monitor = wm.monitor_info_from_win32(
        1,
        info,
        fallback_width=1664,
        fallback_height=1109,
    )
    assert monitor.width == 1664
    assert monitor.height == 1109


def test_enumerate_monitors_uses_get_monitor_info_not_lprect():
    if sys.platform != "win32":
        pytest.skip("EnumDisplayMonitors callback requires win32")
    import ctypes

    from now_playing_desktops.platforms import windows_monitors as wm

    fake_user32 = MagicMock()
    rect = wm._RECT(0, 0, 1664, 1109)

    def get_info(_hmon, byref_info):
        byref_info.contents.rcMonitor = rect
        byref_info.contents.dwFlags = wm.MONITORINFOF_PRIMARY
        return True

    fake_user32.GetMonitorInfoW.side_effect = get_info
    fake_user32.GetSystemMetrics.side_effect = lambda metric: 1664 if metric == 0 else 1109

    def fake_enum(_hdc, _clip, callback, _data):
        callback(7, 0, ctypes.pointer(rect), 0)
        return True

    fake_user32.EnumDisplayMonitors.side_effect = fake_enum

    with (
        patch("now_playing_desktops.platforms.windows_monitors.user32", fake_user32),
        patch("now_playing_desktops.platforms.windows_monitors.set_process_dpi_aware"),
    ):
        monitors = enumerate_monitors()

    assert len(monitors) == 1
    assert monitors[0].width == 1664
    assert monitors[0].height == 1109
    assert monitors[0].is_primary is True
    fake_user32.GetMonitorInfoW.assert_called_once()


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
        patch(
            "now_playing_desktops.platforms.windows_restore._transcoded_wallpaper_path",
            return_value=tmp_path / "missing-transcoded",
        ),
    ):
        snap = platform.capture_restore_snapshot(state_dir=tmp_path / "state")
    stable = snap.get("stable_path") or snap["path"]
    assert stable
    assert Path(stable).is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration")
def test_real_monitor_enumeration_and_compose(tmp_path):
    from now_playing_desktops.composer import compose_wallpaper, save_wallpaper

    monitors = enumerate_monitors()
    assert monitors
    for monitor in monitors:
        assert monitor.width > 0
        assert monitor.height > 0

    target = max(monitors, key=lambda item: item.width * item.height)
    cover = make_test_cover()
    composed = compose_wallpaper(
        cover,
        title="Now Playing",
        artist="Artist",
        width=target.width,
        height=target.height,
    )
    output = tmp_path / "composed.png"
    save_wallpaper(composed, output)
    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_error_logged_once_per_track(tmp_path: Path, caplog):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=PLAYING,
        ),
        patch.object(
            runner,
            "_apply_wallpaper_for_track",
            side_effect=ValueError("bad size"),
        ),
        caplog.at_level(logging.ERROR),
    ):
        runner.apply_playback_once()
        runner.apply_playback_once()

    error_records = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR and "Failed to update wallpaper" in record.message
    ]
    assert len(error_records) == 1
