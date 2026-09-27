from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

from now_playing_desktops.art_cache import ComposedArtCache
from now_playing_desktops.compose_verify import schedule_compose_quality_verification
from now_playing_desktops.composer import compose_wallpaper, save_wallpaper
from now_playing_desktops.playback_types import TrackPlayback
from tests.helpers import FakePlatform, make_runner, make_sample_cover, mock_load_track_cover_rgba

LAPTOP_CANVAS = (2496, 1664)


def test_compose_2496x1664_under_three_seconds():
    cover = make_sample_cover(1000)
    started = time.perf_counter()
    composed = compose_wallpaper(
        cover,
        title="River",
        artist="Cheat Codes",
        width=LAPTOP_CANVAS[0],
        height=LAPTOP_CANVAS[1],
    )
    elapsed = time.perf_counter() - started
    print(f"compose_2496x1664_seconds={elapsed:.3f}")
    assert composed.size == LAPTOP_CANVAS
    assert elapsed < 3.0, f"compose took {elapsed:.2f}s"


def test_apply_does_not_block_on_compose_verification(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOW_PLAYING_COMPOSE_VERIFY", "1")
    verify_started = threading.Event()
    verify_finished = threading.Event()
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    track = TrackPlayback("t", "", "Song", "Artist", True, art_bytes=b"x")
    runner = make_runner(tmp_path, platform=platform)

    def slow_verify(**_kwargs):
        verify_started.set()
        verify_finished.wait(timeout=5)
        verify_finished.set()

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=track,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
        patch(
            "now_playing_desktops.runner.schedule_compose_quality_verification",
            side_effect=slow_verify,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()

    assert platform.set_calls
    assert verify_started.is_set()
    verify_finished.set()


def test_composed_disk_cache_hit_skips_recompose(tmp_path: Path, caplog):
    cache = ComposedArtCache(tmp_path / "composed")
    cover = make_sample_cover(400)
    track = TrackPlayback("id", "art", "Title", "Artist", True)
    material = track.composed_art_material_key
    composed = compose_wallpaper(
        cover,
        title=track.title,
        artist=track.artist,
        width=1920,
        height=1080,
    )
    scratch = tmp_path / "scratch.png"
    save_wallpaper(composed, scratch)
    cached_path = cache.put(track.track_id, material, 1920, 1080, scratch)
    assert cache.get(track.track_id, material, 1920, 1080) == cached_path

    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    runner = make_runner(tmp_path, platform=platform)
    runner._composed_cache = cache
    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=track,
        ),
        patch("now_playing_desktops.runner.compose_wallpaper") as compose_mock,
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
    compose_mock.assert_not_called()
    assert "cache=hit" in caplog.text


def test_schedule_compose_verification_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_COMPOSE_VERIFY", raising=False)
    cover = make_sample_cover(320)
    composed = compose_wallpaper(cover, title="T", artist="A", width=320, height=240)
    with patch("threading.Thread") as thread_mock:
        schedule_compose_quality_verification(
            composed=composed,
            cover=cover,
            title="T",
            artist="A",
            width=320,
            height=240,
        )
    thread_mock.assert_not_called()
