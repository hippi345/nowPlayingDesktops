"""Verify Windows optional dependencies include every winrt module we import."""

from __future__ import annotations

import sys

import pytest

WINRT_IMPORTS = [
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.media.control",
    "winrt.windows.storage.streams",
]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only winrt imports")
def test_windows_extra_imports_all_winrt_modules_used_by_local_source():
    for module_name in WINRT_IMPORTS:
        __import__(module_name)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only winrt stream test")
def test_read_bytes_from_in_memory_random_access_stream():
    import asyncio

    from winrt.windows.storage.streams import (
        InMemoryRandomAccessStream,
        RandomAccessStreamReference,
    )

    from now_playing_desktops.sources.local.windows_smtc_thumbnail import (
        read_random_access_stream_bytes,
        read_thumbnail_reference_bytes,
    )

    payload = b"\x89PNG\r\n\x1a\n" + b"0" * 32

    async def _run():
        stream = InMemoryRandomAccessStream()
        await stream.write_async(bytearray(payload))
        stream.seek(0)
        assert await read_random_access_stream_bytes(stream) == payload

        stream.seek(0)
        reference = RandomAccessStreamReference.create_from_stream(stream)
        thumb = await read_thumbnail_reference_bytes(reference, attempts=1, delay_seconds=0)
        assert thumb == payload

    asyncio.run(_run())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only COM + SMTC apartment test")
def test_smtc_manager_request_after_sta_com_init():
    from now_playing_desktops.sources.local.windows_smtc_worker import (
        read_spotify_session_after_sta_com_probe,
        reset_smtc_worker,
    )

    reset_smtc_worker()
    read_spotify_session_after_sta_com_probe(timeout=5.0)
