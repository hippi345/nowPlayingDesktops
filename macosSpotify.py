#!/usr/bin/env python3
"""Legacy entry point — use `now-playing-macos` instead."""

import warnings

from now_playing_desktops.cli import main_macos

warnings.warn(
    "macosSpotify.py is deprecated; use `pip install` and run `now-playing-macos`.",
    DeprecationWarning,
    stacklevel=1,
)

if __name__ == "__main__":
    main_macos()
