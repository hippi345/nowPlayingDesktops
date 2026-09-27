from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_console_close_handler_registers_restore():
    import now_playing_desktops.platforms.windows_console as windows_console
    from now_playing_desktops.platforms.windows_console import (
        CTRL_CLOSE_EVENT,
        register_console_restore_handler,
    )

    windows_console._registered_handler = None
    windows_console._win_handler_ref = None

    restore = MagicMock()
    handler_ref = None

    def capture_handler(handler, _add):
        nonlocal handler_ref
        handler_ref = handler
        return True

    with patch(
        "now_playing_desktops.platforms.windows_console.ctypes.windll.kernel32.SetConsoleCtrlHandler",
        side_effect=capture_handler,
    ):
        register_console_restore_handler(restore)

    assert handler_ref is not None
    assert handler_ref(CTRL_CLOSE_EVENT) is True
    restore.assert_called_once()
    assert handler_ref(0) is False
