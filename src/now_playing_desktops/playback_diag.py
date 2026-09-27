"""Diagnostics for playback sources (no secrets)."""

from __future__ import annotations

import os

from now_playing_desktops.auth import (
    cached_token_available,
    spotify_auth_mode,
    spotify_oauth_manager,
)
from now_playing_desktops.playback_source import (
    PlaybackSourceSetting,
    resolve_effective_playback_source,
)
from now_playing_desktops.sources.local import build_local_provider
from now_playing_desktops.sources.spotify_provider import SpotifyPlaybackProvider


def _format_track_line(prefix: str, track) -> str:
    if track is None:
        return f"{prefix}: (no session)"
    state = "playing" if track.is_playing else "paused"
    album = f" / {track.album}" if track.album else ""
    art = "bytes" if track.art_bytes else (track.art_url or "(no art)")
    return f"{prefix}: {state} — {track.artist} — {track.title}{album} [art={art}]"


def playback_diag_lines(
    *,
    source_setting: PlaybackSourceSetting,
    username: str | None,
) -> list[str]:
    effective = resolve_effective_playback_source(explicit=source_setting)
    lines = [
        f"Playback source setting: {source_setting}",
        f"Playback source active: {effective}",
    ]

    spotify_reasons: list[str] = []
    if not os.environ.get("SPOTIPY_CLIENT_ID", "").strip():
        spotify_reasons.append("SPOTIPY_CLIENT_ID not set")
    mode = spotify_auth_mode()
    if mode:
        lines.append(f"Spotify auth mode: {mode}")
        if username:
            manager = spotify_oauth_manager(username, interactive=False)
            if manager is None:
                lines.append("Spotify cached token: no")
            else:
                lines.append(
                    "Spotify cached token: " + ("yes" if cached_token_available(manager) else "no")
                )
            provider = SpotifyPlaybackProvider.from_username(username)
            if provider is None:
                spotify_reasons.append("could not build Spotify client")
                lines.append(_format_track_line("Spotify source sees", None))
            else:
                lines.append(_format_track_line("Spotify source sees", provider.peek_current()))
        else:
            lines.append("Spotify cached token: unknown (no username)")
            lines.append(_format_track_line("Spotify source sees", None))
    else:
        lines.append("Spotify auth mode: (not configured)")
        lines.append(_format_track_line("Spotify source sees", None))

    local = build_local_provider()
    local_reason = local.availability_reason()
    if local_reason:
        lines.append(f"Local source: unavailable ({local_reason})")
        lines.append(_format_track_line("Local source sees", None))
    else:
        lines.append(_format_track_line("Local source sees", local.peek_current()))

    if spotify_reasons and effective == "spotify":
        lines.append("Spotify unavailable: " + "; ".join(spotify_reasons))
    return lines
