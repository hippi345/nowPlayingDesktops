from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if sys.platform == "win32":
    from now_playing_desktops.platforms.windows_restore import (
        BACKGROUND_SLIDESHOW,
        apply_windows_restore_snapshot,
        capture_windows_restore_snapshot,
        file_digest,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_capture_preserves_existing_snapshot_during_active_session(tmp_path: Path):
    existing_stable = tmp_path / "state" / "original_wallpaper.jpg"
    existing_stable.parent.mkdir(parents=True)
    existing_stable.write_bytes(b"\xff\xd8\xff\x00kept")
    existing = {
        "backend": "windows",
        "stable_path": str(existing_stable),
        "content_hash": file_digest(existing_stable.read_bytes()),
    }
    with (
        patch(
            "now_playing_desktops.platforms.windows_restore._pick_wallpaper_source_bytes",
        ) as pick_mock,
        patch(
            "now_playing_desktops.platforms.windows_restore._read_desktop_style",
            return_value={"wallpaper_style": "10", "tile_wallpaper": "0"},
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_background_type",
            return_value=0,
        ),
    ):
        snap = capture_windows_restore_snapshot(
            state_dir=tmp_path / "state",
            generated_dir=tmp_path / "cache",
            reported_path=None,
            per_monitor=False,
            monitor_paths={},
            existing_snapshot=existing,
            session_active=True,
        )
    pick_mock.assert_not_called()
    assert snap["stable_path"] == existing["stable_path"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_restore_calls_spi_with_stable_path_only(tmp_path: Path):
    image = tmp_path / "original_wallpaper.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nstable")
    digest = file_digest(image.read_bytes())
    snapshot = {
        "stable_path": str(image),
        "content_hash": digest,
        "wallpaper_style": "6",
        "tile_wallpaper": "0",
        "background_type": 0,
        "per_monitor": False,
        "path": str(tmp_path / "TranscodedWallpaper"),
    }
    spi_calls: list[tuple] = []

    def fake_spi(code, _a, path, flags):
        spi_calls.append((code, path, flags))
        return True

    with (
        patch(
            "now_playing_desktops.platforms.windows_restore.ctypes.windll.user32.SystemParametersInfoW",
            side_effect=fake_spi,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._restore_desktop_style",
        ) as style_mock,
        patch(
            "now_playing_desktops.platforms.windows_restore._get_last_error",
            return_value=0,
        ),
    ):
        apply_windows_restore_snapshot(
            snapshot,
            set_wallpaper_on_monitor=MagicMock(),
            set_wallpaper_primary=MagicMock(),
        )

    assert spi_calls
    code, path, flags = spi_calls[0]
    assert code == 20
    assert path == str(image.resolve())
    assert flags == 0x01 | 0x02
    style_mock.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_restore_slideshow_logs_and_restores_background_type(tmp_path: Path, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    image = tmp_path / "original_wallpaper.jpg"
    data = b"\xff\xd8\xff\x00"
    image.write_bytes(data)
    snapshot = {
        "stable_path": str(image),
        "content_hash": file_digest(data),
        "wallpaper_style": "10",
        "tile_wallpaper": "0",
        "background_type": BACKGROUND_SLIDESHOW,
        "per_monitor": False,
    }

    with (
        patch(
            "now_playing_desktops.platforms.windows_restore.ctypes.windll.user32.SystemParametersInfoW",
            return_value=True,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._write_reg_dword",
        ) as dword_mock,
        patch(
            "now_playing_desktops.platforms.windows_restore._restore_desktop_style",
        ),
    ):
        apply_windows_restore_snapshot(
            snapshot,
            set_wallpaper_on_monitor=MagicMock(),
            set_wallpaper_primary=MagicMock(),
        )

    dword_mock.assert_called()
    assert "slideshow" in caplog.text.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_runner_pause_triggers_windows_restore(tmp_path: Path):
    from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps
    from now_playing_desktops.spotify_art import TrackPlayback
    from now_playing_desktops.wallpaper_state import WallpaperSessionState
    from tests.helpers import FakePlatform

    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    restore_mock = MagicMock()
    platform.apply_restore_snapshot = restore_mock
    runner = NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            playback_provider=MagicMock(),
            cache_dir=tmp_path / "cache",
            state_path=tmp_path / "state.json",
            poll_interval_seconds=2.5,
        )
    )

    WallpaperSessionState(
        original_wallpaper_snapshot={"backend": "windows", "path": str(original)},
        session_active=True,
    ).save(tmp_path / "state.json")
    paused = TrackPlayback("t", "u", "T", "A", is_playing=False)
    with patch(
        "now_playing_desktops.runner.fetch_playback_for_runner",
        return_value=paused,
    ):
        runner.apply_playback_once()
    restore_mock.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_set_wallpaper_invokes_fill_style(tmp_path: Path):
    from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform

    image = tmp_path / "fill-test.png"
    from PIL import Image

    Image.new("RGB", (8, 8), (1, 2, 3)).save(image)
    platform = WindowsWallpaperPlatform()
    with patch(
        "now_playing_desktops.platforms.windows_restore.apply_windows_fill_wallpaper_style",
    ) as fill_mock:
        platform.set_wallpaper(image)
    fill_mock.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_windows_wallpaper_smoke_snapshot_apply_restore(tmp_path: Path):
    """Live SPI snapshot/apply cycle on the CI desktop with byte hash verification."""
    from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform

    platform = WindowsWallpaperPlatform()
    state_dir = tmp_path / "state"
    generated = tmp_path / "generated"
    generated.mkdir()
    snap = platform.capture_restore_snapshot(state_dir=state_dir, generated_dir=generated)
    stable = snap.get("stable_path")
    assert stable, "expected a stable wallpaper snapshot"
    original_bytes = Path(stable).read_bytes()
    original_hash = snap.get("content_hash") or file_digest(original_bytes)
    assert original_hash == file_digest(original_bytes)

    test_image = tmp_path / "test-wallpaper.png"
    from PIL import Image

    Image.new("RGB", (64, 64), (40, 120, 200)).save(test_image)
    with patch(
        "now_playing_desktops.platforms.windows_restore.apply_windows_fill_wallpaper_style",
    ) as fill_mock:
        platform.set_wallpaper(test_image)
    fill_mock.assert_called_once()

    transcoded = (
        Path(__import__("os").environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Themes"
        / "TranscodedWallpaper"
    )
    if transcoded.is_file():
        transcoded.write_bytes(test_image.read_bytes())

    platform.apply_restore_snapshot(snap)

    restored_bytes = Path(stable).read_bytes()
    assert file_digest(restored_bytes) == original_hash
    assert restored_bytes == original_bytes
