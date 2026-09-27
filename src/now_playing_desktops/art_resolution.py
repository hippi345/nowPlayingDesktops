"""Resolve album art when SMTC bytes or Spotify URLs are missing."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_TIMEOUT_SECONDS = 5.0
PLACEHOLDER_SIZE = 1000
ITUNES_UPGRADE_OVER_SMTC_MIN_PX = 600


@dataclass(frozen=True)
class ResolvedArt:
    image_bytes: bytes
    source: str
    width: int
    height: int
    detail: str


def _normalize_name(value: str) -> str:
    lowered = value.casefold().strip()
    return re.sub(r"[^a-z0-9]+", "", lowered)


def artist_names_match(expected: str, candidate: str) -> bool:
    expected_norm = _normalize_name(expected)
    candidate_norm = _normalize_name(candidate)
    if not expected_norm or not candidate_norm:
        return False
    if expected_norm == candidate_norm:
        return True
    if expected_norm in candidate_norm or candidate_norm in expected_norm:
        return True
    expected_tokens = {t for t in re.split(r"[^a-z0-9]+", expected.casefold()) if t}
    candidate_tokens = {t for t in re.split(r"[^a-z0-9]+", candidate.casefold()) if t}
    if not expected_tokens or not candidate_tokens:
        return False
    overlap = expected_tokens & candidate_tokens
    return len(overlap) >= min(len(expected_tokens), len(candidate_tokens), 1)


def _itunes_cache_path(cache_dir: Path, artist: str, title: str) -> Path:
    key = hashlib.sha256(f"{artist}\0{title}".encode()).hexdigest()[:32]
    return cache_dir / "itunes" / f"{key}.json"


def lookup_itunes_artwork_url(
    artist: str,
    title: str,
    *,
    session: requests.Session,
    cache_dir: Path,
) -> str | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _itunes_cache_path(cache_dir, artist, title)
    if cache_path.is_file():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_url = payload.get("artwork_url")
            if isinstance(cached_url, str) and cached_url:
                return cached_url
        except (OSError, json.JSONDecodeError, TypeError):
            logger.warning("Could not read iTunes art cache at %s", cache_path, exc_info=True)

    term = quote(f"{artist} {title}")
    url = f"{ITUNES_SEARCH_URL}?term={term}&entity=song&limit=5"
    try:
        response = session.get(url, timeout=ITUNES_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.warning("iTunes artwork lookup failed for %s — %s", artist, title, exc_info=True)
        return None

    results = data.get("results") or []
    for entry in results:
        if not isinstance(entry, dict):
            continue
        candidate_artist = str(entry.get("artistName") or "")
        if not artist_names_match(artist, candidate_artist):
            continue
        artwork = entry.get("artworkUrl100")
        if not isinstance(artwork, str) or not artwork:
            continue
        hi_res = artwork.replace("100x100bb", "1000x1000bb")
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"artwork_url": hi_res}),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("Could not write iTunes art cache at %s", cache_path, exc_info=True)
        return hi_res
    logger.info("iTunes artwork lookup found no match for %s — %s", artist, title)
    return None


def _placeholder_colors(
    artist: str,
    title: str,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.sha256(f"{artist}\0{title}".encode()).digest()
    base = (
        40 + digest[0] % 120,
        45 + digest[1] % 110,
        70 + digest[2] % 100,
    )
    accent = (
        min(base[0] + 80, 255),
        min(base[1] + 60, 255),
        min(base[2] + 40, 255),
    )
    return base, accent


def render_placeholder_cover(
    title: str,
    artist: str,
    *,
    size: int = PLACEHOLDER_SIZE,
) -> Image.Image:
    top_rgb, bottom_rgb = _placeholder_colors(artist, title)
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        blend = y / max(size - 1, 1)
        color = tuple(
            int(top_rgb[channel] * (1 - blend) + bottom_rgb[channel] * blend)
            for channel in range(3)
        )
        draw.line([(0, y), (size, y)], fill=color)

    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", size=size // 14)
    except OSError:
        title_font = ImageFont.load_default()

    margin = size // 10
    text = title.strip() or "Unknown Title"
    subtitle = artist.strip() or "Unknown Artist"
    draw.multiline_text(
        (margin, size // 2 - size // 8),
        f"{text}\n{subtitle}",
        fill=(245, 245, 250),
        font=title_font,
        spacing=8,
    )
    return image.convert("RGBA")


def _image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _download_itunes_art(
    track,
    *,
    download_dir: Path,
    session: requests.Session,
) -> ResolvedArt | None:
    itunes_url = lookup_itunes_artwork_url(
        track.artist,
        track.title,
        session=session,
        cache_dir=download_dir,
    )
    if not itunes_url:
        return None
    try:
        response = session.get(itunes_url, timeout=ITUNES_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.content
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
        return ResolvedArt(
            image_bytes=data,
            source="itunes",
            width=width,
            height=height,
            detail=itunes_url,
        )
    except (requests.RequestException, OSError):
        logger.warning(
            "Failed to download iTunes artwork for %s — %s",
            track.artist,
            track.title,
            exc_info=True,
        )
        return None


def resolve_track_art(
    track,
    *,
    download_dir: Path,
    session: requests.Session | None = None,
) -> ResolvedArt:
    """Resolve cover bytes using SMTC, Spotify URL, iTunes, then placeholder."""
    http = session or requests.Session()

    if track.art_bytes:
        with Image.open(io.BytesIO(track.art_bytes)) as image:
            width, height = image.size
        smtc = ResolvedArt(
            image_bytes=track.art_bytes,
            source="smtc_thumbnail",
            width=width,
            height=height,
            detail=f"{len(track.art_bytes)} bytes",
        )
        if max(width, height) < ITUNES_UPGRADE_OVER_SMTC_MIN_PX:
            upgraded = _download_itunes_art(track, download_dir=download_dir, session=http)
            if upgraded and max(upgraded.width, upgraded.height) > max(width, height):
                logger.info(
                    "Preferring iTunes art over SMTC thumbnail (%dx%d -> %dx%d)",
                    width,
                    height,
                    upgraded.width,
                    upgraded.height,
                )
                return upgraded
        return smtc

    if track.art_url:
        from now_playing_desktops.spotify_art import download_album_art

        download_path = download_dir / f"{track.track_id}.jpg"
        download_album_art(track.art_url, download_path, session=http)
        data = download_path.read_bytes()
        with Image.open(download_path) as image:
            width, height = image.size
        return ResolvedArt(
            image_bytes=data,
            source="spotify_url",
            width=width,
            height=height,
            detail=track.art_url,
        )

    itunes = _download_itunes_art(track, download_dir=download_dir, session=http)
    if itunes is not None:
        return itunes

    placeholder = render_placeholder_cover(track.title, track.artist)
    png_bytes = _image_to_png_bytes(placeholder)
    return ResolvedArt(
        image_bytes=png_bytes,
        source="placeholder",
        width=placeholder.width,
        height=placeholder.height,
        detail="generated gradient cover",
    )


def describe_resolved_art_for_diag(
    track,
    *,
    download_dir: Path,
    session: requests.Session | None = None,
) -> str:
    """Lightweight art summary for diagnostics (may perform iTunes lookup)."""
    if track.art_bytes:
        with Image.open(io.BytesIO(track.art_bytes)) as image:
            width, height = image.size
        return f"smtc_thumbnail {width}x{height} ({len(track.art_bytes)} bytes)"
    if track.art_url:
        return f"spotify_url {track.art_url}"
    try:
        resolved = resolve_track_art(
            track,
            download_dir=download_dir,
            session=session,
        )
    except Exception as exc:
        return f"unresolved ({exc})"
    return f"{resolved.source} {resolved.width}x{resolved.height} ({resolved.detail})"
