"""Read SMTC thumbnail streams via WinRT."""

from __future__ import annotations

import asyncio
import logging

from now_playing_desktops.sources.local.windows_smtc_winrt import WinrtTimeoutError, winrt_wait

logger = logging.getLogger(__name__)

_THUMBNAIL_RETRY_ATTEMPTS = 3
_THUMBNAIL_RETRY_DELAY_SECONDS = 0.12


async def read_random_access_stream_bytes(stream) -> bytes | None:
    from winrt.windows.storage.streams import Buffer, InputStreamOptions

    size = int(stream.size)
    if size <= 0:
        return None
    buffer = Buffer(size)
    await winrt_wait(
        stream.read_async(buffer, size, InputStreamOptions.READ_AHEAD),
        operation="IRandomAccessStream.read_async",
    )
    return bytes(buffer)


async def read_thumbnail_reference_bytes_once(thumbnail_ref) -> bytes | None:
    if thumbnail_ref is None:
        return None
    try:
        stream = await winrt_wait(
            thumbnail_ref.open_read_async(),
            operation="IRandomAccessStreamReference.open_read_async",
        )
        return await read_random_access_stream_bytes(stream)
    except WinrtTimeoutError:
        return None
    except Exception:
        logger.warning("SMTC thumbnail read failed", exc_info=True)
        return None


async def read_thumbnail_reference_bytes(
    thumbnail_ref,
    *,
    attempts: int = _THUMBNAIL_RETRY_ATTEMPTS,
    delay_seconds: float = _THUMBNAIL_RETRY_DELAY_SECONDS,
) -> bytes | None:
    if thumbnail_ref is None:
        return None
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            art_bytes = await read_thumbnail_reference_bytes_once(thumbnail_ref)
            if art_bytes:
                return art_bytes
            if attempt < attempts - 1:
                await asyncio.sleep(delay_seconds)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "SMTC thumbnail read failed (attempt %s/%s)",
                attempt + 1,
                attempts,
                exc_info=True,
            )
            if attempt < attempts - 1:
                await asyncio.sleep(delay_seconds)
    if last_error is not None:
        logger.warning("SMTC thumbnail unavailable after retries: %s", last_error)
    else:
        logger.warning("SMTC thumbnail stream was empty after %s attempts", attempts)
    return None
