from __future__ import annotations

import asyncio

import pytest

from now_playing_desktops.sources.local.windows_smtc_winrt import WinrtTimeoutError, winrt_wait


def test_winrt_wait_times_out():
    async def slow():
        await asyncio.sleep(30)

    async def _run():
        with pytest.raises(WinrtTimeoutError):
            await winrt_wait(slow(), operation="slow.test", timeout=0.05)

    asyncio.run(_run())
