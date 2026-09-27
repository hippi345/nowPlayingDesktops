"""Main playback loop: compose art, dedupe updates, restore original wallpaper."""

from __future__ import annotations

import atexit
import faulthandler
import logging
import os
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from now_playing_desktops.apply_timing import ApplyTiming
from now_playing_desktops.config import online_art_enabled
from now_playing_desktops.art_background_upgrade import BackgroundArtUpgrader
from now_playing_desktops.art_cache import ComposedArtCache
from now_playing_desktops.compose_verify import schedule_compose_quality_verification
from now_playing_desktops.composer import compose_wallpaper, save_wallpaper
from now_playing_desktops.cover_art import load_track_cover
from now_playing_desktops.platforms.base import WallpaperPlatform
from now_playing_desktops.playback_types import TrackPlayback
from now_playing_desktops.poll_watchdog import PollStallWatchdog
from now_playing_desktops.sources.base import PlaybackProvider
from now_playing_desktops.wallpaper_state import (
    WallpaperSessionState,
    path_is_under_directory,
    should_capture_as_original,
)

logger = logging.getLogger(__name__)


@dataclass
class RunnerDeps:
    platform: WallpaperPlatform
    playback_provider: PlaybackProvider
    cache_dir: Path
    state_path: Path
    poll_interval_seconds: float
    session: requests.Session | None = None
    sleep: Callable[[float], None] | None = None  # injected in tests

    def __post_init__(self) -> None:
        if self.sleep is None:
            import time

            self.sleep = time.sleep


def fetch_playback_for_runner(deps: RunnerDeps) -> TrackPlayback | None:
    """Resolve current playback; patched in unit tests."""
    return deps.playback_provider.fetch_current()


