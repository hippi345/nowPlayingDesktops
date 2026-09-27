"""Shared playback snapshot for wallpaper updates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class TrackPlayback:
    track_id: str
    art_url: str
    title: str
    artist: str
    is_playing: bool
    album: str = ""
    art_bytes: bytes | None = None

    @property
    def art_cache_key(self) -> str:
        if self.art_url:
            return self.art_url
        if self.art_bytes:
            digest = hashlib.sha256(self.art_bytes).hexdigest()
            return f"bytes:{digest[:32]}"
        return self.track_id


def stable_track_id(*, title: str, artist: str, album: str) -> str:
    payload = f"{title}\0{artist}\0{album}".encode()
    return hashlib.sha256(payload).hexdigest()[:20]
