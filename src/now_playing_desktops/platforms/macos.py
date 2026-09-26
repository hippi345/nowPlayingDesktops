"""macOS desktop wallpaper via Finder / appscript."""

from __future__ import annotations

from pathlib import Path


def set_desktop_wallpaper(image_path: Path) -> None:
    """Set the macOS desktop background to ``image_path``."""
    from appscript import app, mactypes

    app("Finder").desktop_picture.set(mactypes.File(str(image_path.resolve())))
