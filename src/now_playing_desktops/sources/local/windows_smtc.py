"""Windows System Media Transport Controls (Spotify session)."""

from __future__ import annotations

import asyncio
import logging

from now_playing_desktops.playback_types import TrackPlayback, stable_track_id
from now_playing_desktops.sources.local.base import LocalPlaybackProvider

logger = logging.getLogger(__name__)


def _winrt_available() -> bool:
    try:
        import winrt.windows.media.control  # noqa: F401

        return True
    except ImportError:
        return False


async def _read_spotify_session_async() -> TrackPlayback | None:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    from winrt.windows.storage.streams import DataReader

    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    sessions = manager.get_sessions()
    for session in sessions:
        app_id = (session.source_app_user_model_id or "").lower()
        if "spotify" not in app_id:
            continue
        props = await session.try_get_media_properties_async()
        if props is None:
            continue
        title = props.title or "Unknown Title"
        artist = props.artist or "Unknown Artist"
        album = props.album_title or ""
        playback = session.get_playback_info()
        status = playback.playback_status
        # GlobalSystemMediaTransportControlsPlaybackStatus.playing == 4
        is_playing = int(status) == 4

        art_bytes: bytes | None = None
        thumb = props.thumbnail
        if thumb is not None:
            try:
                stream = await thumb.open_read_async()
                reader = DataReader.from_buffer(stream)
                count = stream.size
                art_bytes = bytes(await reader.read_bytes_async(count))
            except Exception:
                logger.debug("Could not read SMTC thumbnail bytes", exc_info=True)

        track_id = stable_track_id(title=title, artist=artist, album=album)
        return TrackPlayback(
            track_id=track_id,
            art_url="",
            title=title,
            artist=artist,
            album=album,
            is_playing=is_playing,
            art_bytes=art_bytes,
        )
    return None


class WindowsSmtcProvider(LocalPlaybackProvider):
    def availability_reason(self) -> str | None:
        if not _winrt_available():
            return "install the windows optional dependency (winrt-Windows.Media.Control)"
        return None

    def _read_session(self) -> TrackPlayback | None:
        if not _winrt_available():
            return None
        try:
            return asyncio.run(_read_spotify_session_async())
        except Exception:
            logger.debug("SMTC session read failed", exc_info=True)
            return None
