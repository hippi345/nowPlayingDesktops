"""Dedicated MTA thread for WinRT / SMTC (avoids STA COM deadlock with pywin32)."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import TYPE_CHECKING

from now_playing_desktops.sources.local.windows_smtc_async import (
    is_winrt_timeout,
    read_spotify_session_async,
)

if TYPE_CHECKING:
    from now_playing_desktops.playback_types import TrackPlayback

logger = logging.getLogger(__name__)

SMTC_WORKER_READ_TIMEOUT_SECONDS = 12.0
SMTC_CONSECUTIVE_TIMEOUTS_BEFORE_REBUILD = 3

_COINIT_MULTITHREADED = 0x0
_RPC_E_CHANGED_MODE = -2147417850


def _initialize_mta_apartment() -> None:
    import ctypes

    hr = ctypes.windll.ole32.CoInitializeEx(None, _COINIT_MULTITHREADED)
    if hr not in (0, 1, _RPC_E_CHANGED_MODE):
        raise OSError(f"CoInitializeEx(MTA) failed: HRESULT=0x{hr & 0xFFFFFFFF:08X}")


def _worker_thread_main(
    ready: threading.Event,
    loop_holder: dict[str, asyncio.AbstractEventLoop],
) -> None:
    _initialize_mta_apartment()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop_holder["loop"] = loop
    ready.set()
    loop.run_forever()
    loop.close()


class SmtcSessionWorker:
    """Runs all WinRT SMTC I/O on one persistent MTA thread."""

    def __init__(self) -> None:
        self._ready = threading.Event()
        self._loop_holder: dict[str, asyncio.AbstractEventLoop] = {}
        self._thread = threading.Thread(
            target=_worker_thread_main,
            args=(self._ready, self._loop_holder),
            name="now-playing-smtc-mta",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=10.0):
            raise RuntimeError("SMTC worker thread failed to start within 10s")
        self._loop = self._loop_holder["loop"]
        self._consecutive_timeouts = 0
        self._session_generation = 0
        self._timeout_lock = threading.Lock()

    @property
    def consecutive_timeouts(self) -> int:
        return self._consecutive_timeouts

    def rebuild_session_manager(self) -> None:
        self._session_generation += 1
        logger.warning(
            "Rebuilding SMTC session manager after %s consecutive timeouts (generation=%s)",
            self._consecutive_timeouts,
            self._session_generation,
        )
        self._consecutive_timeouts = 0

    def read_spotify_session(
        self,
        *,
        timeout: float = SMTC_WORKER_READ_TIMEOUT_SECONDS,
    ) -> TrackPlayback | None:
        future = asyncio.run_coroutine_threadsafe(
            self._read_spotify_session_with_generation(),
            self._loop,
        )
        try:
            track = future.result(timeout=timeout)
        except FuturesTimeoutError:
            self._register_timeout("SMTC worker read (outer wait)")
            return None
        except Exception:
            logger.warning("SMTC session read failed on worker thread", exc_info=True)
            return None
        with self._timeout_lock:
            self._consecutive_timeouts = 0
        return track

    def _register_timeout(self, operation: str) -> None:
        with self._timeout_lock:
            self._consecutive_timeouts += 1
            count = self._consecutive_timeouts
        logger.warning(
            "SMTC read timed out (%s); consecutive timeouts=%s",
            operation,
            count,
        )
        if count >= SMTC_CONSECUTIVE_TIMEOUTS_BEFORE_REBUILD:
            self.rebuild_session_manager()

    async def _read_spotify_session_with_generation(self) -> TrackPlayback | None:
        generation = self._session_generation
        try:
            track = await read_spotify_session_async()
        except Exception as exc:
            if is_winrt_timeout(exc):
                self._register_timeout(str(exc))
                return None
            raise
        if generation != self._session_generation:
            logger.debug("Discarding SMTC read from stale generation %s", generation)
        return track

    def shutdown(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)


_worker: SmtcSessionWorker | None = None
_worker_lock = threading.Lock()


def get_smtc_worker() -> SmtcSessionWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = SmtcSessionWorker()
        return _worker


def reset_smtc_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.shutdown()
            _worker = None


def read_spotify_session_after_sta_com_probe(
    *,
    timeout: float = 5.0,
) -> None:
    """Exercise SMTC from the runner COM path; must return without hanging."""
    from now_playing_desktops.platforms.windows_com import idesktop_wallpaper_probe

    idesktop_wallpaper_probe()
    worker = get_smtc_worker()
    started = time.monotonic()
    worker.read_spotify_session(timeout=timeout)
    elapsed = time.monotonic() - started
    if elapsed >= timeout:
        raise AssertionError(f"SMTC read blocked for {elapsed:.2f}s (limit {timeout}s)")
