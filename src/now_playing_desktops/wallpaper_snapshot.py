"""Stable on-disk copies of the user's original wallpaper (byte snapshots)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from now_playing_desktops.wallpaper_state import path_is_under_directory

logger = logging.getLogger(__name__)

STABLE_WALLPAPER_BASENAME = "original_wallpaper"
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def file_digest(data: bytes) -> str:
    """Short uppercase hex digest for logging and snapshot metadata."""
    return hashlib.sha256(data).hexdigest()[:8].upper()


def extension_from_magic(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"BM"):
        return ".bmp"
    if data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def collect_render_content_hashes(generated_dir: Path | None) -> set[str]:
    if generated_dir is None or not generated_dir.is_dir():
        return set()
    digests: set[str] = set()
    for path in generated_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        try:
            digests.add(file_digest(path.read_bytes()))
        except OSError:
            continue
    return digests


def path_is_generated_render(
    candidate: Path,
    *,
    generated_dir: Path | None,
    state_dir: Path | None,
) -> bool:
    if generated_dir and path_is_under_directory(candidate, generated_dir):
        return True
    if state_dir and path_is_under_directory(candidate, state_dir):
        name = candidate.name.lower()
        if name.startswith(STABLE_WALLPAPER_BASENAME):
            return True
    return False


def bytes_match_render(data: bytes, render_digests: set[str]) -> bool:
    if not data:
        return False
    return file_digest(data) in render_digests


def should_preserve_existing_snapshot(
    existing: dict[str, Any] | None,
    *,
    session_active: bool,
    recovering: bool,
) -> bool:
    if not existing:
        return False
    if not (session_active or recovering):
        return False
    stable = existing.get("stable_path")
    if not stable:
        return False
    path = Path(str(stable))
    return path.is_file() and path.stat().st_size > 0


def write_stable_wallpaper_copy(
    data: bytes,
    state_dir: Path,
    *,
    basename: str = STABLE_WALLPAPER_BASENAME,
) -> tuple[Path, str]:
    state_dir.mkdir(parents=True, exist_ok=True)
    ext = extension_from_magic(data)
    dest = state_dir / f"{basename}{ext}"
    dest.write_bytes(data)
    digest = file_digest(data)
    logger.info(
        "Wrote stable wallpaper snapshot (%s bytes, digest=%s): %s",
        len(data),
        digest,
        dest,
    )
    return dest, digest


def copy_file_to_stable_wallpaper(
    source: Path,
    state_dir: Path,
    *,
    basename: str = STABLE_WALLPAPER_BASENAME,
) -> tuple[Path, str]:
    data = source.read_bytes()
    return write_stable_wallpaper_copy(data, state_dir, basename=basename)


def attach_stable_copy_to_snapshot(
    snapshot: dict[str, Any],
    *,
    state_dir: Path,
    source_path: Path | None,
    source_bytes: bytes | None,
    generated_dir: Path | None,
    render_digests: set[str] | None = None,
    basename: str = STABLE_WALLPAPER_BASENAME,
) -> dict[str, Any]:
    """Return ``snapshot`` updated with ``stable_path`` and ``content_hash`` when possible."""
    digests = (
        render_digests
        if render_digests is not None
        else collect_render_content_hashes(generated_dir)
    )
    data = source_bytes
    if data is None and source_path is not None and source_path.is_file():
        if path_is_generated_render(
            source_path,
            generated_dir=generated_dir,
            state_dir=state_dir,
        ):
            logger.debug("Skipping generated render path as wallpaper source: %s", source_path)
            return snapshot
        data = source_path.read_bytes()
    if data is None:
        return snapshot
    if bytes_match_render(data, digests):
        logger.debug("Skipping wallpaper source matching a composed render digest")
        return snapshot
    dest, digest = write_stable_wallpaper_copy(data, state_dir, basename=basename)
    snapshot = dict(snapshot)
    snapshot["stable_path"] = str(dest.resolve())
    snapshot["content_hash"] = digest
    snapshot["path"] = snapshot["stable_path"]
    return snapshot
