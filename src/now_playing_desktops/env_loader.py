"""Load Spotify OAuth settings from ``.env`` files without a shell environment."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from now_playing_desktops.config import user_config_dir

logger = logging.getLogger(__name__)

REQUIRED_SPOTIFY_ENV_VARS = ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET")


def env_file_candidates(*, explicit: Path | None = None) -> list[Path]:
    """Return candidate ``.env`` paths in lookup order (not filtered by existence)."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    env_from_var = os.environ.get("NOW_PLAYING_ENV_FILE", "").strip()
    if env_from_var:
        candidates.append(Path(env_from_var).expanduser())
    candidates.append(user_config_dir() / ".env")
    candidates.append(Path.cwd() / ".env")
    return candidates


def find_env_file(*, explicit: Path | None = None) -> Path | None:
    """Return the first existing env file from :func:`env_file_candidates`."""
    for path in env_file_candidates(explicit=explicit):
        if path.is_file():
            return path.resolve()
    return None


def load_environment(*, explicit: Path | None = None, verbose: bool = False) -> Path | None:
    """Load the first available env file without overriding variables already set."""
    path = find_env_file(explicit=explicit)
    if path is None:
        return None
    load_dotenv(path, override=False)
    if verbose:
        logger.debug("Loaded environment from %s", path)
    return path


def merged_env_values(*, explicit: Path | None = None) -> dict[str, str | None]:
    """Merge ``os.environ`` with values from the resolved env file (file wins for unset keys)."""
    merged: dict[str, str | None] = {
        key: os.environ.get(key) for key in (*REQUIRED_SPOTIFY_ENV_VARS, "SPOTIPY_REDIRECT_URI")
    }
    path = find_env_file(explicit=explicit)
    if path is not None:
        for key, value in dotenv_values(path).items():
            if value is not None and not merged.get(key):
                merged[key] = value
    return merged


def spotify_credentials_configured(*, explicit: Path | None = None) -> bool:
    """Return whether required Spotify OAuth variables are available."""
    values = merged_env_values(explicit=explicit)
    return all(values.get(name) for name in REQUIRED_SPOTIFY_ENV_VARS)


def default_env_file_hint() -> str:
    """Human-readable location where users should place autostart ``.env`` settings."""
    return str(user_config_dir() / ".env")


def missing_env_file_message() -> str:
    """Message when autostart cannot find OAuth settings."""
    return (
        "Cannot enable autostart: Spotify OAuth settings were not found. "
        f"Create {default_env_file_hint()} with SPOTIPY_CLIENT_ID and "
        "SPOTIPY_CLIENT_SECRET (see .env.example), or pass --env-file PATH."
    )


def resolve_spotify_username(explicit: str | None = None) -> str | None:
    """Resolve Spotify username from CLI argument or SPOTIPY_CLIENT_USERNAME."""
    if explicit and explicit.strip():
        return explicit.strip()
    from_env = os.environ.get("SPOTIPY_CLIENT_USERNAME", "").strip()
    if from_env:
        return from_env
    return None
