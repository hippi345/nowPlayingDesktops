"""Spotify OAuth configuration from environment variables."""

from __future__ import annotations

import os
import sys

import spotipy.util as util

SCOPE = "user-read-currently-playing"
DEFAULT_REDIRECT_URI = "http://localhost/"


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


def prompt_for_token(username: str) -> str | None:
    """Prompt the user to authorize and return an access token."""
    try:
        client_id = _require_env("SPOTIPY_CLIENT_ID")
        client_secret = _require_env("SPOTIPY_CLIENT_SECRET")
    except SpotifyConfigError as exc:
        print(exc, file=sys.stderr)
        return None

    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()
    return util.prompt_for_user_token(
        username,
        SCOPE,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )
