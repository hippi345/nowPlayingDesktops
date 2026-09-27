#!/usr/bin/env python3
"""Legacy entry point — use `now-playing-windows` instead."""

import sys
import warnings

if sys.platform == "win32":
    from now_playing_desktops.platforms.windows_dpi import set_process_dpi_aware

    set_process_dpi_aware()

from now_playing_desktops.cli import main_windows

warnings.warn(
    "spotifyWindows.py is deprecated; use `pip install` and run `now-playing-windows`.",
    DeprecationWarning,
    stacklevel=1,
)

if __name__ == "__main__":
    main_windows()
