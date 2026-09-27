"""macOS Spotify.app AppleScript playback."""

from __future__ import annotations

import logging
import subprocess

from now_playing_desktops.playback_types import TrackPlayback, stable_track_id
from now_playing_desktops.sources.local.base import LocalPlaybackProvider

logger = logging.getLogger(__name__)

_APPLESCRIPT = """
on run
  tell application "Spotify"
    if player state is playing then
      set trackName to name of current track
      set trackArtist to artist of current track
      set trackAlbum to album of current track
      set artworkURL to artwork url of current track
      return trackName & linefeed & trackArtist & linefeed & trackAlbum & linefeed & artworkURL
        & linefeed & "playing"
    else if player state is paused then
      set trackName to name of current track
      set trackArtist to artist of current track
      set trackAlbum to album of current track
      set artworkURL to artwork url of current track
      return trackName & linefeed & trackArtist & linefeed & trackAlbum & linefeed & artworkURL
        & linefeed & "paused"
    end if
  end tell
  return ""
end run
"""


class MacOsSpotifyProvider(LocalPlaybackProvider):
    def _read_session(self) -> TrackPlayback | None:
        try:
            result = subprocess.run(
                ["osascript", "-e", _APPLESCRIPT],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.debug("osascript Spotify query failed", exc_info=True)
            return None
        if result.returncode != 0 or not result.stdout.strip():
            return None
        lines = result.stdout.strip().splitlines()
        if len(lines) < 5:
            return None
        title, artist, album, art_url, state = lines[0], lines[1], lines[2], lines[3], lines[4]
        is_playing = state.strip().lower() == "playing"
        track_id = stable_track_id(title=title, artist=artist, album=album)
        return TrackPlayback(
            track_id=track_id,
            art_url=art_url,
            title=title,
            artist=artist,
            album=album,
            is_playing=is_playing,
        )
