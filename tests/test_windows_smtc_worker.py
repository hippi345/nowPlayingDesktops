from __future__ import annotations

import asyncio
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from now_playing_desktops.playback_types import TrackPlayback
from now_playing_desktops.runner import NowPlayingRunner
from now_playing_desktops.sources.local.windows_smtc_worker import (
    SMTC_CONSECUTIVE_TIMEOUTS_BEFORE_REBUILD,
    SmtcSessionWorker,
    reset_smtc_worker,
)
from tests.helpers import FakePlatform, make_runner, mock_load_track_cover_rgba


@pytest.fixture(autouse=True)
def _reset_global_smtc_worker():
    if sys.platform == "win32":
        reset_smtc_worker()
    yield
    if sys.platform == "win32":
        reset_smtc_worker()


def test_worker_survives_hung_winrt_call(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows-only MTA worker")

    async def hung_read():
        await asyncio.sleep(3600)

    monkeypatch.setattr(
        "now_playing_desktops.sources.local.windows_smtc_worker.read_spotify_session_async",
        hung_read,
    )
    worker = SmtcSessionWorker()
    started = time.monotonic()
    result = worker.read_spotify_session(timeout=0.5)
    elapsed = time.monotonic() - started
    worker.shutdown()
    assert result is None
    assert elapsed < 2.0
    assert worker.consecutive_timeouts == 1


def test_worker_rebuilds_after_repeated_timeouts(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows-only MTA worker")

    async def hung_read():
        await asyncio.sleep(3600)

    monkeypatch.setattr(
        "now_playing_desktops.sources.local.windows_smtc_worker.read_spotify_session_async",
        hung_read,
    )
    worker = SmtcSessionWorker()
    for _ in range(SMTC_CONSECUTIVE_TIMEOUTS_BEFORE_REBUILD):
        assert worker.read_spotify_session(timeout=0.2) is None
    assert worker.consecutive_timeouts == 0
    worker.shutdown()


def test_runner_local_paused_then_playing_applies_tile(tmp_path):
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    paused = TrackPlayback("t1", "", "River", "Cheat Codes", False, art_bytes=b"x")
    playing = TrackPlayback("t1", "", "River", "Cheat Codes", True, art_bytes=b"x")
    runner = make_runner(tmp_path, platform=platform)
    fetch_values = [paused, paused, playing]

    def fetch_side_effect(_deps):
        return fetch_values.pop(0) if fetch_values else playing

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            side_effect=fetch_side_effect,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()
        assert len(platform.set_calls) == 0
        runner.apply_playback_once()
        assert len(platform.set_calls) == 0
        runner.apply_playback_once()
        assert len([p for p in platform.set_calls if p.parent.name == "composed"]) == 1


def test_runner_poll_tick_logged(tmp_path, caplog):
    import logging

    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    runner = make_runner(tmp_path, platform=platform)
    runner.deps.sleep = MagicMock(side_effect=KeyboardInterrupt)
    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=None,
        ),
        patch.object(NowPlayingRunner, "startup"),
        caplog.at_level(logging.DEBUG),pytest.raises(KeyboardInterrupt)
    ):
        runner.run_forever()
    assert "poll tick 1" in caplog.text
