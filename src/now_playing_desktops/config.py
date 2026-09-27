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
# Bump when compose layout/visual output changes so stale PNGs are not reused.
COMPOSED_CACHE_VERSION = "glass-panel-v4"
MAX_COVER_UPSCALE = 1.5
FOREGROUND_HEIGHT_RATIO = 0.4
STATE_FILENAME = "wallpaper-state.json"


def strict_compose_verification_enabled() -> bool:
    return os.environ.get("NOW_PLAYING_STRICT_COMPOSE_VERIFY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def compose_verification_enabled() -> bool:
    """Optional post-apply quality checks (off by default; never blocks wallpaper set)."""
    return os.environ.get("NOW_PLAYING_COMPOSE_VERIFY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


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


def spotify_token_cache_path(username: str) -> Path:
    """OAuth token cache file for a Spotify username (PKCE or client-secret flow)."""
    safe = username.replace("/", "_").replace("\\", "_")
    return user_config_dir() / f"spotify-token-{safe}.cache"
