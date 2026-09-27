"""Windows console control-handler for restore on window close."""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)

CTRL_C_EVENT = 0
CTRL_CLOSE_EVENT = 2

_Handler = Callable[[], None]
_registered_handler: _Handler | None = None
_win_handler_ref = None


def register_console_restore_handler(restore: _Handler) -> None:
    """Register ``restore`` for console close (CTRL_CLOSE_EVENT) on Windows."""
    global _registered_handler, _win_handler_ref
    if sys.platform != "win32":
        return
    if _registered_handler is not None:
        return
    _registered_handler = restore

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def _handler(ctrl_type: int) -> bool:
        if ctrl_type == CTRL_CLOSE_EVENT and _registered_handler is not None:
            try:
                logger.debug("Console close event; restoring wallpaper")
                _registered_handler()
            except Exception:
                logger.exception("Failed to restore wallpaper on console close")
            return True
        return False

    _win_handler_ref = _handler
    if not ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True):
        logger.warning("SetConsoleCtrlHandler failed")
