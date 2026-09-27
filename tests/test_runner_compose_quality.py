from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from now_playing_desktops.spotify_art import TrackPlayback
from tests.helpers import FakePlatform, make_runner, mock_load_track_cover_rgba

PLAYING = TrackPlayback(
    track_id="quality-track",
    art_url="https://example.com/art.jpg",
    title="Song",
    artist="Artist",
    is_playing=True,
)


def test_failed_quality_checks_still_apply_and_cache(tmp_path: Path, caplog):
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"x")
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
        patch(
            "now_playing_desktops.verification.wallpaper_analysis.assert_glass_panel_present",
            side_effect=AssertionError("Glass ring not distinct"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        runner.startup()
        runner.apply_playback_once()

    assert len(platform.set_calls) == 1
    composed_dir = tmp_path / "cache" / "composed"
    assert any(composed_dir.glob("*.png"))
    assert any("applying wallpaper anyway" in r.message for r in caplog.records)


def test_strict_compose_verification_still_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOW_PLAYING_STRICT_COMPOSE_VERIFY", "1")
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"x")
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
        patch(
            "now_playing_desktops.verification.wallpaper_analysis.assert_glass_panel_present",
            side_effect=AssertionError("bad glass"),
        ),
    ):
        runner.startup()
        runner.apply_playback_once()

    assert len(platform.set_calls) == 0


def test_failed_quality_checks_log_warning_not_error(tmp_path: Path, caplog):
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"x")
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
        patch(
            "now_playing_desktops.verification.wallpaper_analysis.assert_glass_panel_present",
            side_effect=AssertionError("Glass ring not distinct"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        runner.startup()
        runner.apply_playback_once()

    assert any("applying wallpaper anyway" in r.message for r in caplog.records)
    assert not any(
        r.levelno == logging.ERROR and "Failed to update wallpaper" in r.message
        for r in caplog.records
    )
