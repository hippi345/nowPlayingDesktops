from __future__ import annotations

import io
import logging
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from now_playing_desktops.art_background_upgrade import ArtUpgradeTicket
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


class _DeferredThread:
    def __init__(self, target=None, kwargs=None, name=None, daemon=None) -> None:
        self._target = target

    def start(self) -> None:
        return


def _composed_set_count(platform: FakePlatform) -> int:
    return len([p for p in platform.set_calls if p.parent.name == "composed"])


def test_immediate_apply_does_not_block_on_itunes(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    from unittest.mock import MagicMock

    from now_playing_desktops.cover_art import load_track_cover

    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    track = TrackPlayback("t1", "", "Song", "Artist", True, art_bytes=_png_bytes((300, 300)))
    runner = make_runner(tmp_path, platform=platform)
    session = MagicMock()

    def load_cover(track_arg, *, download_dir, session=None):
        return load_track_cover(track_arg, download_dir=download_dir, session=session)

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=track,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=load_cover,
        ),
        patch(
            "now_playing_desktops.art_background_upgrade.threading.Thread",
            _DeferredThread,
        ),
    ):
        runner.deps.session = session
        runner.startup()
        runner.apply_playback_once()

    session.get.assert_not_called()
    assert _composed_set_count(platform) == 1


def test_background_upgrade_reapplies_when_better(tmp_path: Path, caplog, monkeypatch):
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
        ),
        caplog.at_level(logging.INFO),
    ):
        runner.startup()
        runner.apply_playback_once()

    assert _composed_set_count(platform) == 2
    assert "Upgraded art Apply took" in caplog.text


def test_stale_upgrade_ignored_after_track_change(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    track_a = TrackPlayback("t1", "", "Song A", "Artist", True, art_bytes=_png_bytes((300, 300)))
    track_b = TrackPlayback("t2", "", "Song B", "Artist", True, art_bytes=_png_bytes((300, 300)))
    runner = make_runner(tmp_path, platform=platform)
    ticket = ArtUpgradeTicket(generation=1, track_id="t1", smtc_max_dim=300)
    upgraded = TrackPlayback(
        "t1",
        "",
        "Song A",
        "Artist",
        True,
        art_bytes=_png_bytes((1000, 1000)),
    )

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=track_a,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        runner.startup()
        runner.apply_playback_once()

    composed_after_first = _composed_set_count(platform)

    with patch(
        "now_playing_desktops.runner.fetch_playback_for_runner",
        return_value=track_b,
    ):
        runner._apply_upgraded_art(upgraded, ticket)

    assert _composed_set_count(platform) == composed_after_first


def test_stale_upgrade_ignored_after_pause(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    playing = TrackPlayback("t1", "", "Song", "Artist", True, art_bytes=_png_bytes((300, 300)))
    paused = TrackPlayback("t1", "", "Song", "Artist", False, art_bytes=_png_bytes((300, 300)))
    runner = make_runner(tmp_path, platform=platform)
    ticket = ArtUpgradeTicket(generation=1, track_id="t1", smtc_max_dim=300)
    upgraded = TrackPlayback(
        "t1",
        "",
        "Song",
        "Artist",
        True,
        art_bytes=_png_bytes((1000, 1000)),
    )

    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=playing,
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
        ),
    ):
        runner.startup()
        runner.apply_playback_once()

    composed_after_play = _composed_set_count(platform)

    with patch(
        "now_playing_desktops.runner.fetch_playback_for_runner",
        return_value=paused,
    ):
        runner.apply_playback_once()
        runner._apply_upgraded_art(upgraded, ticket)

    assert _composed_set_count(platform) == composed_after_play
