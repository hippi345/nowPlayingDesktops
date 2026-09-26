"""Persist original wallpaper path and session flags across runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from now_playing_desktops.config import state_file_path


@dataclass
class WallpaperSessionState:
    original_wallpaper_path: str | None = None
    original_wallpaper_snapshot: dict | None = None
    session_active: bool = False
    generated_wallpaper_dir: str | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> WallpaperSessionState:
        file_path = path or state_file_path()
        if not file_path.is_file():
            return cls()
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        snapshot = data.get("original_wallpaper_snapshot")
        return cls(
            original_wallpaper_path=data.get("original_wallpaper_path"),
            original_wallpaper_snapshot=snapshot if isinstance(snapshot, dict) else None,
            session_active=bool(data.get("session_active")),
            generated_wallpaper_dir=data.get("generated_wallpaper_dir"),
        )

    def save(self, path: Path | None = None) -> None:
        file_path = path or state_file_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def path_is_under_directory(candidate: Path, directory: Path) -> bool:
    try:
        candidate.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def should_capture_as_original(
    current: Path | None,
    *,
    generated_dir: Path,
    stored_original: str | None,
) -> Path | None:
    """Decide which path to store as the user's original wallpaper."""
    if current is None:
        if stored_original:
            return Path(stored_original)
        return None
    if path_is_under_directory(current, generated_dir):
        if stored_original:
            return Path(stored_original)
        return None
    return current
