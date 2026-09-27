from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests
from spotipy.exceptions import SpotifyException

from now_playing_desktops.spotify_art import fetch_playback_with_backoff


def test_fetch_playback_honors_429_retry_after():
    sp = MagicMock()
    exc = SpotifyException(429, -1, "rate", headers={"Retry-After": "0.01"})
    sp.current_user_playing_track.side_effect = [exc, {"item": None}]

    with patch("now_playing_desktops.spotify_art.time.sleep") as sleep_mock:
        result = fetch_playback_with_backoff(sp, max_attempts=2)

    assert result is None
    sleep_mock.assert_called()


def test_fetch_playback_network_error_exponential_backoff():
    sp = MagicMock()
    sp.current_user_playing_track.side_effect = requests.ConnectionError("down")

    with patch("now_playing_desktops.spotify_art.time.sleep") as sleep_mock:
        result = fetch_playback_with_backoff(sp, max_attempts=2)

    assert result is None
    assert sleep_mock.call_count >= 1


def test_fetch_playback_refreshes_token_on_401():
    sp = MagicMock()
    exc = SpotifyException(401, -1, "expired")
    sp.current_user_playing_track.side_effect = [exc, {"item": None}]
    refresh = MagicMock()

    with patch("now_playing_desktops.spotify_art.time.sleep"):
        fetch_playback_with_backoff(sp, max_attempts=2, on_token_refresh=refresh)

    refresh.assert_called_once()
