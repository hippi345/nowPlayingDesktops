"""Mocked Windows dual-monitor span and per-monitor wallpaper verification."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform
from now_playing_desktops.platforms.windows_monitors import compose_canvas_pixel_size
from now_playing_desktops.platforms.windows_restore import (
    TILE_WALLPAPER_OFF,
    WALLPAPER_STYLE_FILL,
    WALLPAPER_STYLE_SPAN,
    apply_windows_fill_wallpaper_style,
    apply_windows_restore_snapshot,
    apply_windows_span_wallpaper_style,
)
from tests.helpers import FakePlatform, make_runner, make_test_cover
from tests.verification_helpers import (
    VERIFY_TRACK,
    assert_centered_within,
    compose_virtual_desktop_span,
    draw_monitor_outlines,
    layout_monitors_b_to_right,
    layout_monitors_negative_origin,
    save_artifact,
    virtual_origin,
)

PLAYING = VERIFY_TRACK


def _screens_from_layout(layout) -> list[ScreenInfo]:
    return [
        ScreenInfo(
            screen_id=m.monitor_id,
            width=m.width,
            height=m.height,
            is_primary=m.is_primary,
            left=m.left,
            top=m.top,
        )
        for m in layout.monitors
    ]


def _style_values_from_mock(winreg_mock) -> dict[str, str]:
    return {
        call.args[1]: call.args[4]
        for call in winreg_mock.SetValueEx.call_args_list
        if call.args[1] in {"WallpaperStyle", "TileWallpaper"}
    }


@pytest.mark.parametrize(
    "layout_factory",
    [layout_monitors_negative_origin, layout_monitors_b_to_right],
)
def test_virtual_desktop_span_canvas_size_and_centering(layout_factory):
    layout = layout_factory()
    monitors = list(layout.monitors)
    width, height = compose_canvas_pixel_size(monitors)
    composed = compose_virtual_desktop_span(monitors)
    assert composed.size == (width, height)
    dx, dy = assert_centered_within(composed, width, height)
    assert dx <= 2 and dy <= 2


def test_windows_two_monitor_span_artifacts():
    for layout in (layout_monitors_negative_origin(), layout_monitors_b_to_right()):
        monitors = list(layout.monitors)
        composed = compose_virtual_desktop_span(monitors)
        origin = virtual_origin(monitors)
        width, height = composed.size
        assert_centered_within(composed, width, height)
        if layout.name == "span-left":
            save_artifact(composed, "win-two-monitor-span.png")
            debug = draw_monitor_outlines(composed, monitors, origin=origin)
            save_artifact(debug, "win-two-monitor-debug.png")
        else:
            save_artifact(composed, "win-two-monitor-span-right.png")


def test_span_wallpaper_style_22_for_multi_monitor_spi():
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg") as winreg_mock,
    ):
        apply_windows_span_wallpaper_style()
    styles = _style_values_from_mock(winreg_mock)
    assert styles["WallpaperStyle"] == WALLPAPER_STYLE_SPAN
    assert styles["TileWallpaper"] == TILE_WALLPAPER_OFF


def test_fill_wallpaper_style_10_for_single_monitor():
    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg") as winreg_mock,
    ):
        apply_windows_fill_wallpaper_style()
    styles = _style_values_from_mock(winreg_mock)
    assert styles["WallpaperStyle"] == WALLPAPER_STYLE_FILL


def test_set_wallpaper_uses_span_style_for_multi_monitor_primary_spi(tmp_path: Path):
    image = tmp_path / "span.png"
    image.write_bytes(b"x")
    monitors = list(layout_monitors_negative_origin().monitors)
    with (
        patch.object(sys, "platform", "win32"),
        patch(
            "now_playing_desktops.platforms.windows_monitors.enumerate_monitors",
            return_value=monitors,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore.apply_windows_span_wallpaper_style",
        ) as span_mock,
        patch(
            "now_playing_desktops.platforms.windows_restore.apply_windows_fill_wallpaper_style",
        ) as fill_mock,
        patch("now_playing_desktops.platforms.windows.ctypes") as ctypes_mock,
    ):
        ctypes_mock.windll.user32.SystemParametersInfoW.return_value = True
        platform = WindowsWallpaperPlatform()
        platform._per_monitor = False
        platform.set_wallpaper(image)
    span_mock.assert_called_once()
    fill_mock.assert_not_called()


def test_set_wallpaper_uses_fill_for_per_monitor_id(tmp_path: Path):
    image = tmp_path / "one.png"
    image.write_bytes(b"x")
    monitors = list(layout_monitors_negative_origin().monitors)
    with (
        patch.object(sys, "platform", "win32"),
        patch(
            "now_playing_desktops.platforms.windows_monitors.enumerate_monitors",
            return_value=monitors,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore.apply_windows_fill_wallpaper_style",
        ) as fill_mock,
        patch(
            "now_playing_desktops.platforms.windows._set_wallpaper_on_monitor",
        ) as set_mon,
    ):
        platform = WindowsWallpaperPlatform()
        platform._per_monitor = True
        platform.set_wallpaper(image, screen_id="2")
    fill_mock.assert_called_once()
    set_mon.assert_called_once()


def test_runner_span_job_matches_virtual_bounds():
    layout = layout_monitors_negative_origin()
    screens = _screens_from_layout(layout)
    platform = FakePlatform(screen=(1920, 1080))
    runner = make_runner(Path("/tmp/unused"), platform=platform)
    with patch.object(sys, "platform", "win32"):
        jobs = runner._resolve_wallpaper_render_jobs(screens)
    expected = compose_canvas_pixel_size(list(layout.monitors))
    assert jobs == [(None, expected[0], expected[1])]


def test_per_monitor_jobs_when_sizes_differ_and_com_available(tmp_path: Path):
    layout = layout_monitors_negative_origin()
    screens = _screens_from_layout(layout)

    class PerScreenPlatform(FakePlatform):
        def supports_per_screen_wallpaper(self) -> bool:
            return True

        def list_screens(self):
            return screens

    runner = make_runner(tmp_path, platform=PerScreenPlatform())
    jobs = runner._resolve_wallpaper_render_jobs(screens)
    assert len(jobs) == 2
    assert {job[0] for job in jobs} == {"1", "2"}


def test_per_monitor_compose_centered_within_each_monitor_rect():
    layout = layout_monitors_negative_origin()
    cover = make_test_cover()
    for monitor in layout.monitors:
        composed = compose_virtual_desktop_span([monitor], cover=cover)
        assert composed.size == (monitor.width, monitor.height)
        assert_centered_within(composed, monitor.width, monitor.height)


def test_windows_restore_restores_style_and_wallpaper(tmp_path: Path):
    original = tmp_path / "orig.jpg"
    original.write_bytes(b"\xff\xd8\xff\x00orig")
    snapshot = {
        "backend": "windows",
        "stable_path": str(original),
        "wallpaper_style": "6",
        "tile_wallpaper": "1",
        "background_type": 0,
        "per_monitor": False,
        "monitors": {},
    }
    spi_calls: list[str] = []

    def fake_spi(path_str: str) -> None:
        spi_calls.append(path_str)

    with (
        patch.object(sys, "platform", "win32"),
        patch("now_playing_desktops.platforms.windows_restore.winreg") as winreg_mock,
        patch(
            "now_playing_desktops.platforms.windows_restore._apply_spi_wallpaper",
            side_effect=fake_spi,
        ),
    ):
        apply_windows_restore_snapshot(
            snapshot,
            set_wallpaper_on_monitor=MagicMock(),
            set_wallpaper_primary=MagicMock(),
        )
    assert spi_calls == [str(original.resolve())]
    restored = _style_values_from_mock(winreg_mock)
    assert restored["WallpaperStyle"] == "6"
    assert restored["TileWallpaper"] == "1"


def test_runner_applies_span_compose_under_mocked_monitors(tmp_path: Path, monkeypatch):
    layout = layout_monitors_negative_origin()
    screens = _screens_from_layout(layout)
    platform = FakePlatform(wallpaper=tmp_path / "wall.jpg")
    (tmp_path / "wall.jpg").write_bytes(b"orig")
    runner = make_runner(tmp_path, platform=platform)
    monkeypatch.setattr(platform, "list_screens", lambda: screens)

    with (
        patch.object(sys, "platform", "win32"),
        patch(
            "now_playing_desktops.platforms.windows_console.register_console_restore_handler",
        ),
        patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.download_album_art",
            side_effect=lambda _u, dest, session=None: make_test_cover().save(dest, "JPEG"),
        ),
    ):
        runner.startup()
        runner.apply_playback_once()

    assert len(platform.set_calls) == 1

    with Image.open(platform.set_calls[0]) as applied:
        expected = compose_canvas_pixel_size(list(layout.monitors))
        assert applied.size == expected
