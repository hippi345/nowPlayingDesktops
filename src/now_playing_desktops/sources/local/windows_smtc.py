"""Windows System Media Transport Controls (Spotify session)."""

from __future__ import annotations

import logging
import sys

from now_playing_desktops.playback_types import TrackPlayback
from now_playing_desktops.sources.local.base import LocalPlaybackProvider

logger = logging.getLogger(__name__)


def _winrt_available() -> bool:
    try:
        import winrt.windows.foundation  # noqa: F401
        import winrt.windows.foundation.collections  # noqa: F401
        import winrt.windows.media.control  # noqa: F401
        import winrt.windows.storage.streams  # noqa: F401

        return True
    except ImportError:
        return False


class WindowsSmtcProvider(LocalPlaybackProvider):
    def availability_reason(self) -> str | None:
        if not _winrt_available():
            return (
                "install the windows optional dependency "
                "(pip install -e '.[windows]' for winrt-Windows.* packages)"
            )
        return None

    def _read_session(self) -> TrackPlayback | None:
        if not _winrt_available():
            return None
        if sys.platform != "win32":
            return None
        from now_playing_desktops.sources.local.windows_smtc_worker import get_smtc_worker

        return get_smtc_worker().read_spotify_session()
