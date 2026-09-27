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
    )


def _fake_reg():
    store: dict[tuple[int, str, str], object] = {}

    def read(root, subkey, name):
        return store.get((root, subkey, name))

    def write_str(root, subkey, name, value):
        store[(root, subkey, name)] = value

    def write_dword(root, subkey, name, value):
        store[(root, subkey, name)] = value

    return store, read, write_str, write_dword


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_capture_copies_transcoded_wallpaper(tmp_path: Path):
    state_dir = tmp_path / "state"
    transcoded = tmp_path / "TranscodedWallpaper"
    transcoded.write_bytes(b"\xff\xd8\xff fake jpeg")
    reported = tmp_path / "missing-on-disk.jpg"

    store, read, write_str, _ = _fake_reg()
    root = 1

    with (
        patch(
            "now_playing_desktops.platforms.windows_restore._transcoded_wallpaper_path",
            return_value=transcoded,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_reg_string",
            side_effect=lambda r, s, n: read(r, s, n),
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_desktop_style",
            return_value={"wallpaper_style": "10", "tile_wallpaper": "0"},
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore._read_background_type",
            return_value=0,
        ),
        patch(
            "now_playing_desktops.platforms.windows_restore.winreg.HKEY_CURRENT_USER",
            root,
        ),
    ):
        snap = capture_windows_restore_snapshot(
            state_dir=state_dir,
            generated_dir=None,
            reported_path=str(reported),
            per_monitor=False,
            monitor_paths={},
        )

    stable = Path(snap["stable_path"])
    assert stable.is_file()
    assert stable.suffix == ".jpg"
    assert snap["wallpaper_style"] == "10"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_restore_calls_spi_with_flags(tmp_path: Path):
    image = tmp_path / "original-wallpaper.png"
    image.write_bytes(b"\x89PNG\r\n")
    snapshot = {
        "stable_path": str(image),
        "wallpaper_style": "6",
        "tile_wallpaper": "0",
        "background_type": 0,
        "per_monitor": False,
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
    image = tmp_path / "original-wallpaper.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    snapshot = {
        "stable_path": str(image),
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
    from tests.helpers import FakePlatform

    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    restore_mock = MagicMock()
    platform.apply_restore_snapshot = restore_mock
    runner = NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            sp=MagicMock(),
            cache_dir=tmp_path / "cache",
            state_path=tmp_path / "state.json",
            poll_interval_seconds=2.5,
        )
    )
    from now_playing_desktops.wallpaper_state import WallpaperSessionState

    WallpaperSessionState(
        original_wallpaper_snapshot={"backend": "windows", "path": str(original)},
        session_active=True,
    ).save(tmp_path / "state.json")
    paused = TrackPlayback("t", "u", "T", "A", is_playing=False)
    with patch(
        "now_playing_desktops.runner.fetch_playback_with_backoff",
        return_value=paused,
    ):
        runner.apply_playback_once()
    restore_mock.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_windows_wallpaper_smoke_snapshot_apply_restore(tmp_path: Path):
    """Live SPI snapshot/apply cycle on the CI desktop."""
    from now_playing_desktops.platforms.windows import WindowsWallpaperPlatform

    platform = WindowsWallpaperPlatform()
    state_dir = tmp_path / "state"
    generated = tmp_path / "generated"
    generated.mkdir()
    snap = platform.capture_restore_snapshot(state_dir=state_dir, generated_dir=generated)
    stable = snap.get("stable_path") or snap.get("path")
    assert stable, "expected a wallpaper path to snapshot"

    test_image = tmp_path / "test-wallpaper.png"
    from PIL import Image

    Image.new("RGB", (64, 64), (40, 120, 200)).save(test_image)
    platform.set_wallpaper(test_image)

    platform.apply_restore_snapshot(snap)

    buffer = __import__("ctypes").create_unicode_buffer(260)
    ok = __import__("ctypes").windll.user32.SystemParametersInfoW(0x0073, 260, buffer, 0)
    assert ok
    restored = buffer.value.strip()
    assert restored
    assert Path(restored).resolve() == Path(stable).resolve()
