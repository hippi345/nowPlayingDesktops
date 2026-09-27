from __future__ import annotations

from unittest.mock import patch


def test_playing_thumbnail_returns_on_first_success_without_refetch():
    import asyncio
    from now_playing_desktops.sources.local.windows_smtc_async import _read_thumbnail_with_refetch

    read_calls = {"count": 0}

    class FakeThumb:
        pass

    class FakeProps:
        thumbnail = FakeThumb()

    class FakeSession:
        async def try_get_media_properties_async(self):
            read_calls["count"] += 1
            return FakeProps()

    async def read_once(_thumb):
        return b"art-bytes"

    async def _run():
        with patch(
            "now_playing_desktops.sources.local.windows_smtc_async.read_thumbnail_reference_bytes_once",
            read_once,
        ):
            return await _read_thumbnail_with_refetch(
                FakeSession(),
                FakeProps(),
                is_playing=True,
            )

    result = asyncio.run(_run())
    assert result == b"art-bytes"
    assert read_calls["count"] == 0
