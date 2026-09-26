from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from now_playing_desktops.cli import build_parser, main


def test_cli_parser_accepts_run_restore_and_once():
    parser = build_parser()
    args = parser.parse_args(["run", "user", "--once", "--poll-interval", "2.2"])
    assert args.command == "run"
    assert args.username == "user"
    assert args.once is True
    assert args.poll_interval == 2.2
    restore_args = parser.parse_args(["restore"])
    assert restore_args.command == "restore"


def test_cli_run_once_invokes_runner(tmp_path: Path):
    platform = MagicMock()
    platform.get_current_wallpaper.return_value = tmp_path / "wall.jpg"
    (tmp_path / "wall.jpg").write_bytes(b"w")
    runner = MagicMock()

    with (
        patch("now_playing_desktops.cli.get_platform", return_value=platform),
        patch(
            "now_playing_desktops.cli.create_spotify_client",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ),
        patch("now_playing_desktops.cli.NowPlayingRunner", return_value=runner),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
        patch("now_playing_desktops.cli.state_file_path", return_value=tmp_path / "state.json"),
    ):
        code = main(["-v", "run", "user", "--once"])

    assert code == 0
    runner.startup.assert_called_once()
    runner.apply_playback_once.assert_called_once()


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


def test_cli_run_reports_unsupported_platform():
    from now_playing_desktops.platforms import UnsupportedPlatformError

    with patch(
        "now_playing_desktops.cli.get_platform",
        side_effect=UnsupportedPlatformError("nope"),
    ):
        code = main(["run", "user", "--once"])
    assert code == 1
