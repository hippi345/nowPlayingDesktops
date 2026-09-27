from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from now_playing_desktops.composer import (
    compose_wallpaper,
    plan_wallpaper_layout,
    render_backdrop,
    save_wallpaper,
)
from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware
from now_playing_desktops.platforms.windows_restore import (
    WALLPAPER_STYLE_CENTER,
    read_applied_wallpaper_style,
)
from now_playing_desktops.spotify_art import TrackPlayback
from now_playing_desktops.verification.wallpaper_analysis import (
    assert_glass_panel_present,
    assert_no_backdrop_band_edges,
    assert_tile_centered,
    assert_tile_fully_visible,
    tile_centering_from_layout,
)
from now_playing_desktops.verification.windows_display import (
    simulate_dpi_unaware_fill_from_origin,
    simulate_wallpaper_on_display,
)
from tests.helpers import ARTIFACTS_DIR, make_runner, make_sample_cover

LONG_TITLE = "Long Title For Centering"
PLAYING = TrackPlayback(
    track_id="desktop-test",
    art_url="https://example.com/art.jpg",
    title=LONG_TITLE,
    artist="Test Artist",
    is_playing=True,
)


def _assert_displayed_wallpaper(
    wallpaper: Image.Image,
    *,
    cover: Image.Image,
    title: str,
    artist: str,
    display_width: int,
    display_height: int,
    wallpaper_style: str,
) -> None:
    displayed = simulate_wallpaper_on_display(
        wallpaper,
        display_width=display_width,
        display_height=display_height,
        wallpaper_style=wallpaper_style,
    )
    layout = plan_wallpaper_layout(
        cover,
        title=title,
        artist=artist,
        width=wallpaper.width,
        height=wallpaper.height,
    )
    if wallpaper_style == WALLPAPER_STYLE_CENTER and wallpaper.size == (
        display_width,
        display_height,
    ):
        backdrop = render_backdrop(cover, display_width, display_height)
        assert_glass_panel_present(displayed, layout, backdrop)
        assert_no_backdrop_band_edges(displayed, cover, layout=layout)
    centering = tile_centering_from_layout(
        layout,
        screen_width=display_width,
        screen_height=display_height,
    )
    assert_tile_centered(centering, tolerance_px=6.0)
    assert_tile_fully_visible(
        layout,
        screen_width=display_width,
        screen_height=display_height,
        margin_px=4,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Requires interactive Windows desktop session")
def test_windows_desktop_apply_and_display_simulation(tmp_path: Path):
    import ctypes

    import mss

    from now_playing_desktops.platforms import windows as win32_wallpaper
    from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform
    from now_playing_desktops.platforms.windows_monitors import enumerate_monitors

    set_process_dpi_aware()
    monitors = enumerate_monitors()
    primary = next(item for item in monitors if item.is_primary)
    cover = make_sample_cover()
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=primary.width,
        height=primary.height,
    )
    image_path = tmp_path / "wallpaper.png"
    save_wallpaper(composed, image_path)

    platform = WindowsWallpaperPlatform()
    runner = make_runner(tmp_path, platform=platform)
    runner.startup = MagicMock()  # type: ignore[method-assign]
    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.download_album_art",
            side_effect=lambda *_a, **_k: None,
        ),
        patch.object(runner, "_compose_path", return_value=image_path),
    ):
        runner.apply_playback_once()

    path_str = str(image_path.resolve())
    ok = ctypes.windll.user32.SystemParametersInfoW(
        win32_wallpaper.SPI_SETDESKWALLPAPER,
        0,
        path_str,
        win32_wallpaper.SPIF_UPDATEINIFILE | win32_wallpaper.SPIF_SENDWININICHANGE,
    )
    assert ok, "SPI_SETDESKWALLPAPER failed"
    time.sleep(2.0)
    ctypes.windll.user32.UpdatePerUserSystemParameters(1, True)

    buffer = ctypes.create_unicode_buffer(win32_wallpaper._MAX_WALLPAPER_CHARS)
    assert ctypes.windll.user32.SystemParametersInfoW(
        win32_wallpaper.SPI_GETDESKWALLPAPER,
        len(buffer),
        buffer,
        0,
    )
    assert buffer.value

    style = read_applied_wallpaper_style()
    with Image.open(image_path) as applied:
        _assert_displayed_wallpaper(
            applied,
            cover=cover,
            title=LONG_TITLE,
            artist="Test Artist",
            display_width=primary.width,
            display_height=primary.height,
            wallpaper_style=style["wallpaper_style"],
        )

    try:
        import win32com.client

        shell = win32com.client.Dispatch("Shell.Application")
        shell.MinimizeAll()
    except Exception:
        pass

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with mss.MSS() as grabber:
        monitor = grabber.monitors[1]
        shot = grabber.grab(monitor)
        capture = Image.frombytes("RGB", shot.size, shot.rgb)
        if capture.size != composed.size:
            capture = capture.resize(composed.size, Image.Resampling.LANCZOS)
        capture.save(ARTIFACTS_DIR / "win-desktop-capture-after-fix.png")


def test_dpi_unaware_logical_wallpaper_simulation_still_centers_after_physical_fix():
    cover = make_sample_cover()
    logical_w, logical_h = 1664, 1109
    physical_w, physical_h = 2496, 1664
    composed_logical = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=logical_w,
        height=logical_h,
    )
    composed_physical = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=physical_w,
        height=physical_h,
    )
    displayed_broken = simulate_dpi_unaware_fill_from_origin(
        composed_logical,
        display_width=physical_w,
        display_height=physical_h,
    )
    displayed_fixed = simulate_wallpaper_on_display(
        composed_physical,
        display_width=physical_w,
        display_height=physical_h,
        wallpaper_style=WALLPAPER_STYLE_CENTER,
    )
    assert displayed_broken.size == (physical_w, physical_h)
    assert displayed_fixed.size == (physical_w, physical_h)
    logical_layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=logical_w,
        height=logical_h,
    )
    fixed_layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=physical_w,
        height=physical_h,
    )
    logical_cx = (logical_layout.panel[0] + logical_layout.panel[2]) / 2
    apparent_x = logical_cx * (physical_w / logical_w)
    assert abs(apparent_x - logical_w * 0.75) < 8
    fixed_center = tile_centering_from_layout(
        fixed_layout,
        screen_width=physical_w,
        screen_height=physical_h,
    )
    assert_tile_centered(fixed_center, tolerance_px=6.0)
    assert_tile_fully_visible(
        fixed_layout,
        screen_width=physical_w,
        screen_height=physical_h,
    )
