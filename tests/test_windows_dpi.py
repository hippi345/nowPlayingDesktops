from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from now_playing_desktops.platforms.windows_dpi import (
    get_process_dpi_awareness,
    physical_pixel_size_from_rect,
    set_process_dpi_aware,
)
from now_playing_desktops.platforms.windows_restore import (
    WALLPAPER_STYLE_FILL,
    apply_windows_wallpaper_style_for_image,
)


def test_physical_pixel_size_uses_native_when_rect_is_logical():
    size = physical_pixel_size_from_rect(
        rect_width=1664,
        rect_height=1109,
        dpi_x=144,
        dpi_y=144,
        native_size=(2496, 1664),
    )
    assert size == (2496, 1664)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_set_process_dpi_aware_does_not_raise():
    set_process_dpi_aware()
    assert get_process_dpi_awareness() in (
        0,
        1,
        2,
    ), "unexpected GetProcessDpiAwareness value"


def test_apply_style_always_fill_even_for_exact_size_bitmap():
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg") as winreg_mock,
    ):
        style = apply_windows_wallpaper_style_for_image(
            image_width=2496,
            image_height=1664,
            monitor_width=2496,
            monitor_height=1664,
        )
    assert style == WALLPAPER_STYLE_FILL
    values = {call.args[1]: call.args[4] for call in winreg_mock.SetValueEx.call_args_list}
    assert values["WallpaperStyle"] == WALLPAPER_STYLE_FILL


def test_apply_style_fill_when_sizes_differ():
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg") as winreg_mock,
    ):
        style = apply_windows_wallpaper_style_for_image(
            image_width=1664,
            image_height=1109,
            monitor_width=2496,
            monitor_height=1664,
        )
    assert style == WALLPAPER_STYLE_FILL
    values = {call.args[1]: call.args[4] for call in winreg_mock.SetValueEx.call_args_list}
    assert values["WallpaperStyle"] == WALLPAPER_STYLE_FILL
