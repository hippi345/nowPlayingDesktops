"""Spotify API helpers for current-track album art."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
import spotipy


def pick_album_image_url(images: list[dict[str, Any]]) -> str | None:
    """Return a reasonable album cover URL from Spotify's images list."""
    if not images:
        return None
    # Original scripts used index 1 (medium); fall back to largest (index 0).
    if len(images) > 1:
        return images[1].get("url")
    return images[0].get("url")


def current_album_art_url(sp: spotipy.Spotify) -> str | None:
    """Fetch the album art URL for the user's currently playing track, if any."""
    results = sp.current_user_playing_track()
    if not results or not results.get("item"):
        return None
    album = results["item"].get("album") or {}
    return pick_album_image_url(album.get("images") or [])


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


def poll_and_update_wallpaper(
    sp: spotipy.Spotify,
    *,
    poll_interval_seconds: float,
    prepare_artwork: Callable[[str], Path],
    set_wallpaper: Callable[[Path], None],
    after_update: Callable[[Path], None] | None = None,
    session: requests.Session | None = None,
) -> None:
    """Poll Spotify and refresh the desktop wallpaper on each interval when art is available."""
    while True:
        url = current_album_art_url(sp)
        if url:
            artwork_path = prepare_artwork(url)
            download_album_art(url, artwork_path, session=session)
            set_wallpaper(artwork_path)
            if after_update:
                after_update(artwork_path)
        time.sleep(poll_interval_seconds)
