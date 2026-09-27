"""Async SMTC session reads (run on the MTA worker event loop only)."""

from __future__ import annotations

import asyncio
import logging

from now_playing_desktops.playback_types import TrackPlayback, stable_track_id
from now_playing_desktops.sources.local.windows_smtc_thumbnail import (
    read_thumbnail_reference_bytes_once,
)
from now_playing_desktops.sources.local.windows_smtc_winrt import WinrtTimeoutError, winrt_wait

logger = logging.getLogger(__name__)

_THUMBNAIL_REFETCH_ATTEMPTS = 5
_THUMBNAIL_REFETCH_DELAY_SECONDS = 0.3


def _session_is_playing(playback) -> bool:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus

    status = playback.playback_status
    return status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING


async def _read_thumbnail_with_refetch(session, props, *, is_playing: bool) -> bytes | None:
    if not is_playing:
        thumb = props.thumbnail
        if thumb is None:
            return None
        return await read_thumbnail_reference_bytes_once(thumb)

    current_props = props
    for attempt in range(_THUMBNAIL_REFETCH_ATTEMPTS):
        thumb = current_props.thumbnail
        if thumb is not None:
            art_bytes = await read_thumbnail_reference_bytes_once(thumb)
            if art_bytes:
                return art_bytes
        if attempt + 1 >= _THUMBNAIL_REFETCH_ATTEMPTS:
            break
        await asyncio.sleep(_THUMBNAIL_REFETCH_DELAY_SECONDS)
        refreshed = await winrt_wait(
            session.try_get_media_properties_async(),
            operation="GlobalSystemMediaTransportControlsSession.try_get_media_properties_async",
        )
        if refreshed is not None:
            current_props = refreshed
    return None


async def read_spotify_session_async() -> TrackPlayback | None:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

    manager = await winrt_wait(
        GlobalSystemMediaTransportControlsSessionManager.request_async(),
        operation="GlobalSystemMediaTransportControlsSessionManager.request_async",
    )
    sessions = manager.get_sessions()
    for session in sessions:
        app_id = (session.source_app_user_model_id or "").lower()
        if "spotify" not in app_id:
            continue
        props = await winrt_wait(
            session.try_get_media_properties_async(),
            operation="GlobalSystemMediaTransportControlsSession.try_get_media_properties_async",
        )
        if props is None:
            continue
        title = props.title or "Unknown Title"
        artist = props.artist or "Unknown Artist"
        album = props.album_title or ""
        playback = session.get_playback_info()
        is_playing = _session_is_playing(playback)

        art_bytes = await _read_thumbnail_with_refetch(session, props, is_playing=is_playing)
        if art_bytes:
            logger.debug(
                "Read SMTC thumbnail for %s — %s (%s bytes)",
                artist,
                title,
                len(art_bytes),
            )

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


def is_winrt_timeout(exc: BaseException) -> bool:
    if isinstance(exc, WinrtTimeoutError):
        return True
    if isinstance(exc, TimeoutError):
        return True
    cause = exc.__cause__
    return cause is not None and is_winrt_timeout(cause)
