from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from now_playing_desktops.composer import plan_wallpaper_layout, render_backdrop
from now_playing_desktops.config import user_config_dir
from now_playing_desktops.runner import NowPlayingRunner, RunnerDeps
from now_playing_desktops.spotify_art import TrackPlayback
from now_playing_desktops.verification.wallpaper_analysis import (
    assert_glass_panel_present,
    assert_no_backdrop_band_edges,
    assert_title_text_present,
)
from tests.helpers import FakePlatform, make_sample_cover

LONG_TITLE = "Long Title For Centering"
PLAYING = TrackPlayback(
    track_id="autostart-path",
    art_url="https://example.com/art.jpg",
    title=LONG_TITLE,
    artist="Test Artist",
    is_playing=True,
)


def test_compose_from_foreign_cwd_with_env_file_like_autostart(tmp_path: Path, monkeypatch):
    foreign_cwd = tmp_path / "foreign"
    foreign_cwd.mkdir()
    config_dir = tmp_path / "config" / "now-playing-desktops"
    config_dir.mkdir(parents=True)
    env_file = config_dir / ".env"
    env_file.write_text(
        "SPOTIPY_CLIENT_ID=id\nSPOTIPY_CLIENT_SECRET=secret\nSPOTIPY_CLIENT_USERNAME=u\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("now_playing_desktops.cli.user_config_dir", lambda: config_dir)
    monkeypatch.setattr("now_playing_desktops.config.user_config_dir", lambda: config_dir)
    monkeypatch.chdir(foreign_cwd)

    from now_playing_desktops.cli import _ensure_runtime_working_directory

    _ensure_runtime_working_directory()

    cover = make_sample_cover()
    cover_path = config_dir / "cache" / "downloads" / "autostart-path.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover.save(cover_path, format="JPEG")

    platform = FakePlatform(screen=(1664, 1109))
    runner = NowPlayingRunner(
        RunnerDeps(
            platform=platform,
            playback_provider=MagicMock(),
            cache_dir=config_dir / "cache",
            state_path=config_dir / "state.json",
            poll_interval_seconds=2.5,
        )
    )

    layout = plan_wallpaper_layout(
        cover,
        title=LONG_TITLE,
        artist="Test Artist",
        width=1664,
        height=1109,
    )

    with patch(
        "now_playing_desktops.runner.load_track_cover",
        side_effect=lambda track, *, download_dir, session=None: Image.open(cover_path).convert(
            "RGBA"
        ),
    ):
        from now_playing_desktops.apply_timing import ApplyTiming

        composed_path = runner._compose_path(PLAYING, 1664, 1109, ApplyTiming())

    assert composed_path.is_file()
    assert os.getcwd() == str(config_dir)

    with Image.open(composed_path) as composed:
        with Image.open(cover_path) as cover_image:
            cover = cover_image.convert("RGB")
        backdrop = render_backdrop(cover, 1664, 1109)
        assert_glass_panel_present(composed, layout, backdrop)
        assert_title_text_present(composed, layout)
        assert_no_backdrop_band_edges(composed, cover, layout=layout)


def test_user_config_dir_default_name():
    path = user_config_dir()
    assert path.name == "now-playing-desktops"
