"""Application paths and defaults."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "now-playing-desktops"
DEFAULT_POLL_INTERVAL_SECONDS = 2.5
MIN_POLL_INTERVAL_SECONDS = 2.0
MAX_POLL_INTERVAL_SECONDS = 3.0
COMPOSED_CACHE_MAX_ENTRIES = 24
MAX_COVER_UPSCALE = 1.5
FOREGROUND_HEIGHT_RATIO = 0.4
STATE_FILENAME = "wallpaper-state.json"


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR_NAME


def default_cache_dir() -> Path:
    return user_config_dir() / "cache"


def state_file_path() -> Path:
    return user_config_dir() / STATE_FILENAME
