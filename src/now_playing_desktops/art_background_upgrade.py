"""Background iTunes art upgrade (never blocks the first SMTC apply)."""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass

import requests
from PIL import Image

from now_playing_desktops.art_resolution import (
    ITUNES_UPGRADE_OVER_SMTC_MIN_PX,
    try_fetch_itunes_upgrade,
)
from now_playing_desktops.playback_types import TrackPlayback

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArtUpgradeTicket:
    generation: int
    track_id: str
    smtc_max_dim: int


class BackgroundArtUpgrader:
    """Fetches higher-res iTunes art off the apply hot path."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._thread: threading.Thread | None = None

    def cancel_pending(self) -> None:
        with self._lock:
            self._generation += 1

    def should_schedule(self, track: TrackPlayback) -> bool:
        if not track.art_bytes:
            return False

        try:
            with Image.open(io.BytesIO(track.art_bytes)) as image:
                smtc_max = max(image.size)
        except OSError:
            return False
        return smtc_max < ITUNES_UPGRADE_OVER_SMTC_MIN_PX

    def schedule(
        self,
        track: TrackPlayback,
        *,
        download_dir,
        session: requests.Session | None,
        on_upgraded,
        is_still_valid,
    ) -> None:
        if not self.should_schedule(track):
            return

        try:
            with Image.open(io.BytesIO(track.art_bytes)) as image:
                smtc_max = max(image.size)
        except OSError:
            return
        with self._lock:
            self._generation += 1
            generation = self._generation
        ticket = ArtUpgradeTicket(
            generation=generation,
            track_id=track.track_id,
            smtc_max_dim=smtc_max,
        )

        def _worker() -> None:
            try:
                upgraded = try_fetch_itunes_upgrade(
                    track,
                    smtc_max_dim=ticket.smtc_max_dim,
                    download_dir=download_dir,
                    session=session,
                )
            except Exception:
                logger.warning(
                    "Background iTunes art upgrade failed for %s — %s",
                    track.artist,
                    track.title,
                    exc_info=True,
                )
                return
            if upgraded is None:
                return
            with self._lock:
                if ticket.generation != self._generation:
                    logger.debug("Ignoring stale iTunes upgrade (generation)")
                    return
            if not is_still_valid(ticket):
                logger.debug("Ignoring stale iTunes upgrade (playback changed)")
                return
            new_track = TrackPlayback(
                track_id=track.track_id,
                art_url=track.art_url,
                title=track.title,
                artist=track.artist,
                album=track.album,
                is_playing=True,
                art_bytes=upgraded.image_bytes,
            )
            logger.info(
                "Upgraded art via iTunes (%dx%d -> %dx%d) for %s — %s",
                upgraded.smtc_width,
                upgraded.smtc_height,
                upgraded.width,
                upgraded.height,
                track.artist,
                track.title,
            )
            on_upgraded(new_track, ticket)

        thread = threading.Thread(
            target=_worker,
            name="itunes-art-upgrade",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        thread.start()
