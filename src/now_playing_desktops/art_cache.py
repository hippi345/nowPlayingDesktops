"""Bounded on-disk cache for composed wallpapers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from now_playing_desktops.config import COMPOSED_CACHE_MAX_ENTRIES, COMPOSED_CACHE_VERSION


class ComposedArtCache:
    """Maps track + resolution to a composed PNG on disk."""

    def __init__(self, cache_dir: Path, *, max_entries: int = COMPOSED_CACHE_MAX_ENTRIES) -> None:
        self.cache_dir = cache_dir
        self.max_entries = max_entries
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(
        self,
        track_id: str,
        art_url: str,
        width: int,
        height: int,
        *,
        layout_signature: str | None = None,
    ) -> Path:
        layout_part = f"|{layout_signature}" if layout_signature else ""
        digest = hashlib.sha256(
            f"{COMPOSED_CACHE_VERSION}{layout_part}|{track_id}|{art_url}|{width}x{height}".encode(),
        ).hexdigest()[:32]
        return self.cache_dir / f"{digest}.png"

    def get(
        self,
        track_id: str,
        art_url: str,
        width: int,
        height: int,
        *,
        layout_signature: str | None = None,
    ) -> Path | None:
        path = self._key_path(
            track_id,
            art_url,
            width,
            height,
            layout_signature=layout_signature,
        )
        if path.is_file():
            path.touch()
            return path
        return None

    def put(
        self,
        track_id: str,
        art_url: str,
        width: int,
        height: int,
        source: Path,
        *,
        layout_signature: str | None = None,
    ) -> Path:
        dest = self._key_path(
            track_id,
            art_url,
            width,
            height,
            layout_signature=layout_signature,
        )
        dest.write_bytes(source.read_bytes())
        self._evict_if_needed()
        return dest

    def _evict_if_needed(self) -> None:
        entries = sorted(
            self.cache_dir.glob("*.png"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(entries) > self.max_entries:
            oldest = entries.pop(0)
            oldest.unlink(missing_ok=True)
