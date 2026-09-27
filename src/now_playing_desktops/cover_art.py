"""Load and prepare album art for composition."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import requests
from PIL import Image

from now_playing_desktops.art_resolution import resolve_track_art
from now_playing_desktops.playback_types import TrackPlayback

logger = logging.getLogger(__name__)

LOW_RES_THUMBNAIL_MAX_PX = 400


def prepare_cover_image(cover: Image.Image) -> Image.Image:
    """Upscale small thumbnails so the blurred backdrop stays smooth."""
    rgba = cover.convert("RGBA")
    width, height = rgba.size
    logger.info("Track thumbnail size: %dx%d", width, height)
    max_dim = max(width, height)
    if max_dim >= LOW_RES_THUMBNAIL_MAX_PX:
        return rgba
    scale = LOW_RES_THUMBNAIL_MAX_PX / max_dim
    new_size = (max(int(width * scale), 1), max(int(height * scale), 1))
    upscaled = rgba.resize(new_size, Image.Resampling.LANCZOS)
    logger.info(
        "Upscaled low-resolution thumbnail from %dx%d to %dx%d",
        width,
        height,
        upscaled.width,
        upscaled.height,
    )
    return upscaled


def load_track_cover(
    track: TrackPlayback,
    *,
    download_dir: Path,
    session: requests.Session | None = None,
) -> Image.Image:
    download_dir.mkdir(parents=True, exist_ok=True)
    resolved = resolve_track_art(track, download_dir=download_dir, session=session)
    logger.info(
        "Track art source: %s (%s)",
        resolved.source,
        f"{resolved.width}x{resolved.height}, {resolved.detail}",
    )
    with Image.open(io.BytesIO(resolved.image_bytes)) as image:
        return prepare_cover_image(image)
