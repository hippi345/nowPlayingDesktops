"""Spotify Web API playback provider."""

from __future__ import annotations

from collections.abc import Callable

import spotipy

from now_playing_desktops.auth import create_spotify_client
from now_playing_desktops.playback_source import PlaybackSourceName
from now_playing_desktops.playback_types import TrackPlayback
from now_playing_desktops.spotify_art import fetch_playback_with_backoff, parse_playing_track


class SpotifyPlaybackProvider:
    source_name: PlaybackSourceName = "spotify"

    def __init__(
        self,
        sp: spotipy.Spotify,
        *,
        on_token_refresh: Callable[[], None] | None = None,
    ) -> None:
        self._sp = sp
        self._on_token_refresh = on_token_refresh

    @classmethod
    def from_username(cls, username: str) -> SpotifyPlaybackProvider | None:
        bundle = create_spotify_client(username)
        if bundle is None:
            return None
        sp, _manager, refresh = bundle
        return cls(sp, on_token_refresh=refresh)

    def availability_reason(self) -> str | None:
        return None

    def fetch_current(self) -> TrackPlayback | None:
        return fetch_playback_with_backoff(
            self._sp,
            on_token_refresh=self._on_token_refresh,
        )

    def peek_current(self) -> TrackPlayback | None:
        try:
            payload = self._sp.current_user_playing_track()
        except Exception:
            return None
        return parse_playing_track(payload)
