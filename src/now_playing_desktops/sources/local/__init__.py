"""Local OS media session playback."""

from __future__ import annotations

import sys

from now_playing_desktops.sources.local.base import LocalPlaybackProvider


def build_local_provider() -> LocalPlaybackProvider:
    if sys.platform == "win32":
        from now_playing_desktops.sources.local.windows_smtc import WindowsSmtcProvider

        return WindowsSmtcProvider()
    if sys.platform == "linux":
        from now_playing_desktops.sources.local.linux_mpris import LinuxMprisProvider

        return LinuxMprisProvider()
    if sys.platform == "darwin":
        from now_playing_desktops.sources.local.macos_spotify import MacOsSpotifyProvider

        return MacOsSpotifyProvider()
    from now_playing_desktops.sources.local.unsupported import UnsupportedLocalProvider

    return UnsupportedLocalProvider(sys.platform)
