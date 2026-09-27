"""Spotify OAuth configuration from environment variables."""

from __future__ import annotations

import errno
import os
import socket
import sys
from collections.abc import Callable
from urllib.parse import urlparse

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.util import get_host_port

SCOPE = "user-read-currently-playing"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8897/callback"


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


def spotify_redirect_uri() -> str:
    """OAuth redirect URI from the environment or the project default."""
    return os.environ.get("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()


def oauth_redirect_host_port(redirect_uri: str) -> tuple[str, int | None]:
    """Parse host and port from a Spotify redirect URI."""
    parsed = urlparse(redirect_uri)
    host, port = get_host_port(parsed.netloc)
    return host, port


def port_in_use_message(port: int) -> str:
    """User-facing message when the OAuth callback port cannot be bound."""
    return (
        f"port {port} is in use; set SPOTIPY_REDIRECT_URI to another 127.0.0.1 port "
        f"(e.g. http://127.0.0.1:8898/callback) and register it in the Spotify dashboard"
    )


def _is_bind_port_error(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    if exc.errno in (errno.EADDRINUSE, errno.EACCES):
        return True
    return getattr(exc, "winerror", None) == 10013


def _exit_port_in_use(port: int) -> None:
    print(port_in_use_message(port), file=sys.stderr)
    sys.exit(1)


def _needs_local_callback_server(redirect_uri: str, *, open_browser: bool) -> bool:
    parsed = urlparse(redirect_uri)
    host, port = oauth_redirect_host_port(redirect_uri)
    return (
        open_browser
        and parsed.scheme == "http"
        and host in ("127.0.0.1", "localhost")
        and port is not None
    )


def _has_cached_token(manager: SpotifyOAuth) -> bool:
    token_info = manager.cache_handler.get_cached_token()
    return manager.validate_token(token_info) is not None


def _precheck_oauth_redirect_port(manager: SpotifyOAuth) -> None:
    if _has_cached_token(manager):
        return
    if not _needs_local_callback_server(manager.redirect_uri, open_browser=manager.open_browser):
        return
    host, port = oauth_redirect_host_port(manager.redirect_uri)
    if port is None:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError as exc:
        if _is_bind_port_error(exc):
            _exit_port_in_use(port)
        raise
    finally:
        sock.close()


def _get_access_token(manager: SpotifyOAuth, *, as_dict: bool = False) -> str | None:
    _precheck_oauth_redirect_port(manager)
    try:
        return manager.get_access_token(as_dict=as_dict)
    except OSError as exc:
        if _is_bind_port_error(exc):
            _, port = oauth_redirect_host_port(manager.redirect_uri)
            _exit_port_in_use(port if port is not None else 0)
        raise


def spotify_oauth_manager(username: str) -> SpotifyOAuth | None:
    """Build a Spotipy OAuth manager that can refresh tokens."""
    try:
        client_id = _require_env("SPOTIPY_CLIENT_ID")
        client_secret = _require_env("SPOTIPY_CLIENT_SECRET")
    except SpotifyConfigError as exc:
        print(exc, file=sys.stderr)
        return None

    redirect_uri = spotify_redirect_uri()
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
    return _get_access_token(manager, as_dict=False)


def create_spotify_client(
    username: str,
) -> tuple[spotipy.Spotify, SpotifyOAuth, Callable[[], None]] | None:
    """Return Spotify client, OAuth manager, and a token-refresh callback."""
    manager = spotify_oauth_manager(username)
    if manager is None:
        return None
    token = _get_access_token(manager, as_dict=False)
    if not token:
        return None

    def refresh() -> None:
        _get_access_token(manager, as_dict=False)

    return spotipy.Spotify(auth=token), manager, refresh
