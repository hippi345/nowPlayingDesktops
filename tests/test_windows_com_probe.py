from __future__ import annotations

import sys
from unittest.mock import patch

from now_playing_desktops.platforms import windows_com as wc


def test_idesktop_wallpaper_probe_uses_ctypes_when_pythoncom_fails():
    wc._com_available = None
    wc._com_probe_detail = ""
    wc._com_backend = None
    with (
        patch.object(sys, "platform", "win32"),
        patch.object(
            wc,
            "_probe_pythoncom",
            return_value=(False, "pythoncom: ImportError: no module"),
        ),
        patch.object(
            wc,
            "_probe_ctypes_com",
            return_value=(True, "CoCreateInstance(IDesktopWallpaper) via ole32 succeeded"),
        ),
    ):
        ok, detail = wc.idesktop_wallpaper_probe()
        assert ok is True
        assert "ole32 succeeded" in detail
        assert wc.idesktop_wallpaper_available() is True
