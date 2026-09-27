from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from now_playing_desktops.composer import (
    backdrop_blur_radius,
    compose_wallpaper,
    compute_cover_placement,
    compute_text_layout,
    contrast_ratio,
    extract_dominant_glow_color,
    load_wallpaper_font,
    max_text_width,
    mean_luminance,
    render_backdrop,
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
    "1664x1109": (1664, 1109),
}


def _expected_backdrop_edge_color(
    cover: Image.Image,
    width: int,
    height: int,
    x: int,
    y: int,
) -> tuple[int, int, int]:
    return render_backdrop(cover, width, height).getpixel((x, y))


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
        expected = _expected_backdrop_edge_color(cover, width, height, x, y)
        assert actual != flat_fill
        assert sum(abs(actual[i] - expected[i]) for i in range(3)) < 55


def test_backdrop_blur_radius_scales_with_screen_size():
    blur_1080 = backdrop_blur_radius(1920, 1080)
    blur_4k = backdrop_blur_radius(3840, 2160)
    assert blur_4k > blur_1080
    assert abs(blur_4k / blur_1080 - 2.0) < 0.15


def test_backdrop_heavy_blur_obscures_cover_detail():
    cover = make_sharp_test_cover()
    width, height = 1920, 1080
    sharp = scale_cover_to_fill(cover, width, height)
    blurred = render_backdrop(cover, width, height)
    sharp_var = image_variance(sharp, (200, 200, 600, 600))
    blurred_var = image_variance(blurred, (200, 200, 600, 600))
    assert blurred_var < sharp_var * 0.35


def test_scale_cover_to_fill_rejects_non_positive_size():
    cover = Image.new("RGB", (100, 100))
    with pytest.raises(ValueError, match="positive"):
        scale_cover_to_fill(cover, 1920, 0)


def test_compose_wallpaper_rejects_non_positive_canvas():
    cover = Image.new("RGB", (100, 100))
    with pytest.raises(ValueError, match="positive"):
        compose_wallpaper(cover, title="T", artist="A", width=-1, height=1080)


def test_radial_vignette_corners_darker_than_center():
    cover = make_sample_cover()
    backdrop = render_backdrop(cover, 1920, 1080)
    center_lum = mean_luminance(backdrop, (860, 440, 1060, 640))
    corner_lum = mean_luminance(backdrop, (0, 0, 120, 120))
    assert corner_lum < center_lum - 12


def test_cover_shadow_darker_below_than_above():
    cover = make_sample_cover()
    composed = compose_wallpaper(
        cover,
        title=SHORT_TITLE,
        artist="Artist",
        width=1920,
        height=1080,
    )
    placement = compute_cover_placement(cover, 1920, 1080)
    cx = placement.x + placement.width // 2
    above = mean_luminance(
        composed,
        (cx - 3, placement.y - 22, cx + 3, placement.y - 8),
    )
    below = mean_luminance(
        composed,
        (
            cx - 3,
            placement.y + placement.height + 8,
            cx + 3,
            placement.y + placement.height + 22,
        ),
    )
    backdrop = render_backdrop(cover, 1920, 1080)
    above_box = (cx - 3, placement.y - 22, cx + 3, placement.y - 8)
    below_box = (
        cx - 3,
        placement.y + placement.height + 8,
        cx + 3,
        placement.y + placement.height + 22,
    )
    above_backdrop = mean_luminance(backdrop, above_box)
    below_backdrop = mean_luminance(backdrop, below_box)
    assert below < below_backdrop - 2
    below_delta = below - below_backdrop
    above_delta = above - above_backdrop
    assert below_delta < 0
    assert below_delta < above_delta - 2


def test_cover_shadow_extends_beyond_cover_edges():
    cover = make_sample_cover()
    composed = compose_wallpaper(
        cover,
        title=SHORT_TITLE,
        artist="Artist",
        width=1920,
        height=1080,
    )
    placement = compute_cover_placement(cover, 1920, 1080)
    mid_y = placement.y + placement.height // 2
    outside = mean_luminance(
        composed,
        (placement.x - 28, mid_y - 4, placement.x - 6, mid_y + 4),
    )
    backdrop_only = mean_luminance(
        render_backdrop(cover, 1920, 1080),
        (placement.x - 28, mid_y - 4, placement.x - 6, mid_y + 4),
    )
    assert outside < backdrop_only - 2


def test_cover_rim_highlight_brighter_than_adjacent_backdrop():
    cover = make_sample_cover()
    composed = compose_wallpaper(
        cover,
        title=SHORT_TITLE,
        artist="Artist",
        width=1920,
        height=1080,
    )
    placement = compute_cover_placement(cover, 1920, 1080)
    rim_lum = mean_luminance(
        composed,
        (placement.x + 6, placement.y + 6, placement.x + 18, placement.y + 18),
    )
    adjacent = mean_luminance(
        composed,
        (placement.x - 24, placement.y + 12, placement.x - 6, placement.y + 30),
    )
    assert rim_lum > adjacent + 8


def test_extract_dominant_glow_color_prefers_vivid_red():
    cover = Image.new("RGB", (64, 64), (20, 20, 20))
    draw = ImageDraw.Draw(cover)
    draw.rectangle((10, 10, 54, 54), fill=(230, 40, 40))
    color = extract_dominant_glow_color(cover)
    assert color[0] > color[1] + 40
    assert color[0] > color[2] + 40


def test_glow_layer_tints_backdrop_behind_cover():
    from now_playing_desktops.composer import _build_glow_layer

    cover = Image.new("RGB", (640, 640), (220, 50, 80))
    placement = compute_cover_placement(cover, 1920, 1080)
    color = extract_dominant_glow_color(cover)
    glow_layer = _build_glow_layer(color, placement, (1920, 1080))
    sample = (placement.x + placement.width // 2, placement.y + placement.height // 2)
    assert glow_layer.getpixel(sample)[3] > 0
    corner = glow_layer.getpixel((10, 10))
    assert corner[3] == 0
    assert color == (220, 50, 80)


def test_title_text_contrast_against_local_backdrop():
    cover = make_sample_cover()
    width, height = 1920, 1080
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    placement = compute_cover_placement(cover, width, height)
    text_y = placement.y + placement.height + height // 32
    band = composed.crop((width // 2 - 350, text_y, width // 2 + 350, text_y + 48))
    bright_pixels = [rgb for rgb in band.getdata() if min(rgb) >= 200]
    assert bright_pixels, "expected bright title pixels in text band"
    text_pixel = max(bright_pixels, key=sum)
    backdrop = render_backdrop(cover, width, height)
    bx = width // 2
    by = text_y + 8
    for y in range(text_y, text_y + 48):
        for x in range(width // 2 - 350, width // 2 + 350):
            if composed.getpixel((x, y)) == text_pixel:
                bx, by = x, y
                break
        else:
            continue
        break
    backdrop_pixel = backdrop.getpixel((bx, by))
    assert contrast_ratio(text_pixel, backdrop_pixel) >= 4.5


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
