"""Playback source selection (Spotify Web API vs local OS media session)."""

from __future__ import annotations

import logging
import os
from typing import Literal

PlaybackSourceName = Literal["spotify", "local"]
PlaybackSourceSetting = Literal["spotify", "local", "auto"]

logger = logging.getLogger(__name__)

VALID_SOURCE_SETTINGS: frozenset[str] = frozenset({"spotify", "local", "auto"})


def _normalized_setting(value: str | None) -> PlaybackSourceSetting:
    raw = (value or "auto").strip().lower()
    if raw not in VALID_SOURCE_SETTINGS:
        msg = f"Invalid playback source {value!r}; use spotify, local, or auto"
        raise ValueError(msg)
    return raw  # type: ignore[return-value]


def resolve_effective_playback_source(
    *,
    explicit: str | None = None,
) -> PlaybackSourceName:
    """Resolve ``auto`` using whether ``SPOTIPY_CLIENT_ID`` is configured."""
    setting = _normalized_setting(explicit or os.environ.get("NOW_PLAYING_SOURCE"))
    if setting == "spotify":
        return "spotify"
    if setting == "local":
        return "local"
    if os.environ.get("SPOTIPY_CLIENT_ID", "").strip():
        return "spotify"
    return "local"


def log_selected_playback_source(
    *,
    setting: PlaybackSourceSetting,
    effective: PlaybackSourceName,
) -> None:
    if setting == "auto":
        logger.info("Playback source: auto -> %s", effective)
    else:
        logger.info("Playback source: %s", effective)
