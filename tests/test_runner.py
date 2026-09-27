from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from now_playing_desktops.apply_timing import ApplyTiming
from now_playing_desktops.spotify_art import TrackPlayback
from now_playing_desktops.wallpaper_state import WallpaperSessionState
from tests.helpers import FakePlatform, make_runner, make_test_cover, mock_load_track_cover_rgba

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
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
        assert len(platform.set_calls) == 1

        runner.apply_playback_once()
        assert len(platform.set_calls) == 1

        with patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PAUSED,
        ):
            runner.apply_playback_once()
        assert platform.wallpaper == original

        with patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=None,
        ):
            runner.apply_playback_once()
        assert platform.wallpaper == original

        with patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
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
    with patch("now_playing_desktops.runner.fetch_playback_for_runner", return_value=None):
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
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
        runner.apply_playback_once()
    assert len(platform.set_calls) == 1


def test_idle_no_original_restore_logged_once(tmp_path: Path, caplog):
    import logging

    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"x")
    runner = make_runner(tmp_path, platform=platform)
    runner._now_playing_wallpaper_active = True
    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PAUSED,
        ),
        caplog.at_level(logging.INFO),
    ):
        runner.apply_playback_once()
        runner.apply_playback_once()
        runner.apply_playback_once()
    info_lines = [
        r.message
        for r in caplog.records
        if r.levelno == logging.INFO and r.message == "No saved original wallpaper to restore"
    ]
    assert len(info_lines) == 1


def test_pause_restores_once_then_skips_while_still_paused(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    restore_mock = MagicMock(return_value=True)
    runner.restore_original_wallpaper = restore_mock

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
        assert runner._now_playing_wallpaper_active is True

    with patch(
        "now_playing_desktops.runner.fetch_playback_for_runner",
        return_value=PAUSED,
    ):
        runner.apply_playback_once()
        runner.apply_playback_once()
        runner.apply_playback_once()

    assert restore_mock.call_count == 1
    assert runner._now_playing_wallpaper_active is False


def test_resume_same_track_reapplies_without_recompose_when_cached(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    compose_mock = MagicMock(
        side_effect=lambda cover, **kwargs: __import__(
            "now_playing_desktops.composer",
            fromlist=["compose_wallpaper"],
        ).compose_wallpaper(cover, **kwargs)
    )

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
        patch("now_playing_desktops.runner.compose_wallpaper", compose_mock),
    ):
        runner.startup()
        runner.apply_playback_once()
        assert len(platform.set_calls) == 1

        with patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PAUSED,
        ):
            runner.apply_playback_once()
        assert platform.wallpaper == original

        with patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ):
            runner.apply_playback_once()
        assert compose_mock.call_count == 1
        composed_calls = [p for p in platform.set_calls if p.parent.name == "composed"]
        assert len(composed_calls) == 2


def test_spotify_closed_restores_when_session_disappears(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    restore_mock = MagicMock(return_value=True)
    runner.restore_original_wallpaper = restore_mock

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()

    with patch("now_playing_desktops.runner.fetch_playback_for_runner", return_value=None):
        runner.apply_playback_once()
        runner.apply_playback_once()

    assert restore_mock.call_count == 1
    assert runner._now_playing_wallpaper_active is False


def test_cache_hit_skips_second_download_and_compose(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    runner = make_runner(tmp_path, platform=platform)
    download_mock = MagicMock(side_effect=mock_load_track_cover_rgba)
    compose_mock = MagicMock(
        side_effect=lambda cover, **kwargs: __import__(
            "now_playing_desktops.composer", fromlist=["compose_wallpaper"]
        ).compose_wallpaper(cover, **kwargs)
    )
    with (
        patch(
            "now_playing_desktops.runner.load_track_cover",
            download_mock,
        ),
        patch(
            "now_playing_desktops.runner.compose_wallpaper",
            compose_mock,
        ),
    ):
        timing = ApplyTiming()
        first = runner._compose_path(PLAYING, 1920, 1080, timing)
        second = runner._compose_path(PLAYING, 1920, 1080, timing)
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
    state = WallpaperSessionState.load(tmp_path / "state.json")
    assert state.session_active is False
    assert state.original_wallpaper_path is None
    assert state.original_wallpaper_snapshot is None


def test_second_restore_after_run_reports_nothing(tmp_path: Path, capsys):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    state_path = tmp_path / "state.json"
    runner = make_runner(tmp_path, platform=platform)
    runner.deps.state_path = state_path

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()

    assert runner.restore_original_wallpaper() is True
    cleared = WallpaperSessionState.load(state_path)
    assert cleared.session_active is False
    assert cleared.original_wallpaper_snapshot is None
    assert cleared.original_wallpaper_path is None
    assert runner.restore_original_wallpaper() is False


def test_failed_restore_keeps_session_state(tmp_path: Path):
    state_path = tmp_path / "state.json"
    snapshot = {"backend": "fake", "path": "/missing.png"}
    WallpaperSessionState(
        original_wallpaper_snapshot=snapshot,
        session_active=True,
    ).save(state_path)
    platform = FakePlatform()
    platform.apply_restore_snapshot = MagicMock(side_effect=RuntimeError("boom"))

    runner = make_runner(tmp_path, platform=platform)
    runner.deps.state_path = state_path
    assert runner.restore_original_wallpaper() is False

    loaded = WallpaperSessionState.load(state_path)
    assert loaded.session_active is True
    assert loaded.original_wallpaper_snapshot == snapshot
