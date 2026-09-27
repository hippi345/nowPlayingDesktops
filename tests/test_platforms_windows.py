import sys
from pathlib import Path
from unittest.mock import patch

import pytest

if sys.platform == "win32":
    from now_playing_desktops.platforms.windows import set_desktop_wallpaper


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only API")
def test_set_desktop_wallpaper_calls_system_parameters(tmp_path: Path):
    from PIL import Image

    image = tmp_path / "bg.jpg"
    Image.new("RGB", (64, 64), (30, 60, 90)).save(image, format="JPEG")

    with (
        patch(
            "now_playing_desktops.platforms.windows.WindowsWallpaperPlatform._monitor_pixel_size_for_screen",
            return_value=(64, 64),
        ),
        patch("now_playing_desktops.platforms.windows_restore.winreg"),
        patch("now_playing_desktops.platforms.windows.ctypes") as ctypes_mock,
    ):
        ctypes_mock.windll.user32.SystemParametersInfoW.return_value = 1
        set_desktop_wallpaper(image)
        ctypes_mock.windll.user32.SystemParametersInfoW.assert_called_once()


def test_windows_module_importable_on_linux():
    """Ensure importing the module does not require win32 at import time."""
    import now_playing_desktops.platforms.windows as win

    assert hasattr(win, "set_desktop_wallpaper")
