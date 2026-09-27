"""Test entry point for autostart Exec verification (mocks Spotify, runs once)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from now_playing_desktops import cli


def _mock_spotify_client():
    return MagicMock(), MagicMock(), lambda: None


def main() -> int:
    with (
        patch(
            "now_playing_desktops.cli.create_spotify_client",
            return_value=_mock_spotify_client(),
        ),
        patch("now_playing_desktops.runner.fetch_playback_with_backoff", return_value=None),
        patch("now_playing_desktops.cli.get_platform") as platform_factory,
    ):
        from now_playing_desktops.platforms.linux import LinuxWallpaperPlatform
        from now_playing_desktops.platforms.linux_backends import FehWallpaperBackend
        from now_playing_desktops.platforms.linux_de import LinuxDesktopEnvironment

        platform_factory.return_value = LinuxWallpaperPlatform(
            de=LinuxDesktopEnvironment.OTHER,
            backend=FehWallpaperBackend(),
        )
        argv = list(sys.argv[1:])
        if "--once" not in argv:
            argv.append("--once")
        return cli.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
