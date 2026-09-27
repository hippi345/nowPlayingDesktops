from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import ImageFont

from now_playing_desktops.composer import (
    TEXT_SUPERSAMPLE_FACTOR,
    TITLE_FONT_FILE,
    _font_path,
    _load_package_font,
    _render_text_layer_supersampled,
    plan_wallpaper_layout,
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
