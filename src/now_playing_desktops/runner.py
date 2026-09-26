"""Main playback loop: compose art, dedupe updates, restore original wallpaper."""

from __future__ import annotations

import atexit
import logging
import os
import signal
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image

from now_playing_desktops.art_cache import ComposedArtCache
from now_playing_desktops.composer import compose_wallpaper, save_wallpaper
from now_playing_desktops.platforms.base import WallpaperPlatform
from now_playing_desktops.spotify_art import (
    TrackPlayback,
    download_album_art,
    fetch_playback_with_backoff,
)
from now_playing_desktops.wallpaper_state import (
    WallpaperSessionState,
    should_capture_as_original,
)

logger = logging.getLogger(__name__)


@dataclass
class RunnerDeps:
    platform: WallpaperPlatform
    sp: object
    cache_dir: Path
    state_path: Path
    poll_interval_seconds: float
    session: requests.Session | None = None
    on_token_refresh: Callable[[], None] | None = None
    sleep: Callable[[float], None] | None = None  # injected in tests

    def __post_init__(self) -> None:
        if self.sleep is None:
            import time

            self.sleep = time.sleep


class NowPlayingRunner:
    """Coordinates Spotify polling, composition, caching, and wallpaper restore."""

    def __init__(self, deps: RunnerDeps) -> None:
        self.deps = deps
        self._composed_cache = ComposedArtCache(deps.cache_dir / "composed")
        self._download_dir = deps.cache_dir / "downloads"
        self._last_applied: tuple[str, str] | None = None
        self._state = WallpaperSessionState.load(deps.state_path)
        self._restore_registered = False

    def _sleep(self, seconds: float) -> None:
        self.deps.sleep(seconds)

    def restore_original_wallpaper(self) -> bool:
        state = WallpaperSessionState.load(self.deps.state_path)
        original = state.original_wallpaper_path
        if not original:
            logger.info("No saved original wallpaper to restore")
            state.session_active = False
            state.save(self.deps.state_path)
            return False
        path = Path(original)
        if not path.is_file():
            logger.warning("Saved original wallpaper missing: %s", path)
            state.session_active = False
            state.save(self.deps.state_path)
            return False
        self.deps.platform.set_wallpaper(path)
        state.session_active = False
        state.save(self.deps.state_path)
        self._last_applied = None
        logger.info("Restored original wallpaper: %s", path)
        return True

    def _ensure_original_saved(self, *, activate_session: bool) -> None:
        generated_dir = self.deps.cache_dir.resolve()
        current = self.deps.platform.get_current_wallpaper()
        original = should_capture_as_original(
            current,
            generated_dir=generated_dir,
            stored_original=self._state.original_wallpaper_path,
        )
        if original is None:
            logger.debug("Skipping original capture (generated wallpaper or unknown path)")
            return
        self._state.original_wallpaper_path = str(original.resolve())
        self._state.generated_wallpaper_dir = str(generated_dir)
        if activate_session:
            self._state.session_active = True
        self._state.save(self.deps.state_path)
        logger.info("Saved original wallpaper path: %s", original)

    def _register_shutdown_handlers(self) -> None:
        if self._restore_registered:
            return
        self._restore_registered = True

        def _restore_on_exit() -> None:
            try:
                self.restore_original_wallpaper()
            except Exception:  # noqa: BLE001 — best-effort on shutdown
                logger.exception("Failed to restore wallpaper on exit")

        atexit.register(_restore_on_exit)

        def _signal_handler(_signum: int, _frame: object) -> None:
            _restore_on_exit()
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

    def startup(self) -> None:
        state = WallpaperSessionState.load(self.deps.state_path)
        recovered_crash = bool(state.session_active)
        if recovered_crash:
            logger.warning("Previous session did not restore; recovering original wallpaper")
            self.restore_original_wallpaper()
        self._state = WallpaperSessionState.load(self.deps.state_path)
        self._ensure_original_saved(activate_session=not recovered_crash)
        self._register_shutdown_handlers()

    def _compose_path(
        self,
        track: TrackPlayback,
        width: int,
        height: int,
    ) -> Path:
        cached = self._composed_cache.get(track.track_id, track.art_url, width, height)
        if cached:
            logger.debug("Cache hit for %s at %sx%s", track.track_id, width, height)
            return cached

        self._download_dir.mkdir(parents=True, exist_ok=True)
        download_path = self._download_dir / f"{track.track_id}.jpg"
        download_album_art(track.art_url, download_path, session=self.deps.session)
        with Image.open(download_path) as cover:
            composed = compose_wallpaper(
                cover,
                title=track.title,
                artist=track.artist,
                width=width,
                height=height,
            )
        fd, tmp_name = tempfile.mkstemp(suffix=".png", dir=self._composed_cache.cache_dir)
        os.close(fd)
        tmp = Path(tmp_name)
        save_wallpaper(composed, tmp)
        return self._composed_cache.put(track.track_id, track.art_url, width, height, tmp)

    def apply_playback_once(self) -> None:
        track = fetch_playback_with_backoff(
            self.deps.sp,
            on_token_refresh=self.deps.on_token_refresh,
        )
        if track is None or not track.is_playing:
            self.restore_original_wallpaper()
            return

        key = (track.track_id, track.art_url)
        if key == self._last_applied:
            logger.debug("Track unchanged; skipping wallpaper update")
            return

        width, height = self.deps.platform.get_primary_screen_size()
        composed_path = self._compose_path(track, width, height)
        self.deps.platform.set_wallpaper(composed_path)
        self._last_applied = key
        self._state.session_active = True
        self._state.save(self.deps.state_path)
        logger.info("Updated wallpaper for %s — %s", track.artist, track.title)

    def run_forever(self) -> None:
        self.startup()
        while True:
            try:
                self.apply_playback_once()
            except Exception:  # noqa: BLE001 — keep loop alive
                logger.exception("Unexpected error in playback loop")
            self._sleep(self.deps.poll_interval_seconds)
