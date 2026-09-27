from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from now_playing_desktops.art_resolution import resolve_track_art, try_fetch_itunes_upgrade
from now_playing_desktops.config import online_art_enabled
from now_playing_desktops.platforms.autostart import build_run_argv
from now_playing_desktops.playback_types import TrackPlayback
from tests.helpers import FakePlatform, make_runner, mock_load_track_cover_rgba


def _png_bytes(size: tuple[int, int] = (300, 300)) -> bytes:
    image = Image.new("RGB", size, (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_online_art_enabled_defaults_true(monkeypatch):
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)
    assert online_art_enabled() is True


def test_online_art_disabled_by_zero(monkeypatch):
    monkeypatch.setenv("NOW_PLAYING_ONLINE_ART", "0")
    assert online_art_enabled() is False


def test_resolve_track_art_no_network_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOW_PLAYING_ONLINE_ART", "0")
    track = TrackPlayback("id", "", "Title", "Artist", True)
    session = MagicMock()
    resolved = resolve_track_art(track, download_dir=tmp_path, session=session)
    assert resolved.source == "placeholder"
    session.get.assert_not_called()


def test_try_fetch_itunes_upgrade_skipped_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOW_PLAYING_ONLINE_ART", "0")
    track = TrackPlayback("id", "", "Title", "Artist", True, art_bytes=_png_bytes())
    session = MagicMock()
    assert (
        try_fetch_itunes_upgrade(
            track,
            smtc_max_dim=300,
            download_dir=tmp_path,
            session=session,
        )
        is None
    )
    session.get.assert_not_called()


def test_runner_does_not_schedule_upgrade_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOW_PLAYING_ONLINE_ART", "0")
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    track = TrackPlayback("t1", "", "Song", "Artist", True, art_bytes=_png_bytes())
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
        patch.object(runner._art_upgrader, "schedule") as schedule_mock,
    ):
        runner.startup()
        runner.apply_playback_once()

    schedule_mock.assert_not_called()


def test_cli_no_online_art_from_env_file(tmp_path: Path, monkeypatch):
    from now_playing_desktops.cli import main

    env_file = tmp_path / "offline.env"
    env_file.write_text("NOW_PLAYING_ONLINE_ART=0\n", encoding="utf-8")
    monkeypatch.delenv("NOW_PLAYING_ONLINE_ART", raising=False)

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=MagicMock()),
        patch("now_playing_desktops.cli.build_playback_provider", return_value=MagicMock()),
        patch(
            "now_playing_desktops.single_instance.ensure_single_run_instance",
            return_value=MagicMock(release=MagicMock()),
        ),
        patch("now_playing_desktops.cli.NowPlayingRunner"),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
        patch("now_playing_desktops.cli.state_file_path", return_value=tmp_path / "state.json"),
    ):
        code = main(["run", "--source", "local", "--env-file", str(env_file), "--once"])

    assert code == 0
    assert online_art_enabled() is False


def test_cli_no_online_art_flag_overrides(tmp_path: Path, monkeypatch):
    from now_playing_desktops.cli import main

    monkeypatch.setenv("NOW_PLAYING_ONLINE_ART", "1")

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=MagicMock()),
        patch("now_playing_desktops.cli.build_playback_provider", return_value=MagicMock()),
        patch(
            "now_playing_desktops.single_instance.ensure_single_run_instance",
            return_value=MagicMock(release=MagicMock()),
        ),
        patch("now_playing_desktops.cli.NowPlayingRunner"),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
        patch("now_playing_desktops.cli.state_file_path", return_value=tmp_path / "state.json"),
    ):
        code = main(["run", "--source", "local", "--no-online-art", "--once"])

    assert code == 0
    assert online_art_enabled() is False


def test_build_run_argv_includes_no_online_art(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("SPOTIPY_CLIENT_ID=id\n", encoding="utf-8")
    argv = build_run_argv(env_file=env, username="u", source="local", no_online_art=True)
    assert "--no-online-art" in argv
