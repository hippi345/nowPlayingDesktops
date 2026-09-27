"""Detect main-thread polls that stall inside playback providers."""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import time

logger = logging.getLogger(__name__)

POLL_STALL_WARNING_SECONDS = 10.0


class PollStallWatchdog:
    def __init__(self, *, stall_seconds: float = POLL_STALL_WARNING_SECONDS) -> None:
        self._stall_seconds = stall_seconds
        self._poll_started: float | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="now-playing-poll-watchdog",
            daemon=True,
        )
        self._warned_for_poll: float | None = None

    def start(self) -> None:
        if sys.platform != "win32":
            return
        self._thread.start()

    def begin_poll(self) -> None:
        with self._lock:
            self._poll_started = time.monotonic()
            self._warned_for_poll = None

    def end_poll(self) -> None:
        with self._lock:
            self._poll_started = None
            self._warned_for_poll = None

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(1.0):
            with self._lock:
                started = self._poll_started
                warned = self._warned_for_poll
            if started is None:
                continue
            elapsed = time.monotonic() - started
            if elapsed < self._stall_seconds:
                continue
            if warned == started:
                continue
            with self._lock:
                self._warned_for_poll = started
            logger.warning(
                "Playback poll still running after %.1fs; dumping all thread stacks",
                elapsed,
            )
            faulthandler.dump_traceback(all_threads=True)
