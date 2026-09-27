from unittest.mock import patch

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
