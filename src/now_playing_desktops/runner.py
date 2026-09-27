"""Main playback loop: compose art, dedupe updates, restore original wallpaper."""

from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
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
        self._render_errors_logged: set[str] = set()

    def _sleep(self, seconds: float) -> None:
        self.deps.sleep(seconds)

    def restore_original_wallpaper(self) -> bool:
        state = WallpaperSessionState.load(self.deps.state_path)
        snapshot = state.original_wallpaper_snapshot
        if snapshot:
            try:
                self.deps.platform.apply_restore_snapshot(snapshot)
            except Exception:
                logger.exception("Failed to apply wallpaper restore snapshot")
                return False
            self._clear_restored_session(state)
            self._last_applied = None
            logger.info("Restored original wallpaper from snapshot")
            return True

        original = state.original_wallpaper_path
        if not original:
            logger.info("No saved original wallpaper to restore")
            if state.session_active:
                state.clear_restore_data()
                state.save(self.deps.state_path)
                self._state = WallpaperSessionState.load(self.deps.state_path)
            return False
        path = Path(original)
        if not path.is_file():
            logger.warning("Saved original wallpaper missing: %s", path)
            return False
        self.deps.platform.set_wallpaper(path)
        self._clear_restored_session(state)
        self._last_applied = None
        logger.info("Restored original wallpaper: %s", path)
        return True

    def _clear_restored_session(self, state: WallpaperSessionState) -> None:
        state.clear_restore_data()
        state.save(self.deps.state_path)
        self._state = WallpaperSessionState.load(self.deps.state_path)

    def _ensure_original_saved(self, *, activate_session: bool) -> None:
        generated_dir = self.deps.cache_dir.resolve()
        current = self.deps.platform.get_current_wallpaper()
        original = should_capture_as_original(
            current,
            generated_dir=generated_dir,
            stored_original=self._state.original_wallpaper_path,
        )
        if original is None and not hasattr(self.deps.platform, "capture_restore_snapshot"):
            logger.debug("Skipping original capture (generated wallpaper or unknown path)")
            return
        if original is not None:
            self._state.original_wallpaper_path = str(original.resolve())
            if hasattr(self.deps.platform, "capture_restore_snapshot"):
                self._state.original_wallpaper_snapshot = (
                    self.deps.platform.capture_restore_snapshot(
                        state_dir=self.deps.state_path.parent,
                        generated_dir=generated_dir,
                    )
                )
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

        if sys.platform == "win32":
            from now_playing_desktops.platforms.windows_console import (
                register_console_restore_handler,
            )

            register_console_restore_handler(_restore_on_exit)

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

    def _log_render_error_once(self, track_id: str, exc: BaseException) -> None:
        if track_id in self._render_errors_logged:
            return
        self._render_errors_logged.add(track_id)
        logger.error(
            "Failed to update wallpaper for track %s: %s",
            track_id,
            exc,
            exc_info=True,
        )

    def _apply_wallpaper_for_track(self, track: TrackPlayback) -> None:
        screens = self.deps.platform.list_screens()
        per_screen = self.deps.platform.supports_per_screen_wallpaper()
        sizes = {(s.width, s.height) for s in screens}
        if per_screen and len(sizes) > 1:
            for screen in screens:
                if screen.width <= 0 or screen.height <= 0:
                    raise ValueError(
                        f"Invalid screen size {screen.width}x{screen.height} "
                        f"for screen {screen.screen_id}"
                    )
                composed_path = self._compose_path(track, screen.width, screen.height)
                self.deps.platform.set_wallpaper(composed_path, screen_id=screen.screen_id)
        else:
            if screens:
                best = max(screens, key=lambda s: s.width * s.height)
                width, height = best.width, best.height
            else:
                width, height = self.deps.platform.get_primary_screen_size()
            if width <= 0 or height <= 0:
                raise ValueError(f"Invalid wallpaper size {width}x{height}")
            composed_path = self._compose_path(track, width, height)
            self.deps.platform.set_wallpaper(composed_path)

    def apply_playback_once(self) -> None:
        track = fetch_playback_with_backoff(
            self.deps.sp,
            on_token_refresh=self.deps.on_token_refresh,
        )
        if track is None or not track.is_playing:
            self.restore_original_wallpaper()
            return

        if not self._state.original_wallpaper_path and not self._state.original_wallpaper_snapshot:
            self._ensure_original_saved(activate_session=True)

        key = (track.track_id, track.art_url)
        if key == self._last_applied:
            logger.debug("Track unchanged; skipping wallpaper update")
            return

        try:
            self._apply_wallpaper_for_track(track)
        except Exception as exc:
            self._log_render_error_once(track.track_id, exc)
            return

        self._render_errors_logged.discard(track.track_id)
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
