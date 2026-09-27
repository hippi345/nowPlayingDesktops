from __future__ import annotations

from pathlib import Path

import pytest

from now_playing_desktops.composer import compose_wallpaper, plan_wallpaper_layout
from now_playing_desktops.config import COMPOSED_CACHE_VERSION
from now_playing_desktops.verification.wallpaper_analysis import (
    assert_glass_panel_present,
    assert_no_backdrop_band_edges,
    assert_title_text_present,
    tile_centering_from_layout,
)
from now_playing_desktops.verification.windows_display import (
    simulate_dpi_unaware_fill_from_origin,
    simulate_wallpaper_on_display,
)
from tests.helpers import (
    ARTIFACTS_DIR,
    make_legacy_cached_wallpaper_without_glass,
    make_sample_cover,
)

LONG_TITLE = "Long Title For Centering"


def test_compose_cache_version_busts_stale_paths(tmp_path: Path):
    from now_playing_desktops.art_cache import ComposedArtCache

    cache = ComposedArtCache(tmp_path)
    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    path = cache.put("t1", "https://art", 1664, 1109, source)
    legacy_key = (
        __import__("hashlib")
        .sha256(
            b"t1|https://art|1664x1109",
        )
        .hexdigest()[:32]
    )
    assert path.name != f"{legacy_key}.png"
    assert COMPOSED_CACHE_VERSION in "glass-panel-v2"


def test_win150_simulation_artifacts_pr12_vs_fixed():
    cover = make_sample_cover()
    logical_w, logical_h = 1664, 1109
    physical_w, physical_h = 2496, 1664
    legacy = make_legacy_cached_wallpaper_without_glass(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=logical_w,
        height=logical_h,
    )
    sim_pr12 = simulate_dpi_unaware_fill_from_origin(
        legacy,
        display_width=physical_w,
        display_height=physical_h,
    )
    composed_physical = compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=physical_w,
        height=physical_h,
    )
    sim_fixed = simulate_wallpaper_on_display(
        composed_physical,
        display_width=physical_w,
        display_height=physical_h,
        wallpaper_style="0",
    )
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    sim_pr12.save(ARTIFACTS_DIR / "sim-win150-pr12.png")
    sim_fixed.save(ARTIFACTS_DIR / "sim-win150-fixed.png")
    composed_physical.save(ARTIFACTS_DIR / "render-2496x1664.png")
    compose_wallpaper(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=logical_w,
        height=logical_h,
    ).save(ARTIFACTS_DIR / "render-1664x1109.png")

    fixed_layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=physical_w,
        height=physical_h,
    )
    from now_playing_desktops.composer import render_backdrop

    backdrop = render_backdrop(cover, physical_w, physical_h)
    assert_glass_panel_present(composed_physical, fixed_layout, backdrop)
    assert_no_backdrop_band_edges(composed_physical, cover, layout=fixed_layout)
    center = tile_centering_from_layout(
        fixed_layout,
        screen_width=physical_w,
        screen_height=physical_h,
    )
    assert abs(center.offset_x) < 6.0


def test_stale_legacy_wallpaper_lacks_glass_and_text():
    cover = make_sample_cover()
    legacy = make_legacy_cached_wallpaper_without_glass(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=1664,
        height=1109,
    )
    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Artist",
        width=1664,
        height=1109,
    )
    from now_playing_desktops.composer import render_backdrop

    backdrop = render_backdrop(cover, 1664, 1109)
    with pytest.raises(AssertionError):
        assert_glass_panel_present(legacy, layout, backdrop)
    with pytest.raises(AssertionError):
        assert_title_text_present(legacy, layout)
