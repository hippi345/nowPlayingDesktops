"""Construct playback providers for CLI and autostart."""

from __future__ import annotations

import logging
import os

from now_playing_desktops.playback_source import (
    VALID_SOURCE_SETTINGS,
    PlaybackSourceName,
    PlaybackSourceSetting,
    log_selected_playback_source,
    resolve_effective_playback_source,
)
from now_playing_desktops.sources.base import PlaybackProvider
from now_playing_desktops.sources.local import build_local_provider
from now_playing_desktops.sources.spotify_provider import SpotifyPlaybackProvider

logger = logging.getLogger(__name__)


def parse_source_setting(value: str | None) -> PlaybackSourceSetting:
    raw = (value or os.environ.get("NOW_PLAYING_SOURCE") or "auto").strip().lower()
    if raw not in VALID_SOURCE_SETTINGS:
        msg = f"Invalid playback source {value!r}; use spotify, local, or auto"
        raise ValueError(msg)
    return raw  # type: ignore[return-value]


def build_playback_provider(
    *,
    source_setting: PlaybackSourceSetting,
    username: str | None,
) -> PlaybackProvider | None:
    effective = resolve_effective_playback_source(explicit=source_setting)
    log_selected_playback_source(setting=source_setting, effective=effective)
    if effective == "local":
        return build_local_provider()
    if not username:
        logger.error("Spotify username required for spotify playback source")
        return None
    return SpotifyPlaybackProvider.from_username(username)


def effective_source_name(source_setting: PlaybackSourceSetting) -> PlaybackSourceName:
    return resolve_effective_playback_source(explicit=source_setting)
