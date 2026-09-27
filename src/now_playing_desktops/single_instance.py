"""Ensure only one ``now-playing run`` process is active."""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from now_playing_desktops.config import user_config_dir

logger = logging.getLogger(__name__)

RUN_MUTEX_NAME = r"Local\now-playing-desktops-run"
_LOCK_FILENAME = "run.lock"


@dataclass
class RunLockStatus:
    acquired: bool
    holder_description: str | None = None


class RunInstanceLock:
    """Held for the lifetime of a ``run`` session."""

    def __init__(self, *, acquired: bool, backend: str, handle: object | None = None) -> None:
        self.acquired = acquired
        self._backend = backend
        self._handle = handle
        self._file_handle = None

    def release(self) -> None:
        if sys.platform == "win32" and self._handle is not None:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        if self._file_handle is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    with contextlib.suppress(OSError):
                        msvcrt.locking(self._file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                self._file_handle.close()
            except OSError:
                pass
            self._file_handle = None
            lock_path = _lock_file_path()
            with contextlib.suppress(OSError):
                lock_path.unlink(missing_ok=True)

    @classmethod
    def try_acquire(cls) -> RunInstanceLock:
        if sys.platform == "win32":
            return cls._try_acquire_windows_mutex()
        return cls._try_acquire_file_lock()

    @classmethod
    def _try_acquire_windows_mutex(cls) -> RunInstanceLock:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, RUN_MUTEX_NAME)
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            if handle:
                kernel32.CloseHandle(handle)
            return cls(acquired=False, backend="windows-mutex")
        return cls(acquired=True, backend="windows-mutex", handle=handle)

    @classmethod
    def _try_acquire_file_lock(cls) -> RunInstanceLock:
        lock_path = _lock_file_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                handle.write(str(os.getpid()))
                handle.flush()
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
        except OSError:
            handle.close()
            return cls(acquired=False, backend="file-lock")
        lock = cls(acquired=True, backend="file-lock")
        lock._file_handle = handle
        return lock

    def __enter__(self) -> RunInstanceLock:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _lock_file_path() -> Path:
    return user_config_dir() / _LOCK_FILENAME


def probe_run_lock_held() -> RunLockStatus:
    """Return whether another instance appears to hold the run lock (non-destructive)."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, RUN_MUTEX_NAME)
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            if handle:
                kernel32.CloseHandle(handle)
            return RunLockStatus(acquired=False, holder_description="windows-mutex busy")
        if handle:
            kernel32.CloseHandle(handle)
        return RunLockStatus(acquired=True, holder_description=None)

    lock_path = _lock_file_path()
    if not lock_path.is_file():
        return RunLockStatus(acquired=True, holder_description=None)
    try:
        handle = lock_path.open("r+", encoding="utf-8")
    except OSError:
        return RunLockStatus(acquired=False, holder_description="lock file present")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pid = handle.read().strip() or "unknown"
        return RunLockStatus(acquired=False, holder_description=f"pid {pid}")
    finally:
        handle.close()
    return RunLockStatus(acquired=True, holder_description=None)


def ensure_single_run_instance() -> RunInstanceLock | None:
    """
    Acquire the run lock or log and return ``None`` when another instance is active.

    Callers should exit 0 when this returns ``None``.
    """
    lock = RunInstanceLock.try_acquire()
    if lock.acquired:
        return lock
    status = probe_run_lock_held()
    logger.warning(
        "Another now-playing run instance is already active (%s); exiting",
        status.holder_description or "lock held",
    )
    return None
