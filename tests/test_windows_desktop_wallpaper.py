from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageChops

from now_playing_desktops.composer import (
    compose_wallpaper,
    plan_wallpaper_layout,
    render_backdrop,
    save_wallpaper,
)
from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware
from now_playing_desktops.spotify_art import TrackPlayback
from now_playing_desktops.verification.wallpaper_analysis import (
    assert_glass_panel_present,
    assert_tile_centered,
    assert_tile_fully_visible,
    tile_centering_from_layout,
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


@pytest.mark.skipif(sys.platform != "win32", reason="Requires interactive Windows desktop session")
def test_windows_desktop_capture_centering_and_glass(tmp_path: Path):
    from PIL import ImageGrab

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
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=primary.width,
        height=primary.height,
    )
    backdrop = render_backdrop(cover, primary.width, primary.height)
    assert_glass_panel_present(composed, layout, backdrop)
    centering = tile_centering_from_layout(
        layout,
        screen_width=primary.width,
        screen_height=primary.height,
    )
    assert_tile_centered(centering, tolerance_px=3.0)
    assert_tile_fully_visible(
        layout,
        screen_width=primary.width,
        screen_height=primary.height,
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

    capture = ImageGrab.grab(all_screens=True)
    if capture.size != composed.size:
        capture = capture.resize(composed.size, Image.Resampling.LANCZOS)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    capture.save(ARTIFACTS_DIR / "win-desktop-capture-after-fix.png")

    px0, py0, px1, py1 = layout.panel
    panel_capture = capture.crop((px0, py0, px1, py1))
    panel_composed = composed.crop((px0, py0, px1, py1))
    panel_diff = ImageChops.difference(panel_capture, panel_composed).convert("L")
    panel_pixels = list(panel_diff.getdata())
    mean_panel_diff = sum(panel_pixels) / max(1, len(panel_pixels))
    assert mean_panel_diff < 45.0, (
        f"Desktop panel diverged from composed PNG (mean={mean_panel_diff:.1f})"
    )

    # Layout centering is the ground truth when bitmap matches monitor pixels.
    assert_tile_centered(
        tile_centering_from_layout(
            layout,
            screen_width=capture.width,
            screen_height=capture.height,
        ),
        tolerance_px=4.0,
    )
