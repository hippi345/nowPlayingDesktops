from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.conftest import make_test_cover
from tests.helpers import FakePlatform, make_runner

from now_playing_desktops.spotify_art import TrackPlayback
from now_playing_desktops.wallpaper_state import WallpaperSessionState

PLAYING = TrackPlayback(
    track_id="t1",
    art_url="https://example.com/art.jpg",
    title="Song",
    artist="Artist",
    is_playing=True,
)
PAUSED = TrackPlayback(
    track_id="t1",
    art_url="https://example.com/art.jpg",
    title="Song",
    artist="Artist",
    is_playing=False,
)


def _write_cover_jpeg(path: Path) -> None:
    make_test_cover().save(path, format="JPEG")


def test_playback_state_machine_play_pause_stop_resume(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.download_album_art",
            side_effect=lambda _u, dest, session=None: _write_cover_jpeg(dest),
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
        assert len(platform.set_calls) == 1

        runner.apply_playback_once()
        assert len(platform.set_calls) == 1

        with patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=PAUSED,
        ):
            runner.apply_playback_once()
        assert platform.wallpaper == original

        with patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=None,
        ):
            runner.apply_playback_once()
        assert platform.wallpaper == original

        with patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=PLAYING,
        ):
            runner.apply_playback_once()
        composed = [p for p in platform.set_calls if p.parent.name == "composed"]
        assert len(composed) == 2


def test_playback_state_machine_spotify_closed_204_restores(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    runner.startup()
    with patch("now_playing_desktops.runner.fetch_playback_with_backoff", return_value=None):
        runner.apply_playback_once()
    assert platform.wallpaper == original


def test_crash_state_restore_on_startup(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    state_path = tmp_path / "state.json"
    WallpaperSessionState(
        original_wallpaper_path=str(original),
        session_active=True,
        generated_wallpaper_dir=str(tmp_path / "cache"),
    ).save(state_path)
    platform = FakePlatform(wallpaper=tmp_path / "generated.png")
    runner = make_runner(tmp_path, platform=platform)
    runner.deps.state_path = state_path
    runner.startup()
    assert platform.wallpaper == original
    assert WallpaperSessionState.load(state_path).session_active is False


def test_dedupe_no_reset_on_same_track(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_with_backoff",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.download_album_art",
            side_effect=lambda _u, dest, session=None: _write_cover_jpeg(dest),
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
        runner.apply_playback_once()
    assert len(platform.set_calls) == 1


def test_cache_hit_skips_second_download_and_compose(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    download_mock = MagicMock(side_effect=lambda _u, dest, session=None: _write_cover_jpeg(dest))
    compose_mock = MagicMock(
        side_effect=lambda cover, **kwargs: __import__(
            "now_playing_desktops.composer", fromlist=["compose_wallpaper"]
        ).compose_wallpaper(cover, **kwargs)
    )
    with (
        patch(
            "now_playing_desktops.runner.download_album_art",
            download_mock,
        ),
        patch(
            "now_playing_desktops.runner.compose_wallpaper",
            compose_mock,
        ),
    ):
        first = runner._compose_path(PLAYING, 1920, 1080)
        second = runner._compose_path(PLAYING, 1920, 1080)
    assert first == second
    download_mock.assert_called_once()
    compose_mock.assert_called_once()


def test_startup_does_not_overwrite_original_with_generated_wallpaper(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    generated = cache / "composed.png"
    generated.write_bytes(b"g")
    original = tmp_path / "real-original.jpg"
    original.write_bytes(b"o")
    state_path = tmp_path / "state.json"
    WallpaperSessionState(
        original_wallpaper_path=str(original),
        session_active=False,
        generated_wallpaper_dir=str(cache),
    ).save(state_path)
    platform = FakePlatform(wallpaper=generated)
    runner = make_runner(tmp_path, platform=platform)
    runner.deps.state_path = state_path
    runner.startup()
    assert WallpaperSessionState.load(state_path).original_wallpaper_path == str(original)


def test_signal_and_atexit_restore_original_wallpaper(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    WallpaperSessionState(
        original_wallpaper_path=str(original),
        session_active=True,
        generated_wallpaper_dir=str(tmp_path / "cache"),
    ).save(tmp_path / "state.json")
    registered: list = []

    def capture(func):
        registered.append(func)
        return func

    with patch("now_playing_desktops.runner.atexit.register", side_effect=capture):
        runner._register_shutdown_handlers()
    assert registered
    registered[0]()
    assert WallpaperSessionState.load(tmp_path / "state.json").session_active is False
