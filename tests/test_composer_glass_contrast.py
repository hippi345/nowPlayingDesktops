from __future__ import annotations

import random

from PIL import Image

from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout, render_backdrop
from now_playing_desktops.verification.wallpaper_analysis import (
    assert_glass_panel_present,
    glass_ring_luminance_margin,
)
from tests.helpers import ARTIFACTS_DIR, make_sample_cover

LONG_TITLE = "Long Title For Centering"
WIDTH, HEIGHT = 1664, 1109
MIN_MARGIN = 4.0


def _solid_cover(rgb: tuple[int, int, int], *, noise: int = 0) -> Image.Image:
    image = Image.new("RGB", (640, 640), rgb)
    if noise:
        px = image.load()
        rng = random.Random(0)
        for y in range(image.height):
            for x in range(image.width):
                jitter = rng.randint(-noise, noise)
                px[x, y] = tuple(max(0, min(255, c + jitter)) for c in rgb)
    return image


def _assert_margin(composed, cover, *, min_margin: float = MIN_MARGIN) -> float:
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=WIDTH,
        height=HEIGHT,
    )
    backdrop = render_backdrop(cover, WIDTH, HEIGHT)
    margin = glass_ring_luminance_margin(composed, layout, backdrop)
    assert_glass_panel_present(composed, layout, backdrop, require_uniformity=False)
    assert margin >= min_margin
    return margin


def test_glass_contrast_dark_mid_bright_covers():
    dark = _solid_cover((8, 10, 12), noise=6)
    mid = _solid_cover((120, 118, 115))
    bright = make_sample_cover()

    dark_composed = compose_wallpaper(
        dark,
        title=LONG_TITLE,
        artist="Artist",
        width=WIDTH,
        height=HEIGHT,
    )
    mid_composed = compose_wallpaper(
        mid,
        title=LONG_TITLE,
        artist="Artist",
        width=WIDTH,
        height=HEIGHT,
    )
    bright_composed = compose_wallpaper(
        bright,
        title=LONG_TITLE,
        artist="Artist",
        width=WIDTH,
        height=HEIGHT,
    )

    dark_margin = _assert_margin(dark_composed, dark, min_margin=4.0)
    mid_margin = _assert_margin(mid_composed, mid)
    bright_margin = _assert_margin(bright_composed, bright)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    dark_composed.save(ARTIFACTS_DIR / "dark-cover-panel.png")
    bright_composed.save(ARTIFACTS_DIR / "normal-cover-panel.png")

    assert dark_margin >= 4.0
    assert mid_margin >= MIN_MARGIN
    assert bright_margin >= MIN_MARGIN