class NowPlayingRunner:
    """Coordinates Spotify polling, composition, caching, and wallpaper restore."""

    def __init__(self, deps: RunnerDeps) -> None:
        self.deps = deps
        self._composed_cache = ComposedArtCache(deps.cache_dir / "composed")
        self._download_dir = deps.cache_dir / "downloads"
        self._last_composed_identity: tuple[str, str] | None = None
        self._now_playing_wallpaper_active: bool = False
        self._state = WallpaperSessionState.load(deps.state_path)
        self._restore_registered = False
        self._render_errors_logged: set[str] = set()
        self._logged_idle_no_original_restore = False
        self._poll_tick = 0
        self._last_poll_ok_monotonic = time.monotonic()
        self._last_heartbeat_monotonic = time.monotonic()
        self._last_poll_state = "unknown"
        self._art_upgrader = BackgroundArtUpgrader()
        self._upgrade_apply_lock = threading.Lock()

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
            logger.info("Restored original wallpaper from snapshot")
            return True

        original = state.original_wallpaper_path
        if not original:
            if not self._logged_idle_no_original_restore:
                logger.info("No saved original wallpaper to restore")
                self._logged_idle_no_original_restore = True
            else:
                logger.debug("No saved original wallpaper to restore")
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
        logger.info("Restored original wallpaper: %s", path)
        return True

    def _clear_restored_session(self, state: WallpaperSessionState) -> None:
        state.clear_restore_data()
        state.save(self.deps.state_path)
        self._state = WallpaperSessionState.load(self.deps.state_path)

    def _ensure_original_saved(self, *, activate_session: bool, recovering: bool = False) -> None:
        generated_dir = self.deps.cache_dir.resolve()
        current = self.deps.platform.get_current_wallpaper()
        current_is_ours = current is not None and path_is_under_directory(current, generated_dir)
        if current_is_ours and (
            self._state.original_wallpaper_snapshot or self._state.original_wallpaper_path
        ):
            self._state.generated_wallpaper_dir = str(generated_dir)
            if activate_session:
                self._state.session_active = True
            self._state.save(self.deps.state_path)
            logger.debug("Keeping stored original; current wallpaper is our render")
            return
        original = should_capture_as_original(
            current,
            generated_dir=generated_dir,
            stored_original=self._state.original_wallpaper_path,
        )
        if original is None and not hasattr(self.deps.platform, "capture_restore_snapshot"):
            logger.debug("Skipping original capture (generated wallpaper or unknown path)")
            return
        if current_is_ours:
            logger.debug("Skipping original capture while showing our render")
            return
        if hasattr(self.deps.platform, "capture_restore_snapshot"):
            snapshot = self.deps.platform.capture_restore_snapshot(
                state_dir=self.deps.state_path.parent,
                generated_dir=generated_dir,
                existing_snapshot=self._state.original_wallpaper_snapshot,
                session_active=self._state.session_active,
                recovering=recovering,
            )
            if snapshot.get("stable_path"):
                self._state.original_wallpaper_snapshot = snapshot
                self._state.original_wallpaper_path = snapshot["stable_path"]
            elif original is not None:
                self._state.original_wallpaper_path = str(original.resolve())
        elif original is not None:
            self._state.original_wallpaper_path = str(original.resolve())
        self._state.generated_wallpaper_dir = str(generated_dir)
        if activate_session:
            self._state.session_active = True
        self._state.save(self.deps.state_path)
        logger.info("Saved original wallpaper path: %s", self._state.original_wallpaper_path)

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
        self._ensure_original_saved(
            activate_session=not recovered_crash,
            recovering=recovered_crash,
        )
        self._register_shutdown_handlers()

    def _compose_path(
        self,
        track: TrackPlayback,
        width: int,
        height: int,
        timing: ApplyTiming,
    ) -> Path:
        material = track.composed_art_material_key
        cached = self._composed_cache.get(track.track_id, material, width, height)
        if cached:
            timing.note_cache("hit")
            logger.debug("Cache hit for %s at %sx%s", track.track_id, width, height)
            return cached

        timing.note_cache("miss")
        with timing.stage("fetch"):
            cover = load_track_cover(
                track,
                download_dir=self._download_dir,
                session=self.deps.session,
            )
        with timing.stage("compose"):
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
        if composed.size != (width, height):
            raise ValueError(
                f"Composed wallpaper size {composed.size[0]}x{composed.size[1]} "
                f"does not match target {width}x{height}",
            )
        with timing.stage("save"):
            save_wallpaper(composed, tmp)
        schedule_compose_quality_verification(
            composed=composed,
            cover=cover,
            title=track.title,
            artist=track.artist,
            width=width,
            height=height,
        )
        return self._composed_cache.put(track.track_id, material, width, height, tmp)

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

    def _resolve_wallpaper_render_jobs(
        self,
        screens: list,
    ) -> list[tuple[str | None, int, int, bool]]:
        """Return ``(screen_id, width, height, virtual_desktop_span)`` render jobs."""
        per_screen = self.deps.platform.supports_per_screen_wallpaper()
        if per_screen and len(screens) > 1:
            return [(screen.screen_id, screen.width, screen.height, False) for screen in screens]
        if sys.platform == "win32" and len(screens) > 1:
            from now_playing_desktops.platforms.windows_monitors import (
                MonitorInfo,
                compose_canvas_pixel_size,
                log_monitors_for_wallpaper_render,
            )

            monitors = [
                MonitorInfo(
                    monitor_id=screen.screen_id,
                    width=screen.width,
                    height=screen.height,
                    is_primary=screen.is_primary,
                    left=getattr(screen, "left", 0),
                    top=getattr(screen, "top", 0),
                    device_name=getattr(screen, "device_name", ""),
                )
                for screen in screens
            ]
            log_monitors_for_wallpaper_render(monitors)
            width, height = compose_canvas_pixel_size(monitors)
            return [(None, width, height, True)]
        if screens:
            primary = next((s for s in screens if s.is_primary), screens[0])
            return [(None, primary.width, primary.height, False)]
        width, height = self.deps.platform.get_primary_screen_size()
        return [(None, width, height, False)]

    def _monitors_from_screens(self, screens: list) -> list:
        from now_playing_desktops.platforms.windows_monitors import MonitorInfo

        return [
            MonitorInfo(
                monitor_id=screen.screen_id,
                width=screen.width,
                height=screen.height,
                is_primary=screen.is_primary,
                left=getattr(screen, "left", 0),
                top=getattr(screen, "top", 0),
                device_name=getattr(screen, "device_name", ""),
            )
            for screen in screens
        ]

    def _monitor_layout_signature(self, monitors: list) -> str:
        return "|".join(
            f"{monitor.monitor_id}:{monitor.width}x{monitor.height}@{monitor.left},{monitor.top}"
            for monitor in sorted(monitors, key=lambda item: item.monitor_id)
        )

    def _compose_virtual_desktop_path(
        self,
        track: TrackPlayback,
        monitors: list,
        timing: ApplyTiming,
    ) -> Path:
        from now_playing_desktops.platforms.windows_monitors import compose_canvas_pixel_size
        from now_playing_desktops.platforms.windows_virtual_compose import (
            compose_virtual_desktop_wallpaper,
            monitor_rect_on_canvas,
            virtual_desktop_origin,
        )

        canvas_w, canvas_h = compose_canvas_pixel_size(monitors)
        signature = self._monitor_layout_signature(monitors)
        material = track.composed_art_material_key
        cached = self._composed_cache.get(
            track.track_id,
            material,
            canvas_w,
            canvas_h,
            layout_signature=f"virtual:{signature}",
        )
        if cached:
            timing.note_cache("hit")
            logger.debug("Virtual desktop cache hit for %s", track.track_id)
            return cached

        timing.note_cache("miss")
        with timing.stage("fetch"):
            cover = load_track_cover(
                track,
                download_dir=self._download_dir,
                session=self.deps.session,
            )
        with timing.stage("compose"):
            composed = compose_virtual_desktop_wallpaper(
                cover,
                title=track.title,
                artist=track.artist,
                monitors=monitors,
            )
        if composed.size != (canvas_w, canvas_h):
            raise ValueError(
                f"Virtual desktop wallpaper size {composed.size} != {canvas_w}x{canvas_h}",
            )
        fd, tmp_name = tempfile.mkstemp(suffix=".png", dir=self._composed_cache.cache_dir)
        os.close(fd)
        tmp = Path(tmp_name)
        with timing.stage("save"):
            save_wallpaper(composed, tmp)
        if monitors:
            primary = next((m for m in monitors if m.is_primary), monitors[0])
            origin_left, origin_top = virtual_desktop_origin(monitors)
            x0, y0, x1, y1 = monitor_rect_on_canvas(
                primary,
                origin_left=origin_left,
                origin_top=origin_top,
            )
            schedule_compose_quality_verification(
                composed=composed.crop((x0, y0, x1, y1)),
                cover=cover,
                title=track.title,
                artist=track.artist,
                width=primary.width,
                height=primary.height,
            )
        return self._composed_cache.put(
            track.track_id,
            material,
            canvas_w,
            canvas_h,
            tmp,
            layout_signature=f"virtual:{signature}",
        )

    def _apply_wallpaper_for_track(self, track: TrackPlayback, timing: ApplyTiming) -> None:
        screens = self.deps.platform.list_screens()
        monitors = self._monitors_from_screens(screens) if sys.platform == "win32" else []
        for screen_id, width, height, virtual_span in self._resolve_wallpaper_render_jobs(
            screens,
        ):
            if width <= 0 or height <= 0:
                label = screen_id or "primary"
                raise ValueError(
                    f"Invalid wallpaper size {width}x{height} for screen {label}",
                )
            if virtual_span:
                composed_path = self._compose_virtual_desktop_path(track, monitors, timing)
            else:
                composed_path = self._compose_path(track, width, height, timing)
            with timing.stage("set"):
                if virtual_span:
                    self.deps.platform.set_wallpaper(
                        composed_path,
                        virtual_desktop_span=True,
                    )
                else:
                    self.deps.platform.set_wallpaper(composed_path, screen_id=screen_id)

    def _handle_idle_playback(self) -> None:
        self._art_upgrader.cancel_pending()
        if not self._now_playing_wallpaper_active:
            return
        self.restore_original_wallpaper()
        self._now_playing_wallpaper_active = False
        self._last_composed_identity = None

    @staticmethod
    def _poll_state_label(track: TrackPlayback | None) -> str:
        if track is None:
            return "no session"
        if not track.is_playing:
            return f"paused — {track.artist} — {track.title}"
        return f"playing — {track.artist} — {track.title}"

    def _playback_matches_ticket(self, ticket) -> bool:
        track = fetch_playback_for_runner(self.deps)
        if track is None or not track.is_playing:
            return False
        return track.track_id == ticket.track_id

    def _apply_upgraded_art(self, track: TrackPlayback, ticket) -> None:
        with self._upgrade_apply_lock:
            if not self._playback_matches_ticket(ticket):
                logger.debug("Skipping iTunes upgrade apply; playback no longer matches")
                return
            identity = (track.track_id, track.art_cache_key)
            if self._last_composed_identity == identity:
                return
            timing = ApplyTiming()
            try:
                self._apply_wallpaper_for_track(track, timing)
            except Exception as exc:
                self._log_render_error_once(track.track_id, exc)
                return
            finally:
                timing.log_summary(prefix="Upgraded art")
            self._render_errors_logged.discard(track.track_id)
            self._last_composed_identity = identity
            self._now_playing_wallpaper_active = True
            self._state.session_active = True
            self._state.save(self.deps.state_path)
            logger.info("Updated wallpaper for %s — %s (iTunes art)", track.artist, track.title)

    def _schedule_itunes_upgrade_if_needed(self, track: TrackPlayback) -> None:
        if not online_art_enabled():
            return
        if not self._art_upgrader.should_schedule(track):
            return
        self._art_upgrader.schedule(
            track,
            download_dir=self._download_dir,
            session=self.deps.session,
            on_upgraded=self._apply_upgraded_art,
            is_still_valid=self._playback_matches_ticket,
        )

    def _apply_track_wallpaper(self, track: TrackPlayback) -> None:
        timing = ApplyTiming()
        try:
            self._apply_wallpaper_for_track(track, timing)
        except Exception as exc:
            self._log_render_error_once(track.track_id, exc)
            return
        finally:
            timing.log_summary()

        self._render_errors_logged.discard(track.track_id)
        self._logged_idle_no_original_restore = False
        identity = (track.track_id, track.art_cache_key)
        self._last_composed_identity = identity
        self._now_playing_wallpaper_active = True
        self._state.session_active = True
        self._state.save(self.deps.state_path)
        logger.info("Updated wallpaper for %s — %s", track.artist, track.title)
        self._schedule_itunes_upgrade_if_needed(track)

    def apply_playback_once(self) -> None:
        track = fetch_playback_for_runner(self.deps)
        self._last_poll_state = self._poll_state_label(track)
        if track is None or not track.is_playing:
            self._handle_idle_playback()
            return

        if not self._state.original_wallpaper_path and not self._state.original_wallpaper_snapshot:
            self._ensure_original_saved(activate_session=True)

        identity = (track.track_id, track.art_cache_key)
        if self._now_playing_wallpaper_active and identity == self._last_composed_identity:
            logger.debug("Track unchanged; skipping wallpaper update")
            return

        if (
            self._last_composed_identity is not None
            and self._last_composed_identity[0] != track.track_id
        ):
            self._art_upgrader.cancel_pending()

        self._apply_track_wallpaper(track)

    def _log_poll_tick(self, *, poll_elapsed: float) -> None:
        source = getattr(self.deps.playback_provider, "source_name", "unknown")
        last_ok_age = time.monotonic() - self._last_poll_ok_monotonic
        logger.debug(
            "poll tick %s (source=%s, state=%s, last_ok=%.1fs ago, poll_took=%.2fs)",
            self._poll_tick,
            source,
            self._last_poll_state,
            last_ok_age,
            poll_elapsed,
        )
        if time.monotonic() - self._last_heartbeat_monotonic >= 60.0:
            logger.info(
                "Heartbeat: poll tick %s, source=%s, state=%s, last_ok=%.0fs ago",
                self._poll_tick,
                source,
                self._last_poll_state,
                last_ok_age,
            )
            self._last_heartbeat_monotonic = time.monotonic()
        if poll_elapsed >= 10.0:
            logger.warning(
                "Playback poll exceeded 10s wall time (%.2fs); dumping thread stacks",
                poll_elapsed,
            )
            faulthandler.dump_traceback(all_threads=True)

    def run_forever(self) -> None:
        self.startup()
        watchdog = PollStallWatchdog()
        watchdog.start()
        while True:
            self._poll_tick += 1
            poll_started = time.monotonic()
            watchdog.begin_poll()
            try:
                try:
                    self.apply_playback_once()
                    self._last_poll_ok_monotonic = time.monotonic()
                except Exception:  # noqa: BLE001 — keep loop alive
                    logger.exception("Unexpected error in playback loop")
            finally:
                watchdog.end_poll()
            poll_elapsed = time.monotonic() - poll_started
            self._log_poll_tick(poll_elapsed=poll_elapsed)
            self._sleep(self.deps.poll_interval_seconds)
