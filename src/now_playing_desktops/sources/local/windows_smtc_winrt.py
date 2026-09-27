"""WinRT await helpers with hard timeouts."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

WINRT_AWAIT_TIMEOUT_SECONDS = 3.0


class WinrtTimeoutError(TimeoutError):
    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(operation)


async def winrt_wait(
    awaitable,
    *,
    operation: str,
    timeout: float = WINRT_AWAIT_TIMEOUT_SECONDS,
):
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except TimeoutError:
        logger.warning("WinRT call timed out after %.1fs: %s", timeout, operation)
        raise WinrtTimeoutError(operation) from None
