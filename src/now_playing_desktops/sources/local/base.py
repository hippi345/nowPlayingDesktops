"""Local playback provider base."""

from __future__ import annotations

from now_playing_desktops.playback_source import PlaybackSourceName
from now_playing_desktops.playback_types import TrackPlayback


class LocalPlaybackProvider:
    source_name: PlaybackSourceName = "local"

    def fetch_current(self) -> TrackPlayback | None:
        return self._read_session()

    def peek_current(self) -> TrackPlayback | None:
        return self._read_session()

    def availability_reason(self) -> str | None:
        return None

    def _read_session(self) -> TrackPlayback | None:
        raise NotImplementedError
