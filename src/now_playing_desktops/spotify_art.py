"""Spotify API helpers for current-track album art and playback state."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
import spotipy
from spotipy.exceptions import SpotifyException

from now_playing_desktops.playback_types import TrackPlayback

logger = logging.getLogger(__name__)


def pick_album_image_url(images: list[dict[str, Any]]) -> str | None:
    """Return the largest album cover URL from Spotify's images list."""
    if not images:
        return None
    return images[0].get("url")


def parse_playing_track(payload: dict[str, Any] | None) -> TrackPlayback | None:
    if not payload or not payload.get("item"):
        return None
    item = payload["item"]
    track_id = item.get("id")
    album = item.get("album") or {}
    art_url = pick_album_image_url(album.get("images") or [])
    if not track_id or not art_url:
        return None
    title = item.get("name") or "Unknown Title"
    artists = item.get("artists") or []
    artist = ", ".join(a.get("name", "") for a in artists if a.get("name")) or "Unknown Artist"
    album = album.get("name") or ""
    is_playing = bool(payload.get("is_playing"))
    return TrackPlayback(
        track_id=track_id,
        art_url=art_url,
        title=title,
        artist=artist,
        is_playing=is_playing,
        album=album,
    )


def fetch_current_playback(sp: spotipy.Spotify) -> TrackPlayback | None:
    """Fetch structured playback info for the user's current track, if any."""
    results = sp.current_user_playing_track()
    return parse_playing_track(results)


def current_album_art_url(sp: spotipy.Spotify) -> str | None:
    """Fetch the album art URL for the user's currently playing track, if any."""
    track = fetch_current_playback(sp)
    return track.art_url if track else None


def download_album_art(
    url: str,
    destination: Path,
    session: requests.Session | None = None,
) -> None:
    """Download album art from ``url`` to ``destination``."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    response = http.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                handle.write(chunk)


def _retry_after_seconds(exc: SpotifyException) -> float | None:
    headers = exc.headers or {}
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after is None:
        return None
    try:
        return float(retry_after)
    except (TypeError, ValueError):
        return None


def fetch_playback_with_backoff(
    sp: spotipy.Spotify,
    *,
    attempt: int = 0,
    max_attempts: int = 5,
    on_token_refresh: Callable[[], None] | None = None,
) -> TrackPlayback | None:
    """Call Spotify with retries for rate limits, network errors, and token refresh."""
    try:
        return fetch_current_playback(sp)
    except SpotifyException as exc:
        if exc.http_status == 429:
            wait = _retry_after_seconds(exc) or min(60.0, 2.0**attempt)
            logger.warning("Spotify rate limited (429); sleeping %.1fs", wait)
            time.sleep(wait)
            if attempt + 1 < max_attempts:
                return fetch_playback_with_backoff(
                    sp,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    on_token_refresh=on_token_refresh,
                )
            return None
        if exc.http_status in {401, 403} and on_token_refresh and attempt + 1 < max_attempts:
            logger.info("Refreshing Spotify token after HTTP %s", exc.http_status)
            on_token_refresh()
            wait = min(30.0, 2.0**attempt)
            time.sleep(wait)
            return fetch_playback_with_backoff(
                sp,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                on_token_refresh=on_token_refresh,
            )
        logger.warning("Spotify API error: %s", exc)
        return None
    except requests.RequestException as exc:
        wait = min(30.0, 2.0**attempt)
        logger.warning("Network error talking to Spotify: %s; sleeping %.1fs", exc, wait)
        time.sleep(wait)
        if attempt + 1 < max_attempts:
            return fetch_playback_with_backoff(
                sp,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                on_token_refresh=on_token_refresh,
            )
        return None


def poll_and_update_wallpaper(
    sp: spotipy.Spotify,
    *,
    poll_interval_seconds: float,
    prepare_artwork: Callable[[str], Path],
    set_wallpaper: Callable[[Path], None],
    after_update: Callable[[Path], None] | None = None,
    session: requests.Session | None = None,
) -> None:
    """Legacy poll loop used by older tests; prefer :mod:`now_playing_desktops.runner`."""
    while True:
        track = fetch_current_playback(sp)
        url = track.art_url if track and track.is_playing else None
        if url:
            artwork_path = prepare_artwork(url)
            download_album_art(url, artwork_path, session=session)
            set_wallpaper(artwork_path)
            if after_update:
                after_update(artwork_path)
        time.sleep(poll_interval_seconds)
