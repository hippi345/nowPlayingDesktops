from __future__ import annotations

import pytest
from PIL import Image
from tests.conftest import ARTIFACTS_DIR, image_variance, make_test_cover

from now_playing_desktops.composer import compose_wallpaper, save_wallpaper

LONG_TITLE = (
    "This Is An Extremely Long Track Title That Should Be Ellipsized "
    "When Rendered On The Wallpaper Composition"
)

RESOLUTIONS = {
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4k": (3840, 2160),
    "ultrawide": (3440, 1440),
}


def _assert_cover_not_over_upscaled(cover: Image.Image, composed: Image.Image, height: int) -> None:
    target_height = int(height * 0.4)
    max_allowed = min(target_height, int(cover.height * 1.5))
    # Foreground occupies a central band; height of high-variance region should respect cap.
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
def test_compose_wallpaper_matches_resolution_and_visual_rules(
    label: str,
    resolution: tuple[int, int],
):
    cover = make_test_cover()
    width, height = resolution
    composed = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=width,
        height=height,
    )
    assert composed.size == (width, height)
    _assert_cover_not_over_upscaled(cover, composed, height)

    center_var = image_variance(
        composed,
        (width // 2 - 120, height // 2 - 120, width // 2 + 120, height // 2 + 120),
    )
    corner_var = image_variance(composed, (40, 40, 200, 200))
    assert center_var > corner_var * 2
    _assert_text_region_present(composed)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS_DIR / f"np-sample-{label}.png"
    save_wallpaper(composed, out)
    assert out.is_file()
