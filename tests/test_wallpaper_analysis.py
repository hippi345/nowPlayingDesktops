from __future__ import annotations

import pytest

from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout, render_backdrop
from now_playing_desktops.platforms.windows_dpi import (
    physical_pixel_size_from_rect,
    simulate_top_left_scale_center_offset,
)
from now_playing_desktops.verification.wallpaper_analysis import (
    assert_glass_panel_present,
    assert_no_backdrop_band_edges,
    assert_tile_centered,
    assert_tile_fully_visible,
    assert_title_text_present,
    tile_centering_from_layout,
)
from tests.helpers import ARTIFACTS_DIR, make_sample_cover

LONG_TITLE = "Long Title For Centering"


def test_physical_pixel_size_scales_logical_rect_at_150_percent_dpi():
    width, height = physical_pixel_size_from_rect(
        rect_width=1664,
        rect_height=1109,
        dpi_x=144,
        dpi_y=144,
        native_size=(2496, 1664),
    )
    assert (width, height) == (2496, 1664)


def test_physical_pixel_size_keeps_pm_aware_native_rect():
    width, height = physical_pixel_size_from_rect(
        rect_width=2496,
        rect_height=1664,
        dpi_x=144,
        dpi_y=144,
        native_size=(2496, 1664),
    )
    assert (width, height) == (2496, 1664)


def test_top_left_stretch_shifts_tile_center_to_three_quarters_width():
    """Documents the observed laptop bug when a 1664px-wide bitmap fills a 2496px display."""
    logical_center = 1664 / 2
    apparent = simulate_top_left_scale_center_offset(
        image_width=1664,
        image_height=1109,
        display_width=2496,
        display_height=1664,
        tile_center_x=logical_center,
    )
    assert abs(apparent - 1248) < 1.0
    assert abs(apparent / 1664 - 0.75) < 0.01


@pytest.mark.parametrize(
    ("width", "height"),
    [(1664, 1109), (1920, 1080), (2560, 1440)],
)
def test_compose_layout_centering_glass_text_and_no_backdrop_bands(width: int, height: int):
    cover = make_sample_cover()
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    backdrop = render_backdrop(cover, width, height)
    centering = tile_centering_from_layout(layout, screen_width=width, screen_height=height)
    assert_tile_centered(centering, tolerance_px=3.0)
    assert_tile_fully_visible(layout, screen_width=width, screen_height=height)
    assert_glass_panel_present(composed, layout, backdrop)
    assert_title_text_present(composed, layout)
    assert_no_backdrop_band_edges(composed, cover, layout=layout)
    if width == 1664 and height == 1109:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        composed.save(ARTIFACTS_DIR / "render-1664x1109.png")
        px0, py0, px1, py1 = layout.panel
        composed.crop((px0, py0, px1, py1)).save(ARTIFACTS_DIR / "glass-panel-head-crop.png")


def test_liquid_glass_png_regression_guard_after_shadow_clip_commit():
    """Compositor shadow/panel changes landed in 969206f; keep PNG glass/text/band checks."""
    import subprocess

    cover = make_sample_cover()
    width, height = 1664, 1109
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=width,
        height=height,
    )
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=width,
        height=height,
    )
    backdrop = render_backdrop(cover, width, height)
    assert_glass_panel_present(composed, layout, backdrop)
    assert_title_text_present(composed, layout)
    assert_no_backdrop_band_edges(composed, cover, layout=layout)
    px0, py0, px1, py1 = layout.panel
    pr9_code = subprocess.check_output(
        ["git", "show", "2746ff4:src/now_playing_desktops/composer.py"],
        text=True,
    )
    namespace: dict = {}
    exec(compile(pr9_code, "composer_pr9.py", "exec"), namespace)
    pr9 = namespace["compose_wallpaper"](
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=width,
        height=height,
    )
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    pr9.crop((px0, py0, px1, py1)).save(ARTIFACTS_DIR / "glass-panel-pr9-crop.png")
    composed.crop((px0, py0, px1, py1)).save(ARTIFACTS_DIR / "glass-panel-after-fix-crop.png")
