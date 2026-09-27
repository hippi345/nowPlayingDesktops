from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import ImageFont

from now_playing_desktops.composer import (
    ARTIST_TEXT_ALPHA,
    ARTIST_TEXT_RGB,
    TEXT_SUPERSAMPLE_FACTOR,
    TITLE_FONT_FILE,
    _font_path,
    _load_package_font,
    _render_text_layer_supersampled,
    compose_wallpaper,
    contrast_ratio,
    plan_wallpaper_layout,
    render_backdrop,
)
from tests.helpers import make_sample_cover

LONG_TITLE = (
    "This Is An Extremely Long Track Title That Should Be Ellipsized "
    "When Rendered On The Wallpaper Composition"
)


def test_font_loads_from_package_resources_not_default():
    font = _load_package_font(TITLE_FONT_FILE, 24)
    assert isinstance(font, ImageFont.FreeTypeFont)
    path = _font_path(TITLE_FONT_FILE)
    assert path.is_file()
    assert "Inter-Bold" in path.name


def test_text_layer_rendered_at_supersample_factor():
    with patch("now_playing_desktops.composer._load_font") as load_mock:
        load_mock.return_value = _load_package_font(TITLE_FONT_FILE, 72)
        _render_text_layer_supersampled(
            "Supersampled",
            font_size=24,
            bold=True,
            fill_alpha=255,
            canvas_width=800,
        )
    load_mock.assert_called_once_with(24 * TEXT_SUPERSAMPLE_FACTOR, bold=True)


def test_compose_wallpaper_centering_padding_within_two_pixels():
    cover = make_sample_cover()
    width, height = 1920, 1080
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    pl = layout.panel
    cov = layout.cover
    cover_left = cov[0] - pl[0]
    cover_right = pl[2] - cov[2]
    assert abs(cover_left - cover_right) <= 2

    title_center = (layout.title[0] + layout.title[2]) / 2
    artist_center = (layout.artist[0] + layout.artist[2]) / 2
    panel_center = (pl[0] + pl[2]) / 2
    assert abs(title_center - panel_center) <= 2
    assert abs(artist_center - panel_center) <= 2

    group_top = cov[1]
    group_bottom = layout.artist[3]
    pad_top = group_top - pl[1]
    pad_bottom = pl[3] - group_bottom
    assert abs(pad_top - pad_bottom) <= 2


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (1920, 1080),
        (2560, 1440),
        (1664, 1109),
        (3440, 1440),
    ],
)
def test_centering_across_resolutions(width: int, height: int):
    cover = make_sample_cover()
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=width,
        height=height,
    )
    pl = layout.panel
    cov = layout.cover
    assert abs((cov[0] - pl[0]) - (pl[2] - cov[2])) <= 2
    pad_top = cov[1] - pl[1]
    pad_bottom = pl[3] - layout.artist[3]
    assert abs(pad_top - pad_bottom) <= 2


def test_supersample_constant_is_three():
    assert TEXT_SUPERSAMPLE_FACTOR == 3


def test_glass_panel_single_layer_rounded_corners_and_soft_shadow_below():
    cover = make_sample_cover()
    width, height = 1664, 1109
    backdrop = render_backdrop(cover, width, height)
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    px0, py0, px1, py1 = layout.panel
    corner = (px0 + 3, py0 + 3)
    backdrop_corner = backdrop.getpixel(corner)
    composed_corner = composed.getpixel(corner)
    assert sum(abs(backdrop_corner[i] - composed_corner[i]) for i in range(3)) < 28

    short_side = min(px1 - px0, py1 - py0)
    below_y = min(height - 2, py1 + int(short_side * 0.045) + 14)
    sample_x = max(0, px0 - 10)
    below_rgb = composed.getpixel((sample_x, below_y))
    backdrop_below = backdrop.getpixel((sample_x, below_y))
    assert sum(abs(below_rgb[i] - backdrop_below[i]) for i in range(3)) < 42


def test_artist_text_contrast_on_glass_panel():
    cover = make_sample_cover()
    width, height = 1664, 1109
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    ax0, ay0, ax1, ay1 = layout.artist
    cx = (ax0 + ax1) // 2
    cy = (ay0 + ay1) // 2
    background = composed.getpixel((cx, cy))
    artist_rgb = tuple(int(c * ARTIST_TEXT_ALPHA / 255) for c in ARTIST_TEXT_RGB)
    assert contrast_ratio(artist_rgb, background) >= 4.5
