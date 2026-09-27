"""Spotify OAuth configuration from environment variables."""

from __future__ import annotations

import errno
import logging
import os
import socket
import sys
from collections.abc import Callable
from typing import Literal
from urllib.parse import urlparse

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth, SpotifyPKCE
from spotipy.util import get_host_port

from now_playing_desktops.config import spotify_token_cache_path, user_config_dir

SCOPE = "user-read-currently-playing"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8897/callback"

SpotifyAuthMode = Literal["client_secret", "pkce"]
type SpotifyAuthManager = SpotifyOAuth | SpotifyPKCE

logger = logging.getLogger(__name__)


class SpotifyConfigError(RuntimeError):
    """Raised when required Spotify OAuth settings are missing."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SpotifyConfigError(
            f"Missing required environment variable {name}. "
            "Create a Spotify app at https://developer.spotify.com/dashboard "
            f"and set {name} (and SPOTIPY_CLIENT_SECRET only if using the legacy flow)."
        )
    return value


def spotify_auth_mode() -> SpotifyAuthMode | None:
    """Return the selected auth mode, or ``None`` when ``SPOTIPY_CLIENT_ID`` is missing."""
    if not os.environ.get("SPOTIPY_CLIENT_ID", "").strip():
        return None
    if os.environ.get("SPOTIPY_CLIENT_SECRET", "").strip():
        return "client_secret"
    return "pkce"


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


def non_interactive_auth_message(username: str) -> str:
    """Tell the user how to sign in when a background run has no usable token cache."""
    return (
        f"No valid cached Spotify token for {username!r}. "
        "Run `now-playing login` with the same --env-file and Spotify username to sign in once."
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


def cache_handler_for_user(username: str) -> CacheFileHandler:
    """Per-user token cache under the application config directory."""
    user_config_dir().mkdir(parents=True, exist_ok=True)
    return CacheFileHandler(cache_path=str(spotify_token_cache_path(username)))


def cached_token_available(manager: SpotifyAuthManager) -> bool:
    """Return whether a usable token exists in the cache (refreshing if expired)."""
    token_info = manager.cache_handler.get_cached_token()
    return manager.validate_token(token_info) is not None


def _precheck_oauth_redirect_port(manager: SpotifyAuthManager) -> None:
    if cached_token_available(manager):
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


def _access_token_from_cache(manager: SpotifyAuthManager) -> str | None:
    token_info = manager.cache_handler.get_cached_token()
    validated = manager.validate_token(token_info)
    if validated is None:
        return None
    return validated["access_token"]


def _get_access_token(
    manager: SpotifyAuthManager,
    *,
    username: str,
    as_dict: bool = False,
    interactive: bool = True,
) -> str | None:
    if not interactive:
        token = _access_token_from_cache(manager)
        if token is not None:
            return token
        logger.error(non_interactive_auth_message(username))
        return None

    _precheck_oauth_redirect_port(manager)
    try:
        if isinstance(manager, SpotifyOAuth):
            return manager.get_access_token(as_dict=as_dict)
        return manager.get_access_token()
    except OSError as exc:
        if _is_bind_port_error(exc):
            _, port = oauth_redirect_host_port(manager.redirect_uri)
            _exit_port_in_use(port if port is not None else 0)
        raise


def spotify_oauth_manager(
    username: str,
    *,
    interactive: bool = True,
) -> SpotifyAuthManager | None:
    """Build a Spotipy OAuth manager that can refresh tokens."""
    try:
        client_id = _require_env("SPOTIPY_CLIENT_ID")
    except SpotifyConfigError as exc:
        print(exc, file=sys.stderr)
        return None

    mode = spotify_auth_mode()
    if mode is None:
        print(
            "Missing required environment variable SPOTIPY_CLIENT_ID.",
            file=sys.stderr,
        )
        return None

    logger.info("Spotify auth mode: %s", mode)

    redirect_uri = spotify_redirect_uri()
    cache_handler = cache_handler_for_user(username)

    if mode == "client_secret":
        try:
            client_secret = _require_env("SPOTIPY_CLIENT_SECRET")
        except SpotifyConfigError as exc:
            print(exc, file=sys.stderr)
            return None
        return SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPE,
            cache_handler=cache_handler,
            open_browser=True,
        )

    return SpotifyPKCE(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        cache_handler=cache_handler,
        open_browser=interactive,
    )


def prompt_for_token(username: str) -> str | None:
    """Prompt the user to authorize and return an access token."""
    return interactive_sign_in(username)


def interactive_sign_in(username: str) -> str | None:
    """Open the browser (or paste URL) flow for the first interactive sign-in."""
    manager = spotify_oauth_manager(username, interactive=True)
    if manager is None:
        return None
    return _get_access_token(manager, username=username, as_dict=False, interactive=True)


def create_spotify_client(
    username: str,
) -> tuple[spotipy.Spotify, SpotifyAuthManager, Callable[[], None]] | None:
    """Return Spotify client, OAuth manager, and a token-refresh callback."""
    mode = spotify_auth_mode()
    interactive = mode == "client_secret"
    manager = spotify_oauth_manager(username, interactive=interactive)
    if manager is None:
        return None
    token = _get_access_token(
        manager,
        username=username,
        as_dict=False,
        interactive=interactive,
    )
    if not token:
        return None

    def refresh() -> None:
        _get_access_token(
            manager,
            username=username,
            as_dict=False,
            interactive=interactive,
        )

    return spotipy.Spotify(auth=token), manager, refresh


def spotify_auth_diag_lines(username: str | None) -> list[str]:
    """Human-readable Spotify auth status for ``diag`` (no secrets or tokens)."""
    mode = spotify_auth_mode()
    if mode is None:
        return [
            "Spotify auth mode: (not configured — set SPOTIPY_CLIENT_ID)",
            "Spotify cached token: no",
        ]
    lines = [f"Spotify auth mode: {mode}"]
    if not username:
        lines.append("Spotify cached token: unknown (set SPOTIPY_CLIENT_USERNAME or pass username)")
        return lines
    manager = spotify_oauth_manager(username, interactive=False)
    if manager is None:
        lines.append("Spotify cached token: no")
        return lines
    lines.append(
        "Spotify cached token: yes"
        if cached_token_available(manager)
        else "Spotify cached token: no"
    )
    return lines
