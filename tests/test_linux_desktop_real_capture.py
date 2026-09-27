"""Real Linux root-window capture verification (Xvfb + openbox + feh + mss)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from now_playing_desktops.platforms.base import ScreenInfo
from now_playing_desktops.platforms.linux import LinuxWallpaperPlatform
from now_playing_desktops.platforms.linux_backends import FehWallpaperBackend
from now_playing_desktops.platforms.linux_de import LinuxDesktopEnvironment
from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps
from now_playing_desktops.spotify_art import TrackPlayback
from tests.helpers import make_sample_cover, mock_load_track_cover_rgba
from tests.linux_desktop_capture import (
    assert_tile_centered,
    capture_root_png,
    captures_match,
    desktop_env,
    feh_set_wallpaper,
    require_linux_capture_tools,
    save_linux_artifact,
    start_openbox,
    start_xvfb,
    wait_for_capture_similar,
    wait_for_non_uniform_capture,
)

_DISPLAY_SERIAL = 600

VERIFY_TRACK = TrackPlayback(
    track_id="verify-track",
    art_url="https://example.test/art.jpg",
    title="Verify Title",
    artist="Verify Artist",
    is_playing=True,
)

RESOLUTIONS = (
    (1920, 1080, "linux-1080p-desktop.png"),
    (2560, 1440, "linux-1440p-desktop.png"),
    (3840, 2160, "linux-4k-desktop.png"),
    (1664, 1109, "linux-1664x1109-desktop.png"),
)


def _next_display() -> str:
    global _DISPLAY_SERIAL
    _DISPLAY_SERIAL += 1
    return f":{_DISPLAY_SERIAL}"


def _screen_info(width: int, height: int) -> list[ScreenInfo]:
    return [ScreenInfo(screen_id="0", width=width, height=height, is_primary=True)]


def _make_runner(work: Path, platform: LinuxWallpaperPlatform) -> NowPlayingRunner:
    return NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            playback_provider=MagicMock(),
            cache_dir=work / "cache",
            state_path=work / "state.json",
            poll_interval_seconds=0.05,
            sleep=lambda _s: None,
        )
    )


@pytest.fixture(scope="module", autouse=True)
def _require_tools():
    if sys.platform != "linux":
        pytest.skip("Linux root-window capture tests run only on Linux CI")
    require_linux_capture_tools()


@pytest.mark.integration
@pytest.mark.parametrize("width,height,artifact_name", RESOLUTIONS)
def test_linux_root_capture_shows_centered_tile_and_restore(
    tmp_path_factory,
    width: int,
    height: int,
    artifact_name: str,
):
    work = tmp_path_factory.mktemp(f"linux-cap-{width}x{height}")
    home = work / "home"
    home.mkdir()
    display = _next_display()
    xvfb = start_xvfb(display, width, height)
    openbox = start_openbox(display, home)
    env = desktop_env(display, home)

    import os

    os.environ["DISPLAY"] = display
    os.environ["HOME"] = str(home)

    original = work / "original.png"
    make_sample_cover(320).save(original, format="PNG")
    feh_set_wallpaper(original, env=env)
    baseline_path = work / "baseline.png"
    baseline = capture_root_png(display, baseline_path)

    platform = LinuxWallpaperPlatform(
        de=LinuxDesktopEnvironment.OTHER,
        backend=FehWallpaperBackend(),
    )
    runner = _make_runner(work, platform)
    paused = TrackPlayback(
        VERIFY_TRACK.track_id,
        VERIFY_TRACK.art_url,
        VERIFY_TRACK.title,
        VERIFY_TRACK.artist,
        is_playing=False,
    )

    try:
        with (
            patch.object(NowPlayingRunner, "_register_shutdown_handlers", lambda _self: None),
            patch(
                "now_playing_desktops.platforms.linux_screen.list_linux_screens",
                return_value=_screen_info(width, height),
            ),
            patch(
                "now_playing_desktops.runner.fetch_playback_for_runner",
                side_effect=[VERIFY_TRACK, paused],
            ),
            patch(
                "now_playing_desktops.runner.load_track_cover",
                side_effect=mock_load_track_cover_rgba,
            ),
        ):
            runner.startup()
            runner.apply_playback_once()

            cap_path = work / "playing.png"
            playing = wait_for_non_uniform_capture(
                display,
                cap_path,
                differ_from=baseline,
            )
            assert playing.size == (width, height)
            dx, dy = assert_tile_centered(
                playing,
                differ_from=baseline,
                tolerance_px=3.0,
            )
            artifact_path = save_linux_artifact(playing, artifact_name)
            assert artifact_path.stat().st_size >= 8_000

            runner.apply_playback_once()
            restored = wait_for_capture_similar(
                display,
                work / "restored.png",
                baseline,
            )
            assert captures_match(baseline, restored)
    finally:
        openbox.terminate()
        xvfb.terminate()
        openbox.wait(timeout=10)
        xvfb.wait(timeout=10)

    if artifact_name == "linux-1080p-desktop.png":
        save_linux_artifact(restored, "linux-restored.png")

    print(
        f"{artifact_name}: capture_bytes={artifact_path.stat().st_size} "
        f"offset_dx={dx:.2f} offset_dy={dy:.2f}",
    )
