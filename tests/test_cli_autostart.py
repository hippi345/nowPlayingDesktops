from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from now_playing_desktops.cli import build_parser, main


def test_cli_parser_accepts_autostart_subcommand():
    parser = build_parser()
    args = parser.parse_args(["autostart", "enable"])
    assert args.command == "autostart"
    assert args.action == "enable"


def test_cli_autostart_status():
    with patch(
        "now_playing_desktops.platforms.autostart.autostart_enabled",
        return_value=True,
    ):
        code = main(["autostart", "status"])
    assert code == 0


def test_cli_autostart_enable_passes_env_file(tmp_path: Path):
    env_file = tmp_path / "oauth.env"
    env_file.write_text(
        "SPOTIPY_CLIENT_ID=id\nSPOTIPY_CLIENT_SECRET=secret\n",
        encoding="utf-8",
    )
    with patch("now_playing_desktops.platforms.autostart.enable_autostart") as enable:
        code = main(["autostart", "enable", "myuser", "--env-file", str(env_file)])
    assert code == 0
    enable.assert_called_once_with(env_file=env_file, username="myuser")


def test_cli_autostart_enable_missing_env_reports_message(tmp_path: Path, capsys):
    with patch(
        "now_playing_desktops.platforms.autostart.enable_autostart",
        side_effect=__import__(
            "now_playing_desktops.platforms.autostart",
            fromlist=["AutostartSetupError"],
        ).AutostartSetupError("missing env"),
    ):
        code = main(["autostart", "enable"])
    assert code == 1
    assert "missing env" in capsys.readouterr().err


def test_cli_run_once_loads_env_file_without_shell_env(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "oauth.env"
    env_file.write_text(
        "SPOTIPY_CLIENT_ID=file-id\n"
        "SPOTIPY_CLIENT_SECRET=file-secret\n"
        "SPOTIPY_CLIENT_USERNAME=file-user\n",
        encoding="utf-8",
    )
    for name in (
        "SPOTIPY_CLIENT_ID",
        "SPOTIPY_CLIENT_SECRET",
        "SPOTIPY_CLIENT_USERNAME",
    ):
        monkeypatch.delenv(name, raising=False)

    runner = MagicMock()
    with (
        patch("now_playing_desktops.cli.get_platform", return_value=MagicMock()),
        patch("now_playing_desktops.cli.create_spotify_client") as create_client,
        patch("now_playing_desktops.cli.NowPlayingRunner", return_value=runner),
        patch("now_playing_desktops.cli.default_cache_dir", return_value=tmp_path / "cache"),
        patch("now_playing_desktops.cli.state_file_path", return_value=tmp_path / "state.json"),
    ):
        create_client.return_value = (MagicMock(), MagicMock(), MagicMock())
        code = main(
            [
                "run",
                "--env-file",
                str(env_file),
                "--once",
            ]
        )

    assert code == 0
    create_client.assert_called_once_with("file-user")
    runner.startup.assert_called_once()
