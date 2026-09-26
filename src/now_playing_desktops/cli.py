"""Command-line entry points for macOS and Windows."""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import spotipy

from now_playing_desktops.auth import prompt_for_token
from now_playing_desktops.spotify_art import poll_and_update_wallpaper


def _run_platform(
    platform_name: str,
    *,
    poll_interval_seconds: float,
    prepare_artwork: Callable[[str], Path],
    set_wallpaper: Callable[[Path], None],
    after_update: Callable[[Path], None] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=f"Set desktop wallpaper from Spotify album art ({platform_name})."
    )
    parser.add_argument("username", help="Spotify username for OAuth")
    args = parser.parse_args()

    token = prompt_for_token(args.username)
    if not token:
        print("Can't get token for", args.username, file=sys.stderr)
        return 1

    sp = spotipy.Spotify(auth=token)

    try:
        poll_and_update_wallpaper(
            sp,
            poll_interval_seconds=poll_interval_seconds,
            prepare_artwork=prepare_artwork,
            set_wallpaper=set_wallpaper,
            after_update=after_update,
        )
    except KeyboardInterrupt:
        return 0
    return 0


def main_macos() -> None:
    from now_playing_desktops.platforms.macos import set_desktop_wallpaper

    cache_dir = Path(tempfile.gettempdir()) / "nowPlayingDesktops"

    def prepare_artwork(_url: str) -> Path:
        return cache_dir / f"current_artwork{datetime.now()}.jpg"

    def after_update(path: Path) -> None:
        import time

        time.sleep(2)
        path.unlink(missing_ok=True)

    raise SystemExit(
        _run_platform(
            "macOS",
            poll_interval_seconds=1.0,
            prepare_artwork=prepare_artwork,
            set_wallpaper=set_desktop_wallpaper,
            after_update=after_update,
        )
    )


def main_windows() -> None:
    from now_playing_desktops.platforms.windows import set_desktop_wallpaper

    cache_dir = Path(tempfile.gettempdir()) / "nowPlayingDesktops"
    artwork_path = cache_dir / "current_artwork.jpg"

    def prepare_artwork(_url: str) -> Path:
        return artwork_path

    def after_update(_path: Path) -> None:
        import time

        time.sleep(0.5)

    raise SystemExit(
        _run_platform(
            "Windows",
            poll_interval_seconds=0.5,
            prepare_artwork=prepare_artwork,
            set_wallpaper=set_desktop_wallpaper,
            after_update=after_update,
        )
    )


if __name__ == "__main__":
    print("Use the now-playing-macos or now-playing-windows commands.", file=sys.stderr)
    raise SystemExit(2)
