from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout
from now_playing_desktops.platforms.windows_monitors import (
    MonitorInfo,
    compose_canvas_pixel_size,
)
from now_playing_desktops.platforms.windows_restore import (
    TILE_WALLPAPER_OFF,
    WALLPAPER_STYLE_FILL,
    apply_windows_fill_wallpaper_style,
)
from now_playing_desktops.spotify_art import TrackPlayback
from tests.helpers import FakePlatform, make_runner, make_sample_cover

LONG_TITLE = "Long Title For Centering"


def test_compose_canvas_single_monitor_uses_monitor_size():
    monitors = [MonitorInfo("1", 1664, 1109, True, left=0, top=0)]
    assert compose_canvas_pixel_size(monitors) == (1664, 1109)


def test_compose_canvas_virtual_desktop_span():
    monitors = [
        MonitorInfo("1", 1920, 1080, True, left=0, top=0),
        MonitorInfo("2", 1280, 1024, False, left=1920, top=0),
    ]
    assert compose_canvas_pixel_size(monitors) == (3200, 1080)


@pytest.mark.parametrize("dpi", [96, 120, 144])
def test_compose_size_unchanged_at_varied_effective_dpi(dpi: int):
    monitors = [MonitorInfo("7", 1664, 1109, True, left=0, top=0)]
    with patch(
        "now_playing_desktops.platforms.windows_monitors._effective_dpi_for_hmonitor",
        return_value=(dpi, dpi),
    ):
        assert compose_canvas_pixel_size(monitors) == (1664, 1109)


def test_glass_tile_center_within_two_pixels_of_image_center():
    cover = make_sample_cover()
    width, height = 1664, 1109
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=width,
        height=height,
    )
    px0, py0, px1, py1 = layout.panel
    cx = (px0 + px1) / 2
    cy = (py0 + py1) / 2
    assert abs(cx - width / 2) <= 2
    assert abs(cy - height / 2) <= 2


def test_apply_windows_fill_wallpaper_style_writes_registry():
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg") as winreg_mock,
    ):
        apply_windows_fill_wallpaper_style()
    assert winreg_mock.CreateKey.called
    set_calls = winreg_mock.SetValueEx.call_args_list
    names = {call.args[1] for call in set_calls}
    assert "WallpaperStyle" in names
    assert "TileWallpaper" in names
    style_value = next(call.args[4] for call in set_calls if call.args[1] == "WallpaperStyle")
    tile_value = next(call.args[4] for call in set_calls if call.args[1] == "TileWallpaper")
    assert style_value == WALLPAPER_STYLE_FILL
    assert tile_value == TILE_WALLPAPER_OFF


def test_runner_render_jobs_match_primary_monitor_size(tmp_path: Path):
    platform = FakePlatform(
        wallpaper=tmp_path / "unused.jpg",
        screen=(1664, 1109),
    )
    runner = make_runner(tmp_path, platform=platform)
    jobs = runner._resolve_wallpaper_render_jobs(platform.list_screens())
    assert jobs == [(None, 1664, 1109)]


def test_compose_path_output_matches_requested_monitor_size(tmp_path: Path):
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"x")
    runner = make_runner(tmp_path, platform=platform)
    track = TrackPlayback("t1", "https://example.com/a.jpg", "Title", "Artist", True)
    with patch(
        "now_playing_desktops.runner.download_album_art",
    ) as download_mock:
        cover_path = tmp_path / "cache" / "downloads" / "t1.jpg"
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        make_sample_cover().save(cover_path)
        download_mock.side_effect = lambda *_a, **_k: None
        out = runner._compose_path(track, 1664, 1109)
    with Image.open(out) as image:
        assert image.size == (1664, 1109)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration")
def test_real_compose_matches_detected_monitor_size(tmp_path: Path):
    from now_playing_desktops.platforms.windows_monitors import enumerate_monitors

    monitors = enumerate_monitors()
    assert monitors
    primary = next(m for m in monitors if m.is_primary)
    cover = make_sample_cover()
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=primary.width,
        height=primary.height,
    )
    assert composed.size == (primary.width, primary.height)
    output = tmp_path / "monitor-sized.png"
    composed.save(output)
    with Image.open(output) as saved:
        assert saved.size == (primary.width, primary.height)
