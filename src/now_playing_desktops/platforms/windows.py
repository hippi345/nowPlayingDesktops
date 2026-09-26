"""Windows desktop wallpaper via SystemParametersInfo."""

from __future__ import annotations

import ctypes
from pathlib import Path

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02


def set_desktop_wallpaper(image_path: Path) -> None:
    """Set the Windows desktop background to ``image_path``."""
    path_str = str(image_path.resolve())
    if not ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER,
        0,
        path_str,
        SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
    ):
        raise OSError(f"SystemParametersInfoW failed for {path_str}")
