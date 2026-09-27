from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from now_playing_desktops.cli import build_parser, main
from now_playing_desktops.spotify_art import TrackPlayback
from now_playing_desktops.wallpaper_state import WallpaperSessionState
from tests.helpers import FakePlatform, mock_load_track_cover_rgba

PLAYING = TrackPlayback(
    track_id="t1",
    art_url="https://example.com/art.jpg",
    title="Song",
    artist="Artist",
    is_playing=True,
)


def test_cli_parser_accepts_run_restore_and_once():
    parser = build_parser()
    args = parser.parse_args(["run", "user", "--once", "--poll-interval", "2.2"])
    assert args.command == "run"
    assert args.username == "user"
    assert args.once is True
    assert args.poll_interval == 2.2
    restore_args = parser.parse_args(["restore"])
    assert restore_args.command == "restore"
    login_args = parser.parse_args(["login", "user", "--env-file", "/tmp/.env"])
    assert login_args.command == "login"
    assert login_args.username == "user"


def test_cli_verbose_after_subcommand_parses():
    args = build_parser().parse_args(["run", "user", "--once", "-v"])
    assert args.command == "run"
    assert args.verbose is True


def test_cli_verbose_before_subcommand_parses():
    with (
        patch("now_playing_desktops.cli.NowPlayingRunner"),
        patch("now_playing_desktops.cli.get_platform", return_value=MagicMock()),
        patch(
            "now_playing_desktops.cli.build_playback_provider",
            return_value=MagicMock(),
        ),
        patch(
            "now_playing_desktops.single_instance.ensure_single_run_instance",
            return_value=MagicMock(release=MagicMock()),
        ),
        patch(
            "now_playing_desktops.cli.configure_application_logging",
        ) as configure_logging,
    ):
        code = main(["-v", "run", "user", "--once"])
    assert code == 0
    configure_logging.assert_called_once()
    assert configure_logging.call_args.kwargs.get("verbose") is True


def test_cli_run_once_invokes_runner(tmp_path: Path):
    platform = MagicMock()
    platform.get_current_wallpaper.return_value = tmp_path / "wall.jpg"
    (tmp_path / "wall.jpg").write_bytes(b"w")
    runner = MagicMock()

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=platform),
        patch(
            "now_playing_desktops.cli.build_playback_provider",
            return_value=MagicMock(),
        ),
        patch(
            "now_playing_desktops.single_instance.ensure_single_run_instance",
            return_value=MagicMock(release=MagicMock()),
        ),
        patch("now_playing_desktops.cli.NowPlayingRunner", return_value=runner),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
        patch("now_playing_desktops.cli.state_file_path", return_value=tmp_path / "state.json"),
    ):
        code = main(["-v", "run", "user", "--once"])

    assert code == 0
    runner.startup.assert_called_once()
    runner.apply_playback_once.assert_called_once()


def test_cli_restore_nothing_to_restore_exits_zero(tmp_path: Path, capsys):
    platform = MagicMock()
    runner = MagicMock()
    runner.restore_original_wallpaper.return_value = False

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=platform),
        patch("now_playing_desktops.cli.NowPlayingRunner", return_value=runner),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
    ):
        code = main(["restore"])

    assert code == 0
    assert "nothing to restore" in capsys.readouterr().out


def test_cli_restore_command(tmp_path: Path):
    platform = MagicMock()
    runner = MagicMock()
    runner.restore_original_wallpaper.return_value = True

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=platform),
        patch("now_playing_desktops.cli.NowPlayingRunner", return_value=runner),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
    ):
        code = main(["restore", "--state-file", str(tmp_path / "state.json")])

    assert code == 0
    runner.restore_original_wallpaper.assert_called_once()


def test_cli_explicit_restore_twice_second_is_nothing_to_restore(tmp_path: Path, capsys):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    state_path = tmp_path / "state.json"
    WallpaperSessionState(
        original_wallpaper_path=str(original),
        original_wallpaper_snapshot={"backend": "fake", "path": str(original)},
        session_active=True,
    ).save(state_path)

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=platform),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
    ):
        assert main(["restore", "--state-file", str(state_path)]) == 0
        assert main(["restore", "--state-file", str(state_path)]) == 0

    out = capsys.readouterr().out
    assert out.count("nothing to restore") == 1
    assert WallpaperSessionState.load(state_path).session_active is False
    assert WallpaperSessionState.load(state_path).original_wallpaper_snapshot is None


def test_cli_run_once_then_double_restore(tmp_path: Path, capsys):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"orig")
    platform = FakePlatform(wallpaper=original)
    state_path = tmp_path / "state.json"

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=platform),
        patch(
            "now_playing_desktops.cli.build_playback_provider",
            return_value=MagicMock(),
        ),
        patch(
            "now_playing_desktops.single_instance.ensure_single_run_instance",
            return_value=MagicMock(release=MagicMock()),
        ),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
        patch("now_playing_desktops.cli.state_file_path", return_value=state_path),
        patch(
            "now_playing_desktops.runner.fetch_playback_for_runner",
            return_value=PLAYING,
        ),
        patch(
            "now_playing_desktops.runner.load_track_cover",
            side_effect=mock_load_track_cover_rgba,
        ),
    ):
        assert main(["run", "user", "--once"]) == 0
        assert main(["restore", "--state-file", str(state_path)]) == 0
        assert main(["restore", "--state-file", str(state_path)]) == 0

    assert capsys.readouterr().out.count("nothing to restore") == 1


def test_cli_run_reports_unsupported_platform():
    from now_playing_desktops.platforms import UnsupportedPlatformError

    with patch(
        "now_playing_desktops.cli.get_platform",
        side_effect=UnsupportedPlatformError("nope"),
    ):
        code = main(["run", "user", "--once"])
    assert code == 1
