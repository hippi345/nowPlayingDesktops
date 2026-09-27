from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from now_playing_desktops.cover_art import prepare_cover_image
from now_playing_desktops.playback_factory import build_playback_provider
from now_playing_desktops.playback_source import resolve_effective_playback_source
from now_playing_desktops.playback_types import TrackPlayback
from now_playing_desktops.sources.local.linux_mpris import LinuxMprisProvider
from now_playing_desktops.sources.local.macos_spotify import MacOsSpotifyProvider
from now_playing_desktops.sources.local.windows_smtc import WindowsSmtcProvider
from tests.helpers import FakePlatform, make_runner, mock_load_track_cover_rgba

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


def test_auto_selects_spotify_when_client_id_present(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    assert resolve_effective_playback_source(explicit="auto") == "spotify"


def test_auto_selects_local_without_client_id(monkeypatch):
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    assert resolve_effective_playback_source(explicit="auto") == "local"


def test_build_playback_provider_local(monkeypatch, caplog):
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    with caplog.at_level(logging.INFO):
        provider = build_playback_provider(source_setting="local", username=None)
    assert provider is not None
    assert provider.source_name == "local"
    assert "Playback source: local" in caplog.text


def test_windows_smtc_provider_parses_session(monkeypatch):
    track = TrackPlayback(
        track_id="abc",
        art_url="",
        title="Title",
        artist="Artist",
        album="Album",
        is_playing=True,
        art_bytes=b"thumb",
    )
    monkeypatch.setattr(
        WindowsSmtcProvider,
        "_read_session",
        lambda self: track,
    )
    provider = WindowsSmtcProvider()
    assert provider.fetch_current() == track


def test_linux_mpris_provider_reads_metadata(monkeypatch):
    track = TrackPlayback(
        track_id="x",
        art_url="file:///tmp/art.jpg",
        title="T",
        artist="A",
        album="Al",
        is_playing=True,
    )
    monkeypatch.setattr(LinuxMprisProvider, "_read_session", lambda self: track)
    assert LinuxMprisProvider().fetch_current() == track


def test_macos_provider_reads_osascript(monkeypatch):
    track = TrackPlayback("id", "http://art", "T", "A", True, album="Al")
    monkeypatch.setattr(MacOsSpotifyProvider, "_read_session", lambda self: track)
    assert MacOsSpotifyProvider().fetch_current() == track


def test_spotify_provider_wraps_fetch(monkeypatch):
    monkeypatch.setenv("SPOTIPY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIPY_CLIENT_SECRET", "secret")
    sp = MagicMock()
    with (
        patch(
            "now_playing_desktops.sources.spotify_provider.create_spotify_client",
            return_value=(sp, MagicMock(), MagicMock()),
        ),
        patch(
            "now_playing_desktops.sources.spotify_provider.fetch_playback_with_backoff",
            return_value=PLAYING,
        ) as fetch_mock,
    ):
        from now_playing_desktops.sources.spotify_provider import SpotifyPlaybackProvider

        provider = SpotifyPlaybackProvider.from_username("user")
        assert provider is not None
        assert provider.fetch_current() == PLAYING
        fetch_mock.assert_called_once()


def test_low_res_thumbnail_upscaled(caplog):
    small = Image.new("RGB", (200, 200), (10, 20, 30))
    with caplog.at_level(logging.INFO):
        out = prepare_cover_image(small)
    assert max(out.size) >= 400
    assert "Upscaled low-resolution thumbnail" in caplog.text


def test_local_without_art_still_applies_wallpaper(tmp_path: Path, caplog):
    import logging

    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
    track = TrackPlayback(
        track_id="local1",
        art_url="",
        title="Song",
        artist="Artist",
        is_playing=True,
    )
    runner = make_runner(tmp_path, platform=platform)
    with (
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=track,
        ),
        patch(
            "now_playing_desktops.art_resolution.lookup_itunes_artwork_url",
            return_value=None,
        ),
        caplog.at_level(logging.INFO),
    ):
        runner.startup()
        runner.apply_playback_once()
    assert len(platform.set_calls) == 1
    assert "Track art source: placeholder" in caplog.text


def test_pause_restore_parity_through_shared_pipeline(tmp_path: Path):
    platform = FakePlatform(wallpaper=tmp_path / "orig.jpg")
    (tmp_path / "orig.jpg").write_bytes(b"orig")
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
    with patch(
        "now_playing_desktops.runner.fetch_playback_for_runner",
        return_value=PAUSED,
    ):
        runner.apply_playback_once()
        assert platform.wallpaper == tmp_path / "orig.jpg"


def test_build_run_argv_includes_source_local(tmp_path: Path):
    from now_playing_desktops.platforms.autostart import build_run_argv

    env = tmp_path / ".env"
    env.write_text("SPOTIPY_CLIENT_ID=id\n", encoding="utf-8")
    argv = build_run_argv(env_file=env, username="u", source="local")
    assert "--source" in argv
    assert "local" in argv
    assert str(env) in argv


def test_autostart_local_without_spotify_credentials(tmp_path: Path, monkeypatch):
    from now_playing_desktops.platforms import autostart

    monkeypatch.setattr(autostart.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    with (
        patch("now_playing_desktops.env_loader.load_environment"),
        patch("now_playing_desktops.env_loader.find_env_file", return_value=None),
    ):
        autostart.enable_autostart(source="local")
    desktop = tmp_path / "config" / "autostart" / "now-playing-desktops.desktop"
    assert desktop.is_file()
    assert "--source local" in desktop.read_text(encoding="utf-8")
