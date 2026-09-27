from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from now_playing_desktops.composer import (
    WallpaperLayout,
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
    panel_bbox_from_capture,
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
    if capture.size != (primary.width, primary.height):
        capture = capture.crop((0, 0, primary.width, primary.height))
    backdrop_capture = backdrop
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    capture.save(ARTIFACTS_DIR / "win-desktop-capture-after-fix.png")

    px0, py0, px1, py1 = panel_bbox_from_capture(capture, backdrop=backdrop_capture)
    detected = WallpaperLayout(
        panel=(px0, py0, px1, py1),
        cover=layout.cover,
        title=layout.title,
        artist=layout.artist,
    )
    detected_centering = tile_centering_from_layout(
        detected,
        screen_width=capture.width,
        screen_height=capture.height,
    )
    assert_tile_centered(detected_centering, tolerance_px=8.0)
