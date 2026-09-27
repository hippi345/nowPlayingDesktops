"""Optional background compose quality verification."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PIL import Image

logger = logging.getLogger(__name__)


def schedule_compose_quality_verification(
    *,
    composed: Image.Image,
    cover: Image.Image,
    title: str,
    artist: str,
    width: int,
    height: int,
) -> None:
    from now_playing_desktops.config import compose_verification_enabled

    if not compose_verification_enabled():
        return
    composed_copy = composed.copy()
    cover_copy = cover.copy()
    thread = threading.Thread(
        target=_run_compose_quality_checks,
        kwargs={
            "composed": composed_copy,
            "cover": cover_copy,
            "title": title,
            "artist": artist,
            "width": width,
            "height": height,
        },
        name="now-playing-compose-verify",
        daemon=True,
    )
    thread.start()


def _run_compose_quality_checks(
    *,
    composed: Image.Image,
    cover: Image.Image,
    title: str,
    artist: str,
    width: int,
    height: int,
) -> None:
    from now_playing_desktops.composer import plan_wallpaper_layout, render_backdrop
    from now_playing_desktops.config import strict_compose_verification_enabled
    from now_playing_desktops.verification.wallpaper_analysis import (
        assert_glass_panel_present,
        assert_no_backdrop_band_edges,
        assert_title_text_present,
    )

    layout = plan_wallpaper_layout(
        cover,
        title=title,
        artist=artist,
        width=width,
        height=height,
    )
    backdrop = render_backdrop(cover, width, height)
    checks: list[tuple[str, Callable[[], None]]] = [
        (
            "glass panel",
            lambda: assert_glass_panel_present(
                composed,
                layout,
                backdrop,
                require_uniformity=False,
            ),
        ),
        ("title text", lambda: assert_title_text_present(composed, layout)),
        (
            "backdrop bands",
            lambda: assert_no_backdrop_band_edges(
                composed,
                cover,
                layout=layout,
                analysis_max_width=640,
            ),
        ),
    ]
    for label, check in checks:
        try:
            check()
        except AssertionError as exc:
            message = f"Compose quality check failed ({label}): {exc}"
            if strict_compose_verification_enabled():
                logger.error("%s (background verify)", message)
            else:
                logger.warning("%s (background verify)", message)
