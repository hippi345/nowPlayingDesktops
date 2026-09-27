"""Linux MPRIS D-Bus playback for Spotify."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from now_playing_desktops.playback_types import TrackPlayback, stable_track_id
from now_playing_desktops.sources.local.base import LocalPlaybackProvider

logger = logging.getLogger(__name__)

SPOTIFY_MPRIS = "org.mpris.MediaPlayer2.spotify"
MPRIS_PATH = "/org/mpris/MediaPlayer2"


def _dbus_next_available() -> bool:
    try:
        import dbus_next  # noqa: F401

        return True
    except ImportError:
        return False


def _variant_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


async def _read_mpris_async() -> TrackPlayback | None:
    from dbus_next.aio import MessageBus

    bus = await MessageBus().connect()
    introspection = await bus.introspect(SPOTIFY_MPRIS, MPRIS_PATH)
    obj = bus.get_proxy_object(SPOTIFY_MPRIS, MPRIS_PATH, introspection)
    player = obj.get_interface("org.mpris.MediaPlayer2.Player")

    status = await player.get_playback_status()
    metadata = await player.get_metadata()
    is_playing = str(status).lower() == "playing"

    md = {str(key): _variant_value(val) for key, val in metadata.items()}
    title = str(md.get("xesam:title") or "Unknown Title")
    artist_field = md.get("xesam:artist")
    if isinstance(artist_field, list):
        artist = ", ".join(str(a) for a in artist_field) or "Unknown Artist"
    else:
        artist = str(artist_field or "Unknown Artist")
    album = str(md.get("xesam:album") or "")
    art_url = str(md.get("mpris:artUrl") or "")

    track_id = stable_track_id(title=title, artist=artist, album=album)
    return TrackPlayback(
        track_id=track_id,
        art_url=art_url,
        title=title,
        artist=artist,
        album=album,
        is_playing=is_playing,
    )


class LinuxMprisProvider(LocalPlaybackProvider):
    def availability_reason(self) -> str | None:
        if not _dbus_next_available():
            return "install the linux optional dependency (dbus-next)"
        return None

    def _read_session(self) -> TrackPlayback | None:
        if not _dbus_next_available():
            return None
        try:
            return asyncio.run(_read_mpris_async())
        except Exception:
            logger.debug("MPRIS session read failed", exc_info=True)
            return None
