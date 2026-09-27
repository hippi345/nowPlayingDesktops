from __future__ import annotations

from now_playing_desktops.playback_types import TrackPlayback
from now_playing_desktops.sources.local.base import LocalPlaybackProvider


class UnsupportedLocalProvider(LocalPlaybackProvider):
    def __init__(self, platform: str) -> None:
        self._platform = platform

    def availability_reason(self) -> str | None:
        return f"local playback is not supported on {self._platform}"

    def _read_session(self) -> TrackPlayback | None:
        return None
