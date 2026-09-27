from __future__ import annotations

import io
import logging
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from now_playing_desktops.art_resolution import ItunesUpgradeResult
from now_playing_desktops.playback_types import TrackPlayback
from tests.helpers import FakePlatform, make_runner, mock_load_track_cover_rgba


def _png_bytes(size: tuple[int, int]) -> bytes:
    image = Image.new("RGB", size, (30, 60, 90))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class _InlineThread:
    def __init__(self, target=None, kwargs=None, name=None, daemon=None) -> None:
        self._target = target

    def start(self) -> None:
        if self._target is not None:
            self._target()


def _composed_set_count(platform: FakePlatform) -> int:
    return len([p for p in platform.set_calls if p.parent.name == "composed"])


def test_steady_play_one_track_one_upgrade_over_many_polls(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    small = _png_bytes((300, 300))
    large = _png_bytes((1000, 1000))
    track = TrackPlayback("t1", "", "Song", "Artist", True, art_bytes=small)
    runner = make_runner(tmp_path, platform=platform)
    upgrade = ItunesUpgradeResult(
        image_bytes=large,
        width=1000,
        height=1000,
        smtc_width=300,
        smtc_height=300,
        detail="itunes",
    )

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
            "now_playing_desktops.art_background_upgrade.threading.Thread",
            _InlineThread,
        ),
        patch(
            "now_playing_desktops.art_background_upgrade.try_fetch_itunes_upgrade",
            return_value=upgrade,
        ) as upgrade_fetch,
    ):
        runner.startup()
        for _ in range(20):
            runner.apply_playback_once()

    assert _composed_set_count(platform) == 2
    upgrade_fetch.assert_called_once()


def test_steady_play_without_upgrade_single_apply(tmp_path: Path, monkeypatch, caplog):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    track = TrackPlayback("t1", "", "Song", "Artist", True, art_bytes=_png_bytes((300, 300)))
    runner = make_runner(tmp_path, platform=platform)

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
            "now_playing_desktops.art_background_upgrade.threading.Thread",
            _InlineThread,
        ),
        patch(
            "now_playing_desktops.art_background_upgrade.try_fetch_itunes_upgrade",
            return_value=None,
        ) as upgrade_fetch,
        caplog.at_level(logging.DEBUG),
    ):
        runner.startup()
        for _ in range(20):
            runner.apply_playback_once()

    assert _composed_set_count(platform) == 1
    upgrade_fetch.assert_called_once()
    assert caplog.text.count("Track unchanged; skipping wallpaper update") == 19


def test_pause_resume_no_second_upgrade_uses_stored_art(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    small = _png_bytes((300, 300))
    large = _png_bytes((1000, 1000))
    playing = TrackPlayback("t1", "", "Song", "Artist", True, art_bytes=small)
    paused = TrackPlayback("t1", "", "Song", "Artist", False, art_bytes=small)
    runner = make_runner(tmp_path, platform=platform)
    upgrade = ItunesUpgradeResult(
        image_bytes=large,
        width=1000,
        height=1000,
        smtc_width=300,
        smtc_height=300,
        detail="itunes",
    )
    fetch_values = [playing]

    def fetch_side_effect(_deps):
        return fetch_values[-1]

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            side_effect=fetch_side_effect,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
        patch(
            "now_playing_desktops.art_background_upgrade.threading.Thread",
            _InlineThread,
        ),
        patch(
            "now_playing_desktops.art_background_upgrade.try_fetch_itunes_upgrade",
            return_value=upgrade,
        ) as upgrade_fetch,
    ):
        runner.startup()
        runner.apply_playback_once()
        assert _composed_set_count(platform) == 2
        restore_calls_before = sum(1 for p in platform.set_calls if p.name == "orig.jpg")

        fetch_values.append(paused)
        runner.apply_playback_once()
        restore_calls_after_pause = sum(1 for p in platform.set_calls if p.name == "orig.jpg")
        assert restore_calls_after_pause == restore_calls_before + 1

        fetch_values.append(playing)
        runner.apply_playback_once()
        assert _composed_set_count(platform) == 3
        upgrade_fetch.assert_called_once()
        assert runner._upgraded_art_bytes["t1"] == large
