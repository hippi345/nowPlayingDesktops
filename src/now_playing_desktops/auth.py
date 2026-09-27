"""Spotify OAuth configuration from environment variables."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPE = "user-read-currently-playing"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"


class SpotifyConfigError(RuntimeError):
    """Raised when required Spotify OAuth settings are missing."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SpotifyConfigError(
            f"Missing required environment variable {name}. "
            "Create a Spotify app at https://developer.spotify.com/dashboard "
            f"and set {name}, SPOTIPY_CLIENT_SECRET, and optionally SPOTIPY_REDIRECT_URI."
        )
    return value


def spotify_oauth_manager(username: str) -> SpotifyOAuth | None:
    """Build a Spotipy OAuth manager that can refresh tokens."""
    try:
        client_id = _require_env("SPOTIPY_CLIENT_ID")
        client_secret = _require_env("SPOTIPY_CLIENT_SECRET")
    except SpotifyConfigError as exc:
        print(exc, file=sys.stderr)
        return None

    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        username=username,
        open_browser=True,
    )


def prompt_for_token(username: str) -> str | None:
    """Prompt the user to authorize and return an access token."""
    manager = spotify_oauth_manager(username)
    if manager is None:
        return None
    return manager.get_access_token(as_dict=False)


def create_spotify_client(
    username: str,
) -> tuple[spotipy.Spotify, SpotifyOAuth, Callable[[], None]] | None:
    """Return Spotify client, OAuth manager, and a token-refresh callback."""
    manager = spotify_oauth_manager(username)
    if manager is None:
        return None
    token = manager.get_access_token(as_dict=False)
    if not token:
        return None

    def refresh() -> None:
        manager.get_access_token(as_dict=False)

    return spotipy.Spotify(auth=token), manager, refresh
