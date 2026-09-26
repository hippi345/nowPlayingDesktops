from __future__ import annotations

import pytest
from PIL import Image, ImageFilter

from now_playing_desktops.composer import (
    compose_wallpaper,
    compute_text_layout,
    load_wallpaper_font,
    max_text_width,
    save_wallpaper,
    scale_cover_to_fill,
    title_font_size_for_height,
)
from tests.helpers import (
    ARTIFACTS_DIR,
    image_variance,
    make_sample_cover,
    make_sharp_test_cover,
)

LONG_TITLE = (
    "This Is An Extremely Long Track Title That Should Be Ellipsized "
    "When Rendered On The Wallpaper Composition"
)
SHORT_TITLE = "Short Title"

RESOLUTIONS = {
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4k": (3840, 2160),
    "ultrawide": (3440, 1440),
}


def _expected_blended_edge_color(
    cover: Image.Image,
    width: int,
    height: int,
    x: int,
    y: int,
) -> tuple[int, int, int]:
    filled = scale_cover_to_fill(cover, width, height)
    blur_radius = max(24, min(width, height) // 40)
    blurred = filled.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    r, g, b = blurred.getpixel((x, y))
    return (
        int(r * 0.55),
        int(g * 0.55),
        int(b * 0.55),
    )


def _assert_edge_pixels_from_art(cover: Image.Image, composed: Image.Image) -> None:
    width, height = composed.size
    edge_points = (
        (2, height // 2),
        (width - 3, height // 2),
        (width // 2, 2),
        (width // 2, height - 3),
    )
    flat_fill = (0, 0, 0)
    for x, y in edge_points:
        actual = composed.getpixel((x, y))
        expected = _expected_blended_edge_color(cover, width, height, x, y)
        assert actual != flat_fill
        assert sum(abs(actual[i] - expected[i]) for i in range(3)) < 45


@pytest.mark.parametrize(
    ("label", "resolution"),
    list(RESOLUTIONS.items()),
    ids=list(RESOLUTIONS.keys()),
)
def test_backdrop_fills_screen_edge_pixels_derived_from_art(
    label: str,
    resolution: tuple[int, int],
):
    cover = make_sample_cover()
    width, height = resolution
    composed = compose_wallpaper(
        cover,
        title=SHORT_TITLE,
        artist="Artist",
        width=width,
        height=height,
    )
    _assert_edge_pixels_from_art(cover, composed)


def test_long_title_ellipsized_within_max_width():
    width, height = 1920, 1080
    cover = make_sample_cover()
    foreground_width = int(cover.width * (int(height * 0.4) / cover.height))
    layout = compute_text_layout(
        title=LONG_TITLE,
        artist="Test Artist",
        screen_width=width,
        screen_height=height,
        foreground_width=foreground_width,
    )
    title_font = load_wallpaper_font(layout.title_font_size)
    assert layout.title.endswith("…")
    assert layout.title != LONG_TITLE
    assert title_font.getlength(layout.title) <= layout.max_width + 1
    assert layout.max_width == max_text_width(foreground_width, width)


def test_short_title_not_ellipsized():
    layout = compute_text_layout(
        title=SHORT_TITLE,
        artist="Band",
        screen_width=1920,
        screen_height=1080,
        foreground_width=400,
    )
    assert layout.title == SHORT_TITLE
    assert not layout.title.endswith("…")


def test_title_font_size_scales_with_screen_height():
    size_1080 = title_font_size_for_height(1080)
    size_4k = title_font_size_for_height(2160)
    assert size_4k > size_1080
    assert 23 <= size_1080 <= 29
    assert 46 <= size_4k <= 58


def _assert_cover_not_over_upscaled(cover: Image.Image, composed: Image.Image, height: int) -> None:
    target_height = int(height * 0.4)
    max_allowed = min(target_height, int(cover.height * 1.5))
    center_box = (
        composed.width // 2 - max_allowed // 2,
        composed.height // 2 - max_allowed // 2,
        composed.width // 2 + max_allowed // 2,
        composed.height // 2 + max_allowed // 2,
    )
    assert center_box[3] - center_box[1] >= max_allowed // 2


def _assert_text_region_present(composed: Image.Image) -> None:
    width, height = composed.size
    text_band = composed.crop((width // 4, int(height * 0.62), width * 3 // 4, int(height * 0.78)))
    pixels = list(text_band.getdata())
    bright = sum(1 for r, g, b in pixels if r > 180 and g > 180 and b > 180)
    assert bright > 50


@pytest.mark.parametrize(
    ("label", "resolution"),
    list(RESOLUTIONS.items()),
    ids=list(RESOLUTIONS.keys()),
)
def test_compose_sample_wallpaper_writes_artifact_png(
    label: str,
    resolution: tuple[int, int],
):
    cover = make_sample_cover()
    width, height = resolution
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    assert composed.size == (width, height)
    _assert_text_region_present(composed)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS_DIR / f"np-sample-{label}.png"
    save_wallpaper(composed, out)
    assert out.is_file()


def test_compose_wallpaper_foreground_sharpness_uses_checker_cover():
    cover = make_sharp_test_cover()
    width, height = 1920, 1080
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    _assert_cover_not_over_upscaled(cover, composed, height)
    center_var = image_variance(
        composed,
        (width // 2 - 120, height // 2 - 120, width // 2 + 120, height // 2 + 120),
    )
    corner_var = image_variance(composed, (40, 40, 200, 200))
    assert center_var > corner_var * 2
